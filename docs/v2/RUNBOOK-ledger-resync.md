# Runbook: v1 → v2 ledger resync

**Why:** after the 2026-10-04 one-time migration, v1 (Mongo) kept receiving tradebook and Groww uploads, manual/adjustment trades (IPO allotments, rights, demerger cost splits), corporate-action fixes (31+ split/bonus records on 2026-11-08), dividends, notes/tags, theses, watchlists, board items and new clients/managers. v2 drifted (155 held symbols vs v1 41; one client 11 positions vs 8; two clients and one manager missing; 5 empty test clients only in v2).

**What:** `scripts/sync_v1_ledger_to_v2.py` (code: `apps/workers/pi_workers/v1_sync_ledger*.py`) reads v1 Mongo **read-only** and brings v2 in line:

| Entity | v2 target | Match key | On change in v1 |
|---|---|---|---|
| managers | `core.managers` | `legacy_id`, else email (if the v2 row has no legacy id) | update |
| clients | `core.clients` | `legacy_id`, else (manager, client_code) | update (v2 broker kept when v1 has none) |
| uploads | `ledger.uploads` | `legacy_id` / (client, sha256) | insert-only |
| trades | `ledger.trades` | (client, v1 fingerprint; includes the broker trade id) | **insert-only** (R13.5); raw v1 doc in `extra.v1` |
| corporate actions | `ledger.corporate_actions` | `key` | update; any change ⇒ recompute all (R8) |
| dividends | `ledger.dividends` | (client, symbol, ex_date) | update |
| theses | `research.stock_theses` | (client, symbol) | update (v1 wins) |
| watchlists + entries | `research.watchlists`, `research.watchlist_entries` | (owner, list name), (list, symbol) | entries update (v1 wins) |
| board items | `research.board_items` | (owner, symbol) | update (v1 wins) |
| trade notes / tags | `research.trade_notes`, `research.trade_tags` | via `scripts/reconcile_trade_notes_tags.py` | insert-only; **v2 edits win** |

Writes: one transaction, COPY → temp staging → `MERGE` (AGENTS §3.8); an advisory lock stops overlapping runs. Rejected v1 docs go to `ops.dq_issues` (`check_name='v1_ledger_sync_reject'`, raw doc + reason; R13.3), once each. Each real run writes an `ops.job_runs` row (`job='v1_ledger_sync'`).

**Never deleted.** Orphans (v2 rows whose v1 source is gone) are *reported*. `--flag-orphans` soft-flags only: v1-origin trades get `deleted_at` (tombstone), orphan clients with **zero** live trades become `INACTIVE`, orphan managers with no live client become inactive. It refuses to tombstone more than 5 % of v1-origin trades (`--max-orphan-fraction`). Dividends, CAs, theses, watchlist rows and board items have no soft-delete column: they are report-only.

## 0. Prerequisites (owner)

1. **Rotate passwords first** (NEXTSTEPS "Blocked on owner"): `pi_migrator`, `pi_worker`, `pi_api` (pi_migrator was exposed in a transcript), and the v2 admin temp password.
2. **DB role for the sync.** Per LLD-database, `pi_worker` is RW on ledger/ops but **read-only on core**, and `research` is written by `pi_api`. The sync writes `core`, `ledger`, `research` and `ops`. Pick one (an owner decision, AGENTS §11):
   - (a) a dedicated `pi_ledger_sync` role: `GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA core, ledger, research TO pi_ledger_sync; GRANT SELECT, INSERT ON ops.dq_issues, ops.job_runs TO pi_ledger_sync;` plus `USAGE` on those schemas and sequences — **no DELETE**; or
   - (b) the same grants on `pi_worker`.
3. Create `/etc/pi/worker.env`, owner `pi`, mode `0600`:
   ```
   DATABASE_URL=postgresql://pi_worker:<rotated>@127.0.0.1:5432/<db>     # recompute (portfolio.*)
   LEDGER_SYNC_DSN=postgresql://pi_ledger_sync:<rotated>@127.0.0.1:5432/<db>
   MONGODB_URL=mongodb://<v1 read user>@127.0.0.1:27017/
   MONGODB_DB=stocks
   ```
   The owner types these values; agents never do. Prefer a read-only Mongo user.
4. `pymongo` installed in `/var/www/portfolio-v2/.venv` (already done on 2026-10-04).
5. Disk: `df -h /var/backups` — the dump below needs free space (disk was ~75 %).

