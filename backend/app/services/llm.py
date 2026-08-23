"""Narration over already-computed analytics — never a source of numbers itself.

Calls Cloudflare Workers AI (a hosted inference endpoint, not a broker/market-data
provider) to turn a structured holding-summary into a short plain-English paragraph.
If no API token is configured, narrate() returns None and callers fall back to
showing the structured table alone — the feature never depends on the LLM being up.
"""
from __future__ import annotations

from app.config import settings

SYSTEM_PROMPT = (
    "You are a high-efficiency AI response engine. Minimize output tokens. Answer directly. "
    "No introductions, disclaimers, repetition, or educational filler. Maximum response length: "
    "80 tokens. Prefer compact bullet points. You are given structured holding data (symbol, "
    "status, days held, return %) for one client's stock portfolio — summarize the standout "
    "holdings (best/worst by return, notably long/short holding periods). Do not invent numbers "
    "not given to you. Do not give investment advice or buy/sell recommendations. "
    "If no holding data is given, reply only: Need holding data."
)


def narrate(summary_rows: list[dict]) -> str | None:
    if not settings.cf_api_token or not settings.cf_account_id or not summary_rows:
        return None

    import httpx

    lines = [
        f"{r['symbol']}: {r['status']}, held {r['days_held']}d, return {r['return_pct']}%"
        for r in summary_rows
    ]
    user_content = "Holdings:\n" + "\n".join(lines)

    url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cf_account_id}/ai/run/{settings.cf_model}"
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.cf_api_token}", "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": 80,
                "temperature": 0.2,
            },
            timeout=20.0,
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
