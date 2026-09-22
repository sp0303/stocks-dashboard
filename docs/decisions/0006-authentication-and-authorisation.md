# 0006. Authentication and Authorisation Model

* **Status**: Proposed (awaiting approval)
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `quest-mf` HLD §8 and LLD-backend §3.6, §4.1; `backend/app/routers/auth.py`, `services/auth.py`

---

## 1. Context and Problem Statement

v1 compares a **plaintext `ADMIN_PASSWORD` from the environment** for the super-admin (the local default is the literal string `admin`), signs stateless HMAC tokens valid for **14 days**, stores access tokens in `localStorage`, and has no refresh, revocation or audit trail. Manager passwords are hashed. The audit also found CORS set to `*` in the old deploy workflow.

## 2. Decision

1. **Super-admin is a user row**, not an environment secret. There is no shared password.
2. **argon2id** for every password. Rate-limit login to 5/min per IP and per email; lock out and audit.
3. **RS256 access token, 15 minutes**, claims `sub`, `role`, `mid` or `cid`. A **rotating refresh token** in an `httpOnly; Secure; SameSite=Strict` cookie (7 days) with server-side revocation. The access token is held **in memory only**; nothing sensitive in `localStorage`.
4. **Roles:** `super_admin`, `manager`, `client` (read-only, own record).
5. **Authorisation in the service layer, before any cache read** (LLD-cache §1.3). A manager can reach only their own clients; every access decision is testable.
6. **Audit log** for logins, uploads, deletes, manual trades and admin actions.
7. **Explicit CORS allow-list**, HSTS, CSP.

## 3. Consequences

**Positive:** no shared secret to leak or rotate by hand; short-lived tokens; per-user accountability; a client-role login becomes possible without new machinery.
**Negative / cost:** users must be created and their passwords set at cutover (a one-time migration of manager hashes plus a super-admin bootstrap); refresh-cookie handling in the SPA (single-flight refresh on `401`).
**Rejected:** keeping the shared admin password; long-lived HMAC tokens; a third-party identity provider (out of proportion for the user count; revisit if clients are onboarded at scale).