## 1. Backup

```bash
sudo -u postgres pg_dump -Fc -d <db> -n core -n ledger -n research -n ops \
  -f /var/backups/pi-v2/pre-ledger-resync-$(date +%Y%m%d-%H%M).dump
sudo chmod 0600 /var/backups/pi-v2/pre-ledger-resync-*.dump
```

## 2. Dry run (read-only transaction; Postgres refuses any write)

```bash
cd /var/www/portfolio-v2
set -a; . /etc/pi/worker.env; set +a
PYTHONPATH=libs/pi_core:apps/api:apps/workers .venv/bin/python scripts/sync_v1_ledger_to_v2.py --dry-run
PYTHONPATH=libs/pi_core:apps/api:apps/workers .venv/bin/python scripts/verify_migration.py --ledger   # drift before
```

Check: `clients insert` ≥ 2 (the two clients missing from v2), `managers insert` 1 (SP), `trades insert` ≈ post-migration uploads + manual trades, `corporate_actions insert` ≈ 31+, the 5 test clients listed as `ORPHAN client … active_trades=0`, and the `rejects` line. A large `ORPHAN trades` count means v2 holds trades v1 no longer has (e.g. v1 manual trades removed) — review before flagging. Notes for brand-new trades show as unresolved in the dry run's journal section; they resolve on the real run.

## 3. Real run

```bash
PYTHONPATH=libs/pi_core:apps/api:apps/workers .venv/bin/python scripts/sync_v1_ledger_to_v2.py --apply --recompute
```

Optional, after reviewing the orphan list: `… --apply --flag-orphans` (tombstones / INACTIVE only).

## 4. Reconcile (R18)

```bash
PYTHONPATH=libs/pi_core:apps/api:apps/workers .venv/bin/python scripts/verify_migration.py --ledger
PYTHONPATH=libs/pi_core:apps/api:apps/workers .venv/bin/python scripts/verify_migration.py           # counts
```

`--ledger` prints per client: v1 vs v2 trade counts, fingerprints missing either side, and symbols whose raw open quantity (buys − sells, tombstones excluded) differs. Exit 1 while drift remains. Then compare a few books in the v2 UI against v1 (pick one client and compare its position count and market value).

## 5. Recompute

`--recompute` runs `python -m pi_workers.portfolio_worker --recompute-all` (pi_worker `DATABASE_URL`) only when the ledger changed. Manual: `sudo systemctl start pi-portfolio-recompute.service`. Clients flagged `INACTIVE` are not recomputed.

## 6. Enable the timer (only when asked)

```bash
sudo cp infra/systemd/pi-ledger-sync.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start pi-ledger-sync.service && journalctl -u pi-ledger-sync -n 50   # one supervised run
sudo systemctl enable --now pi-ledger-sync.timer
```

Every 15 min Mon–Sat. It never restarts or touches the ORB feed, so it is safe in market hours (AGENTS §10). It never passes `--flag-orphans`. Exit 2 (lock held) is treated as success.

## 7. Rollback

1. `sudo systemctl disable --now pi-ledger-sync.timer`
2. Rows added by the sync carry `extra ? 'v1_sync'` (trades) and are listed in `ops.job_runs.meta`. For a full rollback restore the dump: `sudo -u postgres pg_restore -d <db> --clean --if-exists -n core -n ledger -n research -n ops /var/backups/pi-v2/pre-ledger-resync-….dump`, then recompute. A partial undo (e.g. un-tombstone) is `UPDATE ledger.trades SET deleted_at = NULL WHERE …`; INACTIVE clients: `UPDATE core.clients SET status='ACTIVE' WHERE …`.
3. Delete the dump when the sync is verified (it holds client PII, AGENTS §9).

## Known limits

- v1 trades are hard-deleted in v1; v2 only learns of it as an orphan. v2-native trades (no legacy id, created after the cutover, not written by the sync) are counted, never flagged.
- `ledger.uploads.broker_format` is `OTHER` for synced uploads (v1 never recorded it; the raw file is not in Mongo).
- Board items lose v1's `entered_at/entered_price/exited_*`; CAs lose `record_date/face_value/company` (no v2 columns).
- v1 Kite-sync trades lack `client_id`/`trade_type` and are rejected with a reason.
- Watchlist entries without a v1 `added_date` get the run date (column is NOT NULL).
