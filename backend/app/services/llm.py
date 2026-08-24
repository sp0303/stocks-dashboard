"""Narration over already-computed analytics — never a source of numbers itself.

Turns a client's full holding-summary (which can run to hundreds of rows once
closed round-trips pile up) into a short plain-English analysis. Rather than
handing the model every raw row — which drowns an 8B local model and makes it
ramble instead of answering — we first reduce the rows to a handful of
indicators (win rate, average return, best/worst, most re-traded symbol,
longest held) and ask for real commentary on those, not a per-row rephrase.

Tries a local Ollama model first (free, no daily cap, runs on the same host),
then Cloudflare Workers AI if configured, then falls back to a deterministic
plain-Python summary built from the same indicators. narrate() only returns
None if every option is unavailable or empty — callers then show the
structured table alone.
"""
from __future__ import annotations

from collections import Counter

from app.config import settings

SYSTEM_PROMPT = (
    "You are a portfolio analyst writing a client-facing summary for a wealth manager to share "
    "with their client. You are given a small set of pre-computed indicators for one client's "
    "stock portfolio (win rate, average return, best/worst positions, most re-traded symbol, "
    "longest held) — not raw trade data. Write 3-5 sentences of real analysis connecting these "
    "numbers (e.g. trading discipline, concentration risk, whether gains are broad-based or from "
    "one outlier) — do not just restate each indicator as a bullet. "
    "Tone: confident and encouraging, the way a manager would present results to keep a client "
    "engaged — but every claim must be earned by the actual numbers, never exaggerated or invented. "
    "Cite specific figures naturally in the sentences (percentages, day counts, trade counts) rather "
    "than speaking only in vague terms. Where a number is weak, frame it constructively (an area "
    "worth watching, room to tighten up) instead of alarming language. "
    "Do not invent numbers not given to you. Do not give investment advice or buy/sell "
    "recommendations. Plain prose, no headers or emoji, no closing sign-off. "
    "If no indicators are given, reply only: Need holding data."
)


def compute_indicators(summary_rows: list[dict]) -> dict | None:
    """Reduce a (potentially huge) list of per-position rows to the handful of
    signals worth narrating. Shared by every narration path so the LLM and the
    deterministic fallback are always describing the same facts."""
    if not summary_rows:
        return None

    closed = [r for r in summary_rows if r["status"] == "closed" and r["return_pct"] is not None]
    open_positions = [r for r in summary_rows if r["status"] == "open"]
    ranked = sorted((r for r in summary_rows if r["return_pct"] is not None), key=lambda r: r["return_pct"])
    longest_held = max(summary_rows, key=lambda r: r["days_held"] or 0)

    win_rate_pct = round(sum(1 for r in closed if r["return_pct"] > 0) / len(closed) * 100, 1) if closed else None
    avg_return_pct = round(sum(r["return_pct"] for r in closed) / len(closed), 1) if closed else None

    freq = Counter(r["symbol"] for r in closed)
    most_traded = freq.most_common(1)[0] if freq else None

    return {
        "open_count": len(open_positions),
        "closed_count": len(closed),
        "win_rate_pct": win_rate_pct,
        "avg_return_pct": avg_return_pct,
        "best": ranked[-1] if ranked else None,
        "worst": ranked[0] if ranked and ranked[0] is not ranked[-1] else None,
        "longest_held": longest_held,
        "most_traded_symbol": most_traded[0] if most_traded else None,
        "most_traded_count": most_traded[1] if most_traded else 0,
    }


