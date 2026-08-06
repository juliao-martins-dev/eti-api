# eti-dashboard × eti-api — Integration Reference

Every endpoint the admin dashboard needs, with real request/response shapes,
read from the implemented code (`accounts/`, `attendance/`). This is the
contract for swapping `lib/mock-data.ts` out of `lib/store.ts`.

Base URL: `<API_HOST>/api/` — **every path ends with a trailing slash**.
Without it Django 301-redirects, the POST body is dropped, and the request
silently becomes a GET.

All dates are `YYYY-MM-DD`, all times `HH:MM:SS`, domain fields are Tetun.
JSON in and out everywhere below (the punch endpoints are multipart, but the
dashboard never calls those).

---

## 1. Authentication

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `auth/login/` | `{email, password}` | `{access, refresh, user}` — 401 on bad credentials |
| POST | `auth/refresh/` | `{refresh}` | `{access, refresh}` — **both new**; the old refresh is blacklisted |
| POST | `auth/logout/` | `{refresh}` (Bearer required) | 205 `{detail}` |
| POST | `auth/verify/` | `{token}` | 200 / 401 |
| GET | `auth/me/` | — | the profile (sidebar chip) |

`user` / `me` shape:

```json
{
  "id": 1, "numeru_id": 1, "email": "joao@eti-dili.tl",
  "naran_kompletu": "João Gaio", "kargu": "Diretor",
  "foto": "http://host/media/fotos/x.jpg",
  "role": "ADMIN", "role_display": "Administradór"
}
```

Rules the client must implement:

- Access token lives **15 min**, refresh **30 days** (idle timeout — each
  refresh returns a fresh pair). **Persist the new refresh token on every
  refresh** or the next one fails. Single-flight the refresh call; on 401
  refresh once, replay once, then force re-login (mirror
  `eti-mobile/lib/api.ts`).
- Admin-only routes below need an account with `is_staff=True` **or**
  `role="ADMIN"` — otherwise `403`.

## 2. Teacher roster — `/api/profesor/` (admin)

### `GET /api/profesor/`

Plain array (no pagination envelope), ordered by `naran_kompletu`,
**deactivated accounts included** — filter/badge client-side on `is_active`.
Only `role=PROFESSOR` accounts appear; admins are not listed.

```json
[{
  "id": 3, "numeru_id": 1015, "email": "ana@eti-dili.tl",
  "naran_kompletu": "Ana Paula Ximenes", "kargu": "Profesóra Matemátika",
  "foto": null, "role": "PROFESSOR", "role_display": "Professór",
  "sexu": "FETO", "nu_kontaktu": "+670 7810 3345", "is_active": true
}]
```

Use it to join `nu_kontaktu` into the Painel "seidauk marka" list and to fill
the teacher `<select>` on Prezensa/Relatóriu.

### `POST /api/profesor/`

```json
{ "numeru_id": 1015, "naran_kompletu": "Ana Paula Ximenes",
  "email": "ana@eti-dili.tl", "kargu": "Profesóra Matemátika",
  "nu_kontaktu": "+670 7810 3345", "sexu": "FETO" }
```

`numeru_id`, `naran_kompletu`, `email` required; the rest optional. Returns
**201** with the roster row **plus `password_inisial`** — shown exactly once,
unrecoverable afterwards (it is hashed at rest). Surface it in the modal with
a copy button before closing.

Errors: `400 {detail, code: "duplicate_numeru"}` or `"duplicate_email"` —
map onto the two existing toasts. Other validation errors arrive DRF-style
(`{field: [msg]}`).

### `PATCH /api/profesor/{id}/`

Any subset of the POST fields plus `is_active`. Deactivation is this soft
toggle — **there is no DELETE** (405), sheets reference the account. Returns
the updated roster row. Same duplicate codes as POST.

A deactivated teacher drops out of `ohin-hotu` and `hotu` results (both
filter `is_active=True`), so Painel counts shrink accordingly.

## 3. Today, whole school — `GET /api/prezensa/ohin-hotu/` (admin)

Feeds all three Painel sections in one call.

