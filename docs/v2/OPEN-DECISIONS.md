# v2 — Open Decisions and Unverified Facts

**Status:** needs the project owner · 21 Sep 2026
Each row says what blocks on it and what I recommend. Nothing here has been decided silently.

## A. Decisions

| ID | Question | Options | Recommendation | Blocks |
|---|---|---|---|---|
| **O-1** | **VM capacity.** CPU, RAM, architecture and free disk of the OCI box. It must host v1, v2, MongoDB, Postgres, two Redis, workers and (per its CHANGELOG) quest-mf's data tier. I did not read production, so this is unknown. | (a) it fits; (b) add a block volume; (c) second VM for the data tier | run `lscpu; free -h; df -h; uname -m` on the box and share it; decide after | Phase 0.3, all sizing |
| **O-2** | **Postgres topology.** | (a) shared cluster, separate database `portfolio` + roles + connection limits; (b) separate instance on another port; (c) separate VM | (a) if the cluster is confirmed private (O-11), else (b). Revisit at the second VM | Phase 1 |
| **O-3** | **Gain/loss colour.** v1 = green/red. quest-mf = ink positive, ember negative with `+`/▲ and `−`/▼ | (a) adopt quest-mf; (b) keep green/red as a documented extension | (a) for one design language; (b) if managers/clients rely on the colour | Phase 4 |
| **O-4** | **Process supervision.** | (a) systemd on the host; (b) Docker Compose | (a) now (one VM, v1 already runs without Docker, quest-mf's amendment is zero-Docker); reconsider with a second VM | Phase 1 |
| **O-5** | **Chart library.** | (a) ECharts (shared with quest-mf); (b) keep Recharts | (a); Recharts for the pie only is acceptable | Phase 4 |
| **O-6** | **Client role.** Do clients get their own read-only login? | (a) yes at cutover; (b) later; (c) never | (b): the auth model supports it, so it costs nothing to defer | Phase 3 scope |
| **O-7** | **Charges source.** The tradebook has none. Import Console's P&L report? contract notes? | (a) Console P&L report per client; (b) contract-note PDFs; (c) rate-card estimate labelled as such | (a). The user must supply a sample report. Until then P&L is "before charges" (R15) | Phase 2.3 |
| **O-8** | **Policy constants.** Risk-free rate 6.5 %; XIRR suppressed under 365 days; per-data-class freshness limits. | confirm or change | keep; make them versioned settings | Phase 1 |
| **O-9** | **Repository.** | (a) same repo (`apps/`, `libs/`); (b) new repo | (a): shared history, ADR-0001 layout, v1 frozen alongside | Phase 1 |
| **O-10** | **Sharing with quest-mf.** Design tokens, `EChart` wrapper, LTTB, port registry. | (a) copy now; (b) extract a shared `packages/ui` | (a) now; extract only after both products are stable | Phase 4 |
| **O-11** | **Are Postgres/Redis on the host internet-reachable?** quest-mf's CHANGELOG says its dev machine connects to `140.245.194.172:5432/6379` directly. Its own rules forbid exposure. | verify, then close or restrict to an allow-list | do this **first**, before any new data lands there | Phase 0.2 |
| **O-12** | **Benchmark licensing.** quest-mf ADR-0009 chose index-fund proxies for anything published. Our app is private (managers/clients), so price indices from Yahoo may be acceptable. | (a) price indices, labelled; (b) index-fund proxies; (c) licensed TRI | (a) for now, labelled honestly; revisit before any wider distribution | Phase 2.6 |
| **O-13** | **Client-data protection.** Names, client codes and positions of 16 people sit in dumps and dev machines. India's DPDP Act may apply. | define an anonymisation step for dev data; decide who signs off | anonymise before development use; needs a person, not code | Phase 0.5 |
| **O-14** | **Feature parity scope.** Which v1 features must exist at cutover? (Kite accounts, PDF/OCR notes, LLM summary, alerts, sector research…) | mark each Must / Later / Drop | I will build the checklist in Phase 4; you mark it | Phase 4 |
| **O-15** | **Cutover window and downtime tolerance.** | Saturday, up to 4 h of read-only | confirm | Phase 6 |

## B. Facts I could not verify (I did not read production)

| # | Fact | How to verify | Why it matters |
|---|---|---|---|
| U-1 | VM shape and free disk | commands in O-1 | sizing, migration safety |
| U-2 | uvicorn worker count and pm2 configuration | `pm2 show portfolio-backend`, `pm2 env` | whether per-process caches are duplicated today |
| U-3 | nginx compression settings | read the site config | payload size in production |
| U-4 | Whether stored price history is split-adjusted | compare a known split (one held symbol) against as-traded closes | R17; determines the price backfill approach |
| U-5 | Backup state of the current Mongo | ask / inspect cron | no migration without a proven restore |
| U-6 | Which Postgres/Redis processes already run on the host and on which ports | `ss -tlnp` | port collisions (Deployment §1) |
| U-7 | **Angel concurrent-session behaviour** (Spike S-1) | a supervised test outside market hours | decides the worker process design (LLD-backend §7) |
| U-8 | Whether every held symbol is inside the ORB feed's ~2,690-symbol universe | compare held symbols to `orb_universe` | how many EOD closes need a provider at all |

## C. What I need from you to proceed to Phase 0

1. Approve the direction (or say what to change).
2. O-1 outputs (`lscpu`, `free -h`, `df -h`, `uname -m`) and U-2/U-3/U-6 if you are comfortable running the commands.
3. O-3 and O-5, since they change what users see.
4. A decision on shipping the v1 metric fixes (Phase 0.1), because they are uncommitted on `main`.
