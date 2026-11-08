"""reset_user_passwords: generated passwords are strong enough and verify against their hash."""

import importlib.util
from pathlib import Path

from pi_api.modules.auth.service import hash_password, verify_password

_spec = importlib.util.spec_from_file_location(
    "reset_user_passwords",
    Path(__file__).resolve().parents[2] / "scripts" / "reset_user_passwords.py",
)
reset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reset)


def test_temp_password_shape():
    pws = {reset.temp_password() for _ in range(200)}
    assert len(pws) == 200  # no repeats
    for pw in pws:
        assert len(pw) == 14 and pw.isalnum()
        assert any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw)


def test_temp_password_round_trips_through_argon2():
    pw = reset.temp_password()
    assert verify_password(pw, hash_password(pw))
