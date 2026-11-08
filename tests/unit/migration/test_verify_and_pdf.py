"""Count-diff logic of verify_migration and the pdf_uploads report."""

from migrate_pdf_uploads import summarise
from verify_migration import (
    Check,
    evaluate,
    missing_fingerprints,
    render,
    status,
    watchlist_counts,
)


def test_status_rules():
    assert status(Check("x", 5, 5, True), strict=False) == "OK"
    assert status(Check("x", 5, 6, True), strict=False) == "OK(+v2)"
    assert status(Check("x", 5, 6, True), strict=True) == "MISMATCH"
    assert status(Check("x", 5, 4, True), strict=False) == "MISMATCH"
    assert status(Check("x", 5, 4, False), strict=False) == "info"
    assert status(Check("x", 5, None, True), strict=False) == "ERROR"
    assert status(Check("x", 5, None, False), strict=False) == "n/a"


def test_evaluate_exit_code_only_on_required():
    _, code = evaluate([Check("a", 1, 1, True), Check("b", 3, 0, False)], strict=False)
    assert code == 0
    rows, code = evaluate([Check("a", 2, 1, True)], strict=False)
    assert code == 1 and "MISMATCH" in render(rows)


def test_missing_fingerprints():
    assert missing_fingerprints(["a", "b", "b"], ["b", "c"]) == 1


def test_watchlist_counts_handles_lists_and_legacy():
    docs = [
        {
            "lists": [
                {"entries": [{"symbol": "A"}, {"symbol": "A"}, {"symbol": "B"}]},
                {"entries": []},
            ]
        },
        {"entries": [{"symbol": "C"}]},
        {"symbols": ["D", "E"]},
        {},
    ]
    assert watchlist_counts(docs) == (4, 4, 5)


def test_pdf_summary_counts_only():
    c = summarise(
        [
            {"scope": "manager", "status": "DONE", "file_hash": "ab"},
            {"scope": "client", "status": "FAILED", "file_hash": "cd", "blob": b"%PDF"},
        ]
    )
    assert c["docs"] == 2 and c["no_client_owner"] == 1 and c["has_bytes"] == 1
    assert c["status_DONE"] == 1 and c["with_file_hash"] == 2
