"""Contract: the ingest and ledger paths call the recompute hook as f(conn, client_id).

Regression: the batch function grew to five parameters while its callers still passed
two, which would have raised TypeError on every upload and manual trade.
"""

import inspect

from pi_api.modules.ledger import router as ledger_router
from pi_workers import ingest_worker
from pi_workers.portfolio_worker import recompute_single_client


def test_single_client_hook_takes_conn_and_client_id():
    assert list(inspect.signature(recompute_single_client).parameters) == ["conn", "client_id"]


def test_callers_use_the_two_argument_hook():
    assert ledger_router.recompute_single_client is recompute_single_client
    assert ingest_worker.recompute_single_client is recompute_single_client
    assert "recompute_client_portfolio(conn, client_id)" not in inspect.getsource(ingest_worker)