```json
{
  "data": "2026-08-05", "loron": "Quarta-feira",
  "rezumu": { "total": 57, "marka_ona": 40, "seidauk_marka": 17 },
  "profesor": [
    { "profesor": { "id": 6, "numeru_id": 6, "naran_kompletu": "Martinho Martins",
                    "kargu": "Chefe Dep. TLP", "foto": "http://..." },
      "marka_ona": true,
      "prezensa": {
        "id": 91, "data": "2026-08-05", "loron": "Quarta-feira",
        "oras_dader_tama": "08:03:00", "oras_dader_fila": null,
        "oras_lorokraik_tama": null, "oras_lorokraik_fila": null,
        "estadu": "PREZENTE", "estadu_display": "Prezente", "obs": "",
        "marka": [ { "kolumna": "ORAS_DADER_TAMA", "oras": "08:03:00",
                     "oras_orariu": "08:00:00", "atrazadu": true,
                     "foto": "http://host/media/prezensa/2026/08/x.jpg",
                     "latitude": "-8.552336", "longitude": "125.541603",
                     "distansia_metru": 12.4, "iha_eskola": true,
                     "sesaun": "DADER", "tipu": "TAMA",
                     "rejistu_iha": "2026-08-05T08:03:12+09:00" } ]
      } },
    { "profesor": { "...": "..." }, "marka_ona": false, "prezensa": null }
  ]
}
```

`prezensa: null` = has not punched today — that row is the "seidauk marka"
list. `profesor` here lacks `nu_kontaktu`; join it from the roster (§2).

## 4. Period grid — `GET /api/prezensa/hotu/` (admin)

The Prezensa grid and the Relatóriu source. One line per teacher per
**working day** (Sundays excluded), empty days included, teacher-major then
date-ascending.

Query parameters:

| Param | Meaning |
| --- | --- |
| `data=YYYY-MM-DD` | single day mode (response echoes `data` + `loron`) |
| `fulan=1..12&tinan=&semana=1..6?` | month / week mode, defaults to the current month (echoes `fulan`, `tinan`, `semana`) |
| `profesor=<id>` | narrow to one teacher |
| `marka=false` | omit nested punches (light grid load; fetch evidence per day via the full call) |

`data` and `fulan/tinan/semana` are mutually exclusive — `data` wins.

```json
{
  "fulan": 7, "tinan": 2026, "semana": null,
  "profesor": [
    { "profesor": { "id": 3, "...": "..." },
      "data": "2026-07-13",
      "prezensa": { "id": 91, "estadu": "LISENSA",
                     "obs": "Moras — atestadu médiku", "marka": [], "...": "..." },
      "marka_ona": false },
    { "profesor": { "...": "..." }, "data": "2026-07-14",
      "prezensa": null, "marka_ona": false }
  ]
}
```

Note the top-level `data` on every line — an empty day has `prezensa: null`,
so the date cannot live inside it. Count `loron servisu` from the rows
received; a full month for the whole school is ~1 500 lines.

Errors: `400 {code: "invalid_period"}` (bad date/fulan/tinan/semana),
`400 {code: "invalid_profesor"}` (non-numeric `profesor`).

Both `hotu` and `ohin-hotu` list **teachers and admins** (`role` PROFESSOR or
ADMIN, active only) — the director keeps a sheet like everyone else. Students
never appear.

### 4.1 One teacher, paper-sheet layout — `GET /api/prezensa/istoria/?profesor=<id>`

For a per-teacher view shaped exactly like the printed book (header
Naran/Kargu, one row per working day with the four time columns, week
numbers, monthly rezumu), admins may pass `?profesor=<id>` to `istoria/`:

```
GET /api/prezensa/istoria/?fulan=7&tinan=2026&profesor=6
```

Response: `{profesor, kargu, fulan, fulan_display, tinan, semana,
rezumu{loron_servisu, marka_ona, seidauk_marka, marka_total, atrazadu},
loron[]}` — each `loron[]` row carries `data`, `loron` (weekday), `semana`,
`sabadu`, the four `oras_*` columns, `estadu`, `obs` and nested `marka`.
Without the param it returns the caller's own sheet; a non-admin passing it
gets `403`; unknown id → `400 {code: "invalid_profesor"}`.

