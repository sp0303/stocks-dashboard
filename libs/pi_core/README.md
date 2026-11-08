# `pi_core` (Portfolio Intelligence v2 Core Domain Library)

Pure Python domain library for Portfolio Intelligence v2.
Holds the financial calculation engine, time-weighted returns, benchmark PME, metrics, allocation analytics, and ORB strategy logic.

## Principles (Enforced by tests)
1. **Zero I/O:** No network, database, filesystem, or provider calls.
2. **Deterministic & pure:** No clock reads (`today` is always passed as an explicit date parameter).
3. **Single-pass algorithms:** Walks the trade and corporate-action stream in $O(N)$ time.
4. **Governed by Domain Rules R1–R18:** Every metric formula adheres to `docs/v2/DOMAIN-RULES.md`.
