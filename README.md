# ETI PREZENSA — Attendance API for Escola Técnica de Informática Dili

A REST backend that replaces a paper attendance book with a phone, a photo and
a GPS fix.

Every teacher at **ETI-Dili** (Timor-Leste) used to sign a monthly sheet —
*"LISTA PREZENSA BA PROFESÓR/A ETI DILI"* — four times a day: in and out in the
morning, in and out in the afternoon, a handwritten signature next to each time.
This project keeps that exact structure and replaces the two things paper could
not verify: **the time is stamped by the server**, and **the signature becomes a
selfie plus the coordinates the phone was standing at.**

Three pieces talk to one API:

![System flow — mobile and dashboard clients over JWT to the Django REST API, PostgreSQL and MEDIA_ROOT](docs/flow.png)

| | | |
| --- | --- | --- |
| **`eti-api`** | this repository | Django + DRF + SimpleJWT · PostgreSQL · the single source of truth |
| **`eti-mobile`** | teacher's phone | Expo / React Native — clock in/out with camera + GPS, own history, profile |
| **`eti-dashboard`** | admin's browser | Next.js — daily panel, attendance grid, roster, leave registry, reports |

---

## What the backend actually does

It is not a CRUD wrapper. The rules of the paper book live in the API, so no
client can disagree with another:

- **Four slots a day**, exactly as printed: `ORAS_DADER_TAMA` 08:00 ·
  `ORAS_DADER_FILA` 12:00 · `ORAS_LOROKRAIK_TAMA` 13:30 ·
  `ORAS_LOROKRAIK_FILA` 17:30. The server picks the slot from its own clock
  (cut-off 13:00) — the app never chooses.
- **A punch carries evidence.** Photo required, coordinates required. The time
  comes from the server; the client cannot send one.
- **You must be at the school.** Distance is a haversine computed in-process
  (no Maps API, no PostGIS); a punch beyond `ESKOLA_RAIU_METRU` (100 m) is
  refused with the measured distance in the error, so the teacher is told *how
  far off* they are. One env flag turns enforcement off without a deploy.
- **Rules that cannot be bypassed:** no second punch in the same session, no
  checkout before checkin, no Saturday afternoon (the sheet has none), and a
  database constraint behind each so it holds even under a race.
- **Sundays are not working days**, anywhere — reports, grids and history all
  skip them, because the printed sheet does.
- **The monthly sheet opens itself.** The first punch of a month creates the
  sheet and the day row; there is no "start the month" step.
- **Absences are first-class.** Every report returns *every* working day,
  including the ones nobody marked — the gaps are the reason to look.
- **Punch times are read-only forever.** No endpoint edits a recorded time.
  A correction is an administrator writing LEAVE/MISSION/HOLIDAY over a range,
  and even that is refused if the day already holds punches: evidence is never
  buried.

**100 automated tests** cover the above.

---

## Tech stack

| | |
| --- | --- |
| Python | 3.14 |
| Django | 6.0.7 |
| Django REST Framework | 3.17.1 |
| djangorestframework-simplejwt | 5.5.1 (rotation + blacklist) |
| PostgreSQL | via `psycopg` 3.3.4 |
| Pillow | 12.3.0 (photo validation) |
| django-environ | 0.14.0 |

No Celery, no Redis, no queue, no scheduler. Every write happens inside the
request that caused it, so this deploys as one WSGI process next to a database.

---

## REST API

Base `<host>/api/` · **every path ends with a trailing slash** (without it
Django 301-redirects and a POST body is dropped) · JSON in and out, except the
two punch endpoints, which are `multipart/form-data`.

Auth is `Authorization: Bearer <access>` on everything except login/refresh/verify.
`EhAdmin` = the account has `is_staff` **or** `role="ADMIN"`.

### Authentication

| Method | Path | Purpose | Auth |
| --- | --- | --- | --- |
| POST | `auth/login/` | email + password → `access`, `refresh` **and the profile** in one response | — |
| POST | `auth/refresh/` | rotate: returns a **new pair**, blacklists the old refresh | — |
| POST | `auth/verify/` | is this token still valid | — |
| POST | `auth/logout/` | blacklist the refresh token | Bearer |
| GET | `auth/me/` | own profile | Bearer |
| PATCH | `auth/me/` | replace own photo (multipart, `foto` only) | Bearer |

### Attendance — the teacher's own record

| Method | Path | Purpose | Auth |
| --- | --- | --- | --- |
| POST | `prezensa/checkin/` | arrival punch — `foto`, `latitude`, `longitude`, `presizaun?`, `sesaun?` | Bearer |
| POST | `prezensa/checkout/` | departure punch, same payload | Bearer |
| GET | `prezensa/ohin/` | today + the state of the two buttons (`bele_checkin` / `bele_checkout`) | Bearer |
| GET | `prezensa/istoria/` | one month or week, laid out like the paper sheet, with a summary | Bearer |
| GET | `prezensa/` · `prezensa/{id}/` | own day rows | Bearer |
| GET | `lista-prezensa/` · `{id}/` | own monthly sheets | Bearer |

### Administration