## 5. Hand-written days — `/api/prezensa/estadu/` (admin)

### `POST` — register LISENSA / MISAUN / FERIADU / FALTA over a range

```json
{ "profesor": 3, "estadu": "LISENSA",
  "husi": "2026-08-05", "too": "2026-08-07",
  "obs": "Moras — atestadu médiku" }
```

Server behaviour (do **not** re-implement client-side): skips Sundays,
creates the monthly sheet/day rows if absent, overwrites `estadu`/`obs` of
the days in range. `PREZENTE` is not accepted — it can only come from a punch.

**201**:

```json
{ "detail": "Estadu rejistu ho susesu.", "profesor": 3, "estadu": "LISENSA",
  "husi": "2026-08-05", "too": "2026-08-07",
  "loron": ["2026-08-05", "2026-08-06", "2026-08-07"], "total": 3 }
```

Errors:

- `400 {code: "invalid_period"}` — `husi > too`, or range longer than a year.
- `400 {code: "invalid_profesor"}` — unknown teacher id.
- `400 {code: "iha_marka", loron: ["2026-08-06"]}` — **any day in the range
  already holds punches; nothing was written** (atomic). Show the conflicting
  dates; punches are evidence and cannot be buried under a leave.

### `DELETE` — return a day to "no record"

Body: `{"profesor": 3, "data": "2026-08-05"}` → **204**, the day row is gone.

- `404` — no row for that teacher/day.
- `400 {code: "iha_marka"}` — the day holds punches, or its estadu is
  PREZENTE. Only hand-written days can be removed.

## 6. System info — `GET /api/konfig/` (any authenticated user)

For the Konfig panel — values now really come from the server.

```json
{
  "oras_dader_tama": "08:00:00", "oras_dader_fila": "12:00:00",
  "oras_lorokraik_tama": "13:30:00", "oras_lorokraik_fila": "17:30:00",
  "limite_sesaun": "13:00:00",
  "eskola_raiu_metru": 100.0, "eskola_obriga_fatin": true
}
```

Read-only; the school's coordinates are deliberately never included.

## 7. Evidence photos

`marka.foto` and profile `foto` are absolute URLs — render them directly.
**Caveat:** `/media/` is served by Django only while `DEBUG=True`
(`core/urls.py`); in production the web server must serve `MEDIA_ROOT` or
every photo 404s. Flag this at deploy time.

## 8. Error handling summary

Errors are `400/403/404` with `{detail, code?, ...extra}`:

| code | Where | Dashboard reaction |
| --- | --- | --- |
| `duplicate_numeru` / `duplicate_email` | roster POST/PATCH | field toast |
| `invalid_period` | `hotu`, `estadu` POST | fix pickers |
| `invalid_profesor` | `hotu`, `estadu` POST | shouldn't happen from UI |
| `iha_marka` | `estadu` POST/DELETE | show conflicting `loron`, offer to view the day |
| `token_not_valid` | refresh/logout | refresh → re-login |
| — (`403`) | any admin route | account lacks `EhAdmin`; send to login or hide UI |

`detail` messages are Tetun and user-displayable as-is.

## 9. Endpoints that exist but the dashboard does not call

`POST /api/prezensa/checkin|checkout/` (mobile punches, multipart),
`GET /api/prezensa/ohin/` and `istoria/` (self-scoped),
`GET /api/lista-prezensa/` (self-scoped sheets),
`PATCH /api/auth/me/` (own photo only). Listed so nobody goes looking for an
admin variant that doesn't exist — punch times are deliberately read-only,
and there is no CSV endpoint (Relatóriu exports client-side from §4 rows).

## 10. Not implemented (yet)

- **Password reset** — `password_inisial` at creation is the only issuance;
  if an admin loses it there is no recovery endpoint.
- **E-mail delivery** of initial passwords (R3's original wording) — adjust
  the modal hint to "hand the password over" until it exists.
- Pagination — nothing paginates; every list is a plain array.
