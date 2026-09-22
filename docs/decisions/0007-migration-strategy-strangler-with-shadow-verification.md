# 0007. Migration Strategy: Strangler With Shadow Verification

* **Status**: Proposed (awaiting approval)
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `docs/v2/MIGRATION-PLAN.md`; the metrics audit (Sept 2026)

---

## 1. Context and Problem Statement

This is financial software whose numbers users act on. A big-bang rewrite fails quietly: wrong numbers look plausible. The metrics audit found **twelve classes of defect** in v1 (for example a 13.6 % price overstatement from a frozen feed, and a full sale reading as a −90 % day). Separately, the *first draft of the fix* produced a −1084 % drawdown on a real book while its unit tests passed. Both kinds of error were found only by running the code on the real dataset.

## 2. Decision

1. **v1 keeps serving users, untouched, until cutover.** It is feature-frozen after Phase 0 and receives only bug and security fixes.
2. **Ship the known metric fixes to v1 first** (Phase 0), so users are not looking at wrong numbers for the months a rewrite takes.
3. **Correctness is defined by rules and golden fixtures, not by v1's output.** v2 is measured against DOMAIN-RULES R1–R18. A **shadow report** diffs v2 against v1's numbers and requires every difference to be *explained* as intentional or fixed; the target is zero unexplained deltas above ₹1.
4. **Data moves by an idempotent, verifiable ETL** with a signed report (counts, per-client sums, fingerprint sets, candle checksums, engine parity). Mongo stays read-only for 30 days.
5. **Cut over by slice and by user:** soak at `/v2/`, canary one manager, then a Saturday full cutover. Cutover is reversible until the first v2 write, and reversible with a tested delta-export for 7 days after.
6. **No unverified claim of "done":** each phase's exit gate is demonstrated on production-shaped data and rendered pages, not only on unit tests (project owner's standing requirement).

## 3. Consequences

**Positive:** users are never on an unverified system; every numeric change is explained; the rollback path is real; the golden fixtures outlive the migration as a permanent regression suite.
**Negative / cost:** v1 and v2 run in parallel for weeks (capacity on one VM must be checked, O-1); a nightly ETL must be maintained during the soak; the feature freeze needs discipline.
**Rejected:** big-bang cutover; porting v1 code line by line (it would port its defects); dual-writing v1 and v2 (complexity for little gain at this write volume).
