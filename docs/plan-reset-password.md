# Plan — ADMIN accounts in the roster + admin-driven password reset

Two changes, backend first, then `eti-dashboard`.

---

## A. Show ADMIN accounts in `/api/profesor/`

Today `ProfesorViewSet.get_queryset()` filters `role=PROFESSOR`, so the
director never appears in the roster — while `ohin-hotu`, `hotu` and
`istoria?profesor=` already cover `PROFESSOR + ADMIN`
(`attendance/views.py::profesores_relatoriu`). The roster is the odd one out.

**Change:** `role__in=[PROFESSOR, ADMIN]`, ordered by `naran_kompletu`.
`role` and `role_display` are already in `ProfesorRosterSerializer`, so the
payload does not change shape — the dashboard just gets more rows and can badge
them.

### The consequence that must be handled

`DELETE /api/profesor/{id}/` currently 404s on an admin **only because the
queryset hid them**. Once admins are visible, that protection disappears and
one admin could delete another — taking the school's whole attendance history
with them. So the delete guard becomes explicit:

| Target | Before | After |
| --- | --- | --- |
| ADMIN / `is_staff` | `404` (hidden by queryset) | `403 {code: "eh_admin"}` |
| Yourself | `403 rasik` | unchanged |

Same rule for the new reset endpoint: an admin's password is not resettable
from the roster.

---

## B. `POST /api/profesor/{id}/reset-password/`

A teacher who forgets their password has no self-service path — there is no
e-mail delivery and no reset link. They contact the admin, who sets a new
password from the dashboard and hands it over.

### Contract

| | |
| --- | --- |
| Route | `POST /api/profesor/{id}/reset-password/` |
| Auth | `IsAuthenticated` + `EhAdmin` |
| Body | `{ "password_foun": "...", "password_konfirma": "..." }` |

Both fields are required and **must be identical** — that is the "two fields
exactly the same" rule, enforced on the server as well as in the form.

| Code | Body | When |
| --- | --- | --- |
| `200` | `{detail, profesor: {...}}` | Password changed |
| `400` | `{detail, code: "password_la_hanesan"}` | The two fields differ |
| `400` | `{detail, code: "password_fraku", erros: [...]}` | Fails Django's `AUTH_PASSWORD_VALIDATORS` (too short, too common, all numeric, too similar to the email/name) |
| `403` | `{detail, code: "eh_admin"}` | Target is an ADMIN — not resettable here |
| `403` | `{detail, code: "rasik"}` | Target is the caller |
| `404` | — | No such account |

### Behaviour

1. `alvo.set_password(...)` + save — Django hashes it; the plain text is never
   stored and never returned. The admin already has it: they typed it.
2. **Every existing session for that teacher is revoked** — all their
   outstanding refresh tokens are blacklisted. Otherwise a phone that was
   already logged in keeps working after a reset, which defeats the point when
   the reset is because the account was compromised.
3. An audit line: actor, target, and how many sessions were revoked.

### Why no admin-password confirmation here

`DELETE` asks for the admin's own password because it is irreversible. A reset
is recoverable — the admin can simply set another one — so the friction would
buy nothing. The two matching fields are what this operation needs.

### Files

| File | Change |
| --- | --- |
| `accounts/serializers.py` | `ProfesorResetPasswordSerializer` (two fields + match check) |
| `accounts/views.py` | queryset widened; `eh_admin` guard in `destroy()`; `reset_password` action |
| `accounts/tests.py` | roster now lists admins; delete-admin is 403; reset cases |

No migration.

---

## C. Dashboard — `eti-dashboard/`

**Roster table:** admins now appear. Badge them next to the name
(`role_display` → "Administradór") so the list is not confusing, and hide both
destructive buttons on those rows.

**Edit modal → new "Reset password" button** (neutral, next to "Dezativa
konta"), opening a modal with:

- Tetun explanation: *"Profesór ne'ebé lakon password presiza kontaktu admin.
  Hatama password foun, depois entrega ba nia."*
- Two password fields: `Password foun` / `Konfirma password foun`
- The confirm button stays disabled until both are non-empty and identical;
  mismatch shows *"Password la hanesan"*
- On `200`: show the password once with a copy button — the same hand-over card
  the create flow already uses — because the teacher has to be told what it is.

**Files:** `lib/store.ts` (`resetPasswordProfesor`), `lib/types.ts`,
`app/(dashboard)/profesor/page.tsx`.

---

## D. Docs to update

`docs/plan.md` (§6 endpoints, §10 issues), root `plan.md` (API contract table),
`docs/integrate-api.md` (§2 roster: admins now listed, new reset section, error
table).