| Method | Path | Purpose | Auth |
| --- | --- | --- | --- |
| GET | `prezensa/ohin-hotu/` | today for the whole school, **including who has not punched** | EhAdmin |
| GET | `prezensa/hotu/` | any period × any or all staff; `?data=` or `?fulan&tinan&semana`, `?profesor=`, `?marka=false` | EhAdmin |
| GET | `prezensa/istoria/?profesor=<id>` | one teacher's sheet, paper layout | EhAdmin |
| POST | `prezensa/status/` | write LEAVE / MISSION / HOLIDAY / ABSENT over a date range | EhAdmin |
| DELETE | `prezensa/status/` | return a hand-written day to "no record" | EhAdmin |
| GET | `profesor/` | roster — teachers **and** admins, deactivated included | EhAdmin |
| POST | `profesor/` | create an account → `password_inisial`, shown once | EhAdmin |
| PATCH | `profesor/{id}/` | update, or soft-deactivate with `{is_active: false}` | EhAdmin |
| DELETE | `profesor/{id}/` | **irreversible** — the account and all its history; needs the caller's password | EhAdmin |
| POST | `profesor/{id}/reset-password/` | admin sets a new password (two matching fields) and revokes that teacher's sessions | EhAdmin |
| GET | `konfig/` | schedule + geofence settings (never the coordinates) | Bearer |

### Errors

Always `{"detail": "<Tetun, displayable as-is>", "code": "...", ...extra}`:

| code | Meaning |
| --- | --- |
| `duplicate` | already punched this session (carries `oras`) |
| `no_checkin` | checkout before checkin |
| `no_session` | Saturday afternoon does not exist |
| `dook_husi_eskola` | outside the geofence — carries `distansia` in metres |
| `iha_marka` | the day already holds punches; nothing was written |
| `invalid_period` · `invalid_profesor` | bad query or unknown teacher |
| `duplicate_numeru` · `duplicate_email` | the column is taken |
| `password_presiza` · `password_sala` | the caller's password is missing or wrong |
| `password_la_hanesan` · `password_fraku` | the two fields differ, or Django's validators refused it |
| `rasik` · `eh_admin` | the target is you, or an admin |
| `token_not_valid` | expired or blacklisted token |

> **Clients: treat `duplicate` as success.** The punch *was* recorded; if the
> response was lost, a naive retry otherwise shows a teacher a failure for
> attendance that is safely stored.

### Authentication model

Access token **15 minutes**, refresh **30 days**, `ROTATE_REFRESH_TOKENS` on —
so each refresh returns a new refresh token and blacklists the one it replaced.
That makes the 30 days an **idle timeout**, not a re-login deadline: a teacher
who punches on any weekday never logs in again.

Clients must **persist the new refresh token on every refresh**, single-flight
the call, retry once on `401`, then send the user back to login. Both clients do.

---

## Data model

Four tables, one chain:

```
User ──< ListaPrezensa ──< Prezensa ──< Marka
teacher    monthly sheet     one day      one punch (photo + GPS)
```

`Prezensa` deliberately stores **no times** — the four printed columns are
rebuilt from the `Marka` rows, so a punch and the grid can never disagree.
Full ER diagram and per-field notes: **[docs/schema-overview.html](docs/schema-overview.html)**
(open it in a browser).

---

## Getting started

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill it in — see the table below
python manage.py migrate
python manage.py createsuperuser      # prompts email, numeru_id, naran_kompletu
python manage.py runserver 0.0.0.0:8000   # 0.0.0.0 so a phone on the LAN can reach it
python manage.py test --noinput           # 100 tests
```

`.env` keys (**names only — never commit values**):

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Django basics |
| `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL |
| `ESKOLA_LATITUDE`, `ESKOLA_LONGITUDE` | the school's position — the geofence centre |
| `ESKOLA_RAIU_METRU` | radius in metres (default 100) |
| `ESKOLA_OBRIGA_FATIN` | `False` accepts punches from anywhere (testing only) |

**Before production:** `DEBUG=False`, a real `SECRET_KEY` and `ALLOWED_HOSTS`,
TLS, `ESKOLA_OBRIGA_FATIN=True`, the web server serving `MEDIA_ROOT` (the
`/media/` route is DEBUG-only, so photos 404 without it), and
`manage.py flushexpiredtokens` on a weekly schedule.

---

## Repository layout

```
eti-api/
├─ accounts/      identity: custom User (email login), roster, JWT views, EhAdmin
├─ attendance/    the book: ListaPrezensa · Prezensa · Marka, punch rules, geofence, reports
├─ core/          settings, URLconf, WSGI/ASGI
└─ docs/          the documents below
```

Sibling repositories: **`eti-mobile`** (Expo app) and **`eti-dashboard`**
(Next.js admin).

## Documentation

| File | What it is |
| --- | --- |
| [docs/plan.md](docs/plan.md) | full project context — stack, schema, every endpoint, conventions, known issues |
| [docs/integrate-api.md](docs/integrate-api.md) | the client contract: real request/response bodies, error handling, what *not* to build |
| [docs/schema-overview.html](docs/schema-overview.html) | ER diagram + a card per model, opens in a browser |
| [docs/sql-query.md](docs/sql-query.md) | copy-paste SQL reproducing each dashboard screen (pgAdmin) |
| [docs/plan-delete-profesor.md](docs/plan-delete-profesor.md) · [docs/plan-reset-password.md](docs/plan-reset-password.md) | feature design notes |

---

## A note on the language

Field names are **Tetun**, not English, because the domain is: `prezensa`
attendance · `marka` punch · `naran kompletu` full name · `kargu` position ·
`foto` photo · `oras` time · `loron` day · `fulan` month · `tinan` year ·
`semana` week · `dader` morning · `lorokraik` afternoon · `tama` in ·
`fila` out · `atrazadu` late · `iha eskola` at school · `rezumu` summary ·
`seidauk` not yet · `hotu` all · `ohin` today · `istoria` history.

Stored `status` values are English (`PRESENT`, `ABSENT`, `LEAVE`, `MISSION`,
`HOLIDAY`) so the API contract reads unambiguously; every response also carries
`status_display` with the Tetun label the user should see.
