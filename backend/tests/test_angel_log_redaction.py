"""SmartApi logs request headers/params on errors; secrets must never reach the log."""
import logging

from app.services import angel


SAMPLE = (
    "Error occurred while making a POST request to https://x/quote. Error: Invalid Token. "
    "Headers: {'Content-type': 'application/json', 'Authorization': 'Bearer eyJhbGciOi.abc.def', "
    "'X-PrivateKey': 'abcd1234', 'X-UserType': 'USER'}, "
    "Request: {'clientcode': 'Z1', 'password': '9999', 'totp': '123456'}, "
    "Response: {'jwtToken': 'eyJxyz', \"refreshToken\": \"r3fr\", 'feedToken': 'f33d'}"
)


def test_redact_removes_every_secret():
    out = angel.redact_secrets(SAMPLE)
    for secret in ("eyJhbGciOi", "abc.def", "abcd1234", "9999", "123456", "eyJxyz", "r3fr", "f33d"):
        assert secret not in out, secret
    assert "'X-PrivateKey': '***'" in out
    assert "'Content-type': 'application/json'" in out      # non-secrets untouched
    assert "'X-UserType': 'USER'" in out and "'clientcode': 'Z1'" in out


def test_logzero_logger_redacts(caplog):
    from logzero import logger as lz
    angel.install_log_redaction()
    angel.install_log_redaction()                            # idempotent
    assert sum(isinstance(f, angel._RedactSecrets) for f in lz.filters) == 1
    seen = []
    h = logging.Handler()
    h.emit = lambda r: seen.append(h.format(r))
    lz.addHandler(h)
    try:
        lz.error(SAMPLE)
        lz.error("key %s", "'X-PrivateKey': 'zzz999'")
    finally:
        lz.removeHandler(h)
    assert seen and all("abcd1234" not in s and "zzz999" not in s for s in seen)


def test_smartconnect_uses_the_filtered_logger():
    import SmartApi.smartConnect as sc
    from logzero import logger as lz
    assert sc.logger is lz
