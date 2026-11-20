"""Manager-level upload: any tradebook is routed to the client it belongs to, never guessed."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services import ingestion


def _xlsx(code="", name="", n=1, price=1500.0):
    trades = [{"symbol": "INFY", "isin": "INE009A01021", "exchange": "NSE", "segment": "EQ",
               "series": "EQ", "trade_date": "2026-10-06", "trade_type": "buy", "quantity": 1,
               "price": price + i, "trade_id": f"{code or name}{i}", "order_id": f"9{i}",
               "order_execution_time": "2026-10-06T10:00:00"} for i in range(n)]
    return ingestion.build_tradebook_xlsx(trades, code, name)


@pytest.fixture()
def book(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_url", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_password", "adminpass")
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"role": "admin", "password": "adminpass"}).json()["data"]["token"]}

        def mgr(name):
            return c.post("/api/admin/managers", json={"name": name, "email": f"{name}@x.io"},
                          headers=h).json()["data"]["id"]

        def client(mid, name, code=""):
            return c.post("/api/clients", json={"name": name, "portfolio_manager_id": mid, "client_code": code},
                          headers=h).json()["data"]["id"]

        m1, m2 = mgr("m1"), mgr("m2")
        ids = {
            "coded": client(m1, "Asha Rao", "AB1234"),
            "uncoded": client(m1, "Sumanth Billa"),
            "other_mgr": client(m2, "Other Person", "ZZ9999"),
        }
        yield c, h, m1, m2, ids


def _up(c, h, mid, body, force=False):
    url = f"/api/managers/{mid}/tradebooks" + ("?force=true" if force else "")
    return c.post(url, files={"file": ("tb.xlsx", body, "application/octet-stream")}, headers=h)


def _count(c, h, cid):
    return len(c.get(f"/api/clients/{cid}/trades", headers=h).json()["data"])


def test_parser_reads_holder_name_but_not_header_columns():
    import io
    p = ingestion.parse_tradebook(io.BytesIO(_xlsx("AB1234", "Asha Rao")))
    assert (p.file_client_id, p.file_client_name) == ("AB1234", "Asha Rao")
    assert ingestion.parse_tradebook(io.BytesIO(_xlsx("AB1234"))).file_client_name is None


def test_routed_by_account_code(book):
    c, h, m1, _, ids = book
    r = _up(c, h, m1, _xlsx("ab1234", "Someone Else", n=2))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["client"]["id"] == ids["coded"] and d["matched_by"] == "account"
    assert d["summary"]["imported"] == 2
    assert _count(c, h, ids["coded"]) == 2 and _count(c, h, ids["uncoded"]) == 0


def test_routed_by_name_word_order_and_case_insensitive_and_code_adopted(book):
    c, h, m1, _, ids = book
    r = _up(c, h, m1, _xlsx("QQ1111", "BILLA  SUMANTH"))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["client"]["id"] == ids["uncoded"] and r.json()["data"]["matched_by"] == "name"
    assert c.get(f"/api/clients/{ids['uncoded']}", headers=h).json()["data"]["client_code"] == "QQ1111"
    # from now on the code itself routes it
    r2 = _up(c, h, m1, _xlsx("QQ1111", "", price=1600.0))
    assert r2.status_code == 200 and r2.json()["data"]["matched_by"] == "account"


def test_name_never_overrides_a_different_account_code(book):
    c, h, m1, _, ids = book
    r = _up(c, h, m1, _xlsx("XY0001", "Asha Rao"))            # Asha's account is AB1234
    assert r.status_code == 422 and "no client" in r.text
    assert _count(c, h, ids["coded"]) == 0


def test_partial_name_is_not_a_match(book):
    c, h, m1, _, ids = book
    assert _up(c, h, m1, _xlsx("", "Sumanth")).status_code == 422
    assert _count(c, h, ids["uncoded"]) == 0


def test_another_managers_account_is_refused(book):
    c, h, m1, _, ids = book
    r = _up(c, h, m1, _xlsx("ZZ9999", "Other Person"))
    assert r.status_code == 422 and "not one of your clients" in r.text
    assert _count(c, h, ids["other_mgr"]) == 0


def test_file_with_no_code_or_name_is_refused(book):
    c, h, m1, _, _ = book
    r = _up(c, h, m1, _xlsx("", ""))
    assert r.status_code == 422 and "cannot be matched" in r.text


def test_name_only_file_cannot_land_on_a_coded_client(book):
    c, h, m1, _, ids = book
    r = _up(c, h, m1, _xlsx("", "Asha Rao"))                   # existing per-client guard still applies
    assert r.status_code == 422
    assert _count(c, h, ids["coded"]) == 0


def test_duplicate_names_are_ambiguous(book):
    c, h, m1, _, _ = book
    c.post("/api/clients", json={"name": "sumanth billa", "portfolio_manager_id": m1}, headers=h)
    r = _up(c, h, m1, _xlsx("", "Sumanth Billa"))
    assert r.status_code == 409 and "more than one client" in r.text


def test_same_file_twice_is_409_then_force_reimports_without_dupes(book):
    c, h, m1, _, ids = book
    body = _xlsx("AB1234", n=3)
    assert _up(c, h, m1, body).status_code == 200
    r = _up(c, h, m1, body)
    assert r.status_code == 409 and "already uploaded" in r.text
    r = _up(c, h, m1, body, force=True)
    assert r.status_code == 200 and r.json()["data"]["summary"]["imported"] == 0
    assert _count(c, h, ids["coded"]) == 3


def test_manager_cannot_upload_into_another_managers_book(book):
    c, h, m1, m2, _ = book
    # a manager token for m1 must not post to m2's route
    from app.services import auth
    tok = auth.make_token({"role": "manager", "manager_id": m1})
    r = _up(c, {"Authorization": f"Bearer {tok}"}, m2, _xlsx("ZZ9999"))
    assert r.status_code == 403


def test_per_client_upload_unchanged(book):
    c, h, _, _, ids = book
    r = c.post(f"/api/clients/{ids['coded']}/tradebooks",
               files={"file": ("tb.xlsx", _xlsx("AB1234"), "application/octet-stream")}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["summary"]["imported"] == 1