def fallback_narrate(summary_rows: list[dict]) -> str | None:
    """Plain-Python stand-in for narrate() — same indicators, no LLM call. Used
    when every LLM provider is unconfigured, rate-limited, or erroring, so the
    summary card still has content instead of going blank."""
    ind = compute_indicators(summary_rows)
    if ind is None:
        return None

    parts = []
    if ind["best"]:
        parts.append(f"Best: {ind['best']['symbol']} {ind['best']['return_pct']:+.1f}% ({ind['best']['status']})")
    if ind["worst"]:
        parts.append(f"Worst: {ind['worst']['symbol']} {ind['worst']['return_pct']:+.1f}% ({ind['worst']['status']})")
    parts.append(f"Longest held: {ind['longest_held']['symbol']} ({ind['longest_held']['days_held']}d)")
    if ind["win_rate_pct"] is not None:
        parts.append(f"Win rate: {ind['win_rate_pct']}% of {ind['closed_count']} closed trades")

    return ". ".join(parts) + "."


def _indicators_text(ind: dict) -> str:
    lines = [f"Open positions: {ind['open_count']}, Closed round-trips: {ind['closed_count']}"]
    if ind["win_rate_pct"] is not None:
        lines.append(f"Win rate (closed): {ind['win_rate_pct']}%")
    if ind["avg_return_pct"] is not None:
        lines.append(f"Average return (closed): {ind['avg_return_pct']}%")
    if ind["best"]:
        b = ind["best"]
        lines.append(f"Best: {b['symbol']} {b['return_pct']}% ({b['status']}, held {b['days_held']}d)")
    if ind["worst"]:
        w = ind["worst"]
        lines.append(f"Worst: {w['symbol']} {w['return_pct']}% ({w['status']}, held {w['days_held']}d)")
    lh = ind["longest_held"]
    lines.append(f"Longest held: {lh['symbol']} ({lh['days_held']}d, {lh['status']})")
    if ind["most_traded_symbol"]:
        lines.append(f"Most re-traded symbol: {ind['most_traded_symbol']} ({ind['most_traded_count']} round trips)")
    return "Portfolio indicators:\n" + "\n".join(lines)


def _narrate_ollama(indicators_text: str) -> tuple[str | None, str | None]:
    """Returns (narrative, thinking). thinking is the model's chain-of-thought,
    shown collapsed in the UI the way ChatGPT/Claude show reasoning traces —
    kept separate from `content` (the actual answer) via Ollama's native
    thinking field rather than parsed out of the text."""
    if not settings.ollama_enabled:
        return None, None

    import httpx

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        r = httpx.post(
            url,
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": indicators_text},
                ],
                "stream": False,
                "think": True,
                "options": {"num_predict": 2000, "temperature": 0.3},  # thinking + answer share this budget; no cost on local Ollama, just time
            },
            timeout=240.0,  # local CPU inference is slower than a hosted API — worth the wait for quality
        )
        if r.status_code != 200:
            return None, None
        message = r.json().get("message") or {}
        text = (message.get("content") or "").strip()
        thinking = (message.get("thinking") or "").strip()
        return (text or None), (thinking or None)
    except Exception:
        return None, None


def _narrate_cloudflare(indicators_text: str) -> str | None:
    if not settings.cf_api_token or not settings.cf_account_id:
        return None

    import httpx

    url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cf_account_id}/ai/run/{settings.cf_model}"
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.cf_api_token}", "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": indicators_text},
                ],
                "max_tokens": 250,
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("success"):
            return None
        result = data.get("result", {})
        text = result.get("response") or ""
        if not text.strip():
            # some models (reasoning models especially) only populate the
            # OpenAI-style choices[].message.content field, not `response`.
            choices = result.get("choices") or []
            if choices:
                text = choices[0].get("message", {}).get("content") or ""
        return text.strip() or None
    except Exception:
        return None


def narrate(summary_rows: list[dict]) -> tuple[str | None, str | None]:
    """Returns (narrative, thinking). thinking is only ever populated by the
    Ollama path — Cloudflare and the deterministic fallback have none."""
    ind = compute_indicators(summary_rows)
    if ind is None:
        return None, None
    indicators_text = _indicators_text(ind)

    text, thinking = _narrate_ollama(indicators_text)
    if text:
        return text, thinking
    return _narrate_cloudflare(indicators_text), None
