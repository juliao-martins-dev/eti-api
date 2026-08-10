# SQL Queries — ETI PREZENSA (PostgreSQL / pgAdmin)

Copy-paste queries that reproduce **exactly what each Web Dashboard screen
shows**. Read from the live schema, so column names and values are the real
ones. Every query is plain SQL — no Django needed.

Replace the values in `-- 🔧` lines and run.

---

## 0. Schema map

```
accounts_user ──< attendance_listaprezensa ──< attendance_prezensa ──< attendance_marka
   (teacher)          (one sheet per month)        (one row per day)      (one punch)
```

| Table | Key columns |
| --- | --- |
| `accounts_user` | `id`, `numeru_id` (UNIQUE), `email` (UNIQUE), `naran_kompletu`, `role`, `sexu`, `kargu`, `nu_kontaktu`, `foto`, `is_active`, `is_staff`, `password` |
| `attendance_listaprezensa` | `id`, `profesor_id` → user, `kargu`, `fulan` (1–12), `tinan`, UNIQUE `(profesor_id, fulan, tinan)` |
| `attendance_prezensa` | `id`, `lista_id` → sheet, `data` (date), `status`, `obs`, UNIQUE `(lista_id, data)` |
| `attendance_marka` | `id`, `prezensa_id` → day, `sesaun`, `tipu`, `oras`, `foto`, `latitude`, `longitude`, `presizaun`, `distansia_metru`, `iha_eskola`, `rejistu_iha`, UNIQUE `(prezensa_id, sesaun, tipu)` |

**Values**

| Column | Allowed | Tetun label shown in the UI |
| --- | --- | --- |
| `role` | `ADMIN`, `PROFESSOR` | Administradór / Professór |
| `status` | `PRESENT`, `ABSENT`, `LEAVE`, `MISSION`, `HOLIDAY` | Prezente / Falta / Lisensa / Misaun / Feriadu |
| `sesaun` | `DADER`, `LOROKRAIK` | dader = morning, lorokraik = afternoon |
| `tipu` | `TAMA`, `FILA` | tama = in, fila = out |
| `sexu` | `MANE`, `FETO` | |

**Scheduled times** (a `TAMA` punch after its time is *atrazadu*):
`DADER TAMA 08:00` · `DADER FILA 12:00` · `LOROKRAIK TAMA 13:30` · `LOROKRAIK FILA 17:30`

**Two rules every dashboard screen follows**

1. **Sunday is not a working day** — `EXTRACT(ISODOW FROM d) <> 7`.
2. **Reports include teachers *and* admins** (the director keeps a sheet too):
   `role IN ('PROFESSOR','ADMIN') AND is_active`.
   The **Profesór sira** roster screen is the exception: `role = 'PROFESSOR'` only.

`id` columns are identity columns — omit `id` on INSERT and Postgres assigns it.

---

## 1. Screen: Profesór sira

### 1.1 The table (PROFESÓR · NU. ID · KARGU · KONTAKTU · ESTADU KONTA)

```sql
SELECT
    u.id,
    u.naran_kompletu                        AS "PROFESÓR",
    u.email                                 AS "EMAIL",
    u.numeru_id                             AS "NU. ID",
    COALESCE(NULLIF(u.kargu, ''), '—')      AS "KARGU",
    COALESCE(NULLIF(u.nu_kontaktu, ''), '—') AS "KONTAKTU",
    CASE WHEN u.is_active THEN 'Ativu' ELSE 'Dezativadu' END AS "ESTADU KONTA"
FROM accounts_user u
WHERE u.role = 'PROFESSOR'          -- the roster lists teachers only
ORDER BY u.naran_kompletu;
```

### 1.2 The search box ("Buka naran, email, kargu…")

```sql
-- 🔧 what you typed in the search box
\set buka '\'%soares%\''

SELECT
    u.naran_kompletu, u.email, u.numeru_id, u.kargu, u.nu_kontaktu,
    CASE WHEN u.is_active THEN 'Ativu' ELSE 'Dezativadu' END AS estadu_konta
FROM accounts_user u
WHERE u.role = 'PROFESSOR'
  AND (
        u.naran_kompletu ILIKE '%soares%'   -- 🔧
     OR u.email          ILIKE '%soares%'   -- 🔧
     OR u.kargu          ILIKE '%soares%'   -- 🔧
  )
ORDER BY u.naran_kompletu;
```

### 1.3 INSERT — modal "Aumenta Profesór"

> ⚠️ **Password.** Django stores a *hash*, never plain text. The value below is
> an **unusable** password: the account exists and shows in the dashboard, but
> **nobody can log in with it**. To give the teacher a working password, either
> create them through the dashboard (which returns `password_inisial`), or run
> afterwards:
> `python manage.py shell -c "from accounts.models import User; u=User.objects.get(email='...'); u.set_password('SenhaFoun123'); u.save()"`

```sql
INSERT INTO accounts_user (
    password, is_superuser, first_name, last_name, is_staff, is_active,
    date_joined, email, naran_kompletu, role, sexu, kargu,
    habilitasaun_literaria, disiplina_hanorin, nu_kontaktu, foto,
    nivel_edukasaun, area_estudu, numeru_id
) VALUES (
    '!',                       -- unusable password (see warning above)
    FALSE, '', '', FALSE, TRUE,
    NOW(),
    'marcelina@eti.tl',        -- 🔧 Email (uza atu login)
    'Marcelina da Silva',      -- 🔧 Naran kompletu
    'PROFESSOR',
    'FETO',                    -- 🔧 Sexu: MANE | FETO
    'Profesóra Kímika',        -- 🔧 Kargu
    '', '',
    '+670 7712 3456',          -- 🔧 Nu. kontaktu
    NULL, '', '',
    1071                       -- 🔧 Numeru ID (must be unique)
)
RETURNING id, numeru_id, naran_kompletu, email, kargu, is_active;
```

Check before inserting, so you get a clear answer instead of a constraint error
(the dashboard shows these as `duplicate_numeru` / `duplicate_email`):

```sql
SELECT numeru_id, email, naran_kompletu
FROM accounts_user
WHERE numeru_id = 1071            -- 🔧
   OR email = 'marcelina@eti.tl'; -- 🔧
```

### 1.4 UPDATE — modal "Rai mudansa"

```sql
UPDATE accounts_user
SET naran_kompletu = 'Elyzio Soares',           -- 🔧
    numeru_id      = 112,                       -- 🔧
    sexu           = 'MANE',                    -- 🔧
    email          = 'elyzio.soares@eti.tl',    -- 🔧
    kargu          = 'Professor Matematica',    -- 🔧
    nu_kontaktu    = '+670 7811 8019'           -- 🔧
WHERE id = 1                                    -- 🔧 teacher id
RETURNING id, naran_kompletu, numeru_id, email, kargu, nu_kontaktu, is_active;
```

### 1.5 Deactivate / reactivate an account

The dashboard **never deletes** a teacher — sheets reference the account.
"Dezativa konta" is a soft flag.

```sql
-- Dezativa konta
UPDATE accounts_user SET is_active = FALSE
WHERE id = 1                                    -- 🔧
RETURNING id, naran_kompletu, is_active;

-- Ativa fila fali
UPDATE accounts_user SET is_active = TRUE
WHERE id = 1                                    -- 🔧
RETURNING id, naran_kompletu, is_active;

-- By numeru_id or email instead
UPDATE accounts_user SET is_active = FALSE WHERE numeru_id = 112;          -- 🔧
UPDATE accounts_user SET is_active = FALSE WHERE email = 'x@eti.tl';       -- 🔧

-- Everyone currently deactivated
SELECT numeru_id, naran_kompletu, email, kargu
FROM accounts_user
WHERE role = 'PROFESSOR' AND is_active = FALSE
ORDER BY naran_kompletu;
```

### 1.6 DELETE — only when you really mean it

```sql
-- See what would be destroyed first: deleting a user CASCADES to their
-- sheets, days and punches (the photos on disk are NOT removed).
SELECT
    (SELECT count(*) FROM attendance_listaprezensa l WHERE l.profesor_id = u.id) AS lista,
    (SELECT count(*) FROM attendance_prezensa p
       JOIN attendance_listaprezensa l ON l.id = p.lista_id
      WHERE l.profesor_id = u.id) AS loron,
    (SELECT count(*) FROM attendance_marka m
       JOIN attendance_prezensa p ON p.id = m.prezensa_id
       JOIN attendance_listaprezensa l ON l.id = p.lista_id
      WHERE l.profesor_id = u.id) AS marka
FROM accounts_user u
WHERE u.id = 1;                                 -- 🔧

-- Prefer 1.5 (deactivate). This is irreversible.
-- The dashboard now does the same thing through
-- DELETE /api/profesor/{id}/ with the admin's password, which also removes
-- the photo files this statement leaves behind on disk.
DELETE FROM accounts_user WHERE id = 1;         -- 🔧
```

---

## 2. Screen: Prezensa (the grid)

The grid shows **one row per teacher per working day**, including days with no
record (`—`). That is why every query below starts from a generated calendar
and `LEFT JOIN`s the data in — an `INNER JOIN` would silently hide exactly the
absences the screen exists to show.

### 2.1 Mode "Loron" — one day, all teachers

```sql
-- 🔧 the date in the picker
WITH parametru AS (SELECT DATE '2026-08-07' AS loron)
SELECT
    to_char(p9.loron, 'DD') || ' ' ||
      CASE EXTRACT(MONTH FROM p9.loron)
        WHEN 1 THEN 'Janeiru'  WHEN 2 THEN 'Fevereiru' WHEN 3 THEN 'Marsu'
        WHEN 4 THEN 'Abril'    WHEN 5 THEN 'Maiu'      WHEN 6 THEN 'Juñu'
        WHEN 7 THEN 'Jullu'    WHEN 8 THEN 'Agostu'    WHEN 9 THEN 'Setembru'
        WHEN 10 THEN 'Outubru' WHEN 11 THEN 'Novembru' ELSE 'Dezembru'
      END                                                   AS "DATA",
    CASE EXTRACT(ISODOW FROM p9.loron)
        WHEN 1 THEN 'Segunda' WHEN 2 THEN 'Tersa' WHEN 3 THEN 'Kuarta'
        WHEN 4 THEN 'Kinta'   WHEN 5 THEN 'Sesta' WHEN 6 THEN 'Sábadu'
        ELSE 'Domingu' END                                  AS "LORON",
    u.naran_kompletu                                        AS "PROFESÓR",
    COALESCE(NULLIF(u.kargu, ''), '')                       AS "KARGU",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='DADER'     AND m.tipu='TAMA'), 'HH24:MI'), '—') AS "DADER TAMA",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='DADER'     AND m.tipu='FILA'), 'HH24:MI'), '—') AS "DADER FILA",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='LOROKRAIK' AND m.tipu='TAMA'), 'HH24:MI'), '—') AS "LOROKRAIK TAMA",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='LOROKRAIK' AND m.tipu='FILA'), 'HH24:MI'), '—') AS "LOROKRAIK FILA",
    CASE p.status
        WHEN 'PRESENT' THEN 'Prezente' WHEN 'ABSENT'  THEN 'Falta'
        WHEN 'LEAVE'   THEN 'Lisensa'  WHEN 'MISSION' THEN 'Misaun'
        WHEN 'HOLIDAY' THEN 'Feriadu'  ELSE '—' END         AS "ESTADU",
    -- the orange dot in the UI: an arrival later than its scheduled time
    COALESCE(bool_or(m.oras > TIME '08:00') FILTER (WHERE m.sesaun='DADER'     AND m.tipu='TAMA'), FALSE) AS atrazadu_dader,
    COALESCE(bool_or(m.oras > TIME '13:30') FILTER (WHERE m.sesaun='LOROKRAIK' AND m.tipu='TAMA'), FALSE) AS atrazadu_lorokraik,
    COALESCE(p.obs, '')                                     AS "OBS"
FROM parametru p9
CROSS JOIN accounts_user u
LEFT JOIN attendance_listaprezensa l
       ON l.profesor_id = u.id
      AND l.fulan = EXTRACT(MONTH FROM p9.loron)
      AND l.tinan = EXTRACT(YEAR  FROM p9.loron)
LEFT JOIN attendance_prezensa p
       ON p.lista_id = l.id AND p.data = p9.loron
LEFT JOIN attendance_marka m
       ON m.prezensa_id = p.id
WHERE u.role IN ('PROFESSOR','ADMIN') AND u.is_active
GROUP BY p9.loron, u.id, u.naran_kompletu, u.kargu, p.status, p.obs
ORDER BY u.naran_kompletu;
```

### 2.2 Mode "Fulan" — a whole month (every working day, Sundays skipped)

```sql
-- 🔧 month and year from the pickers
WITH parametru AS (SELECT 8 AS fulan, 2026 AS tinan),
loron AS (
    SELECT d::date AS data
    FROM parametru,
         generate_series(
             make_date(tinan, fulan, 1),
             (make_date(tinan, fulan, 1) + INTERVAL '1 month - 1 day')::date,
             INTERVAL '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) <> 7        -- Sunday is not a working day
),
profesor AS (
    SELECT id, naran_kompletu, kargu
    FROM accounts_user
    WHERE role IN ('PROFESSOR','ADMIN') AND is_active
    -- 🔧 for ONE teacher, uncomment:  AND id = 1
)
SELECT
    -- "01 Agostu", not to_char's English "01 Aug"
    to_char(loron.data, 'DD') || ' ' ||
      CASE EXTRACT(MONTH FROM loron.data)
        WHEN 1 THEN 'Janeiru'  WHEN 2 THEN 'Fevereiru' WHEN 3 THEN 'Marsu'
        WHEN 4 THEN 'Abril'    WHEN 5 THEN 'Maiu'      WHEN 6 THEN 'Juñu'
        WHEN 7 THEN 'Jullu'    WHEN 8 THEN 'Agostu'    WHEN 9 THEN 'Setembru'
        WHEN 10 THEN 'Outubru' WHEN 11 THEN 'Novembru' ELSE 'Dezembru'
      END                                                   AS "DATA",
    CASE EXTRACT(ISODOW FROM loron.data)
        WHEN 1 THEN 'Segunda' WHEN 2 THEN 'Tersa' WHEN 3 THEN 'Kuarta'
        WHEN 4 THEN 'Kinta'   WHEN 5 THEN 'Sesta' ELSE 'Sábadu' END AS "LORON",
    profesor.naran_kompletu                                 AS "PROFESÓR",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='DADER'     AND m.tipu='TAMA'), 'HH24:MI'), '—') AS "DADER TAMA",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='DADER'     AND m.tipu='FILA'), 'HH24:MI'), '—') AS "DADER FILA",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='LOROKRAIK' AND m.tipu='TAMA'), 'HH24:MI'), '—') AS "LOROKRAIK TAMA",
    COALESCE(to_char(MAX(m.oras) FILTER (WHERE m.sesaun='LOROKRAIK' AND m.tipu='FILA'), 'HH24:MI'), '—') AS "LOROKRAIK FILA",
    CASE p.status
        WHEN 'PRESENT' THEN 'Prezente' WHEN 'ABSENT'  THEN 'Falta'
        WHEN 'LEAVE'   THEN 'Lisensa'  WHEN 'MISSION' THEN 'Misaun'
        WHEN 'HOLIDAY' THEN 'Feriadu'  ELSE '—' END         AS "ESTADU",
    COALESCE(p.obs, '')                                     AS "OBS"
FROM loron
CROSS JOIN profesor
LEFT JOIN attendance_listaprezensa l
       ON l.profesor_id = profesor.id
      AND l.fulan = EXTRACT(MONTH FROM loron.data)
      AND l.tinan = EXTRACT(YEAR  FROM loron.data)
LEFT JOIN attendance_prezensa p
       ON p.lista_id = l.id AND p.data = loron.data
LEFT JOIN attendance_marka m
       ON m.prezensa_id = p.id
GROUP BY loron.data, profesor.id, profesor.naran_kompletu, p.status, p.obs
ORDER BY profesor.naran_kompletu, loron.data;
```

### 2.3 Mode "Semana" — one week of a month

Weeks are counted **from Monday inside the month**, the same way the API does
it (`semana_husi`): week = `(day_of_month + weekday_of_the_1st - 1) / 7 + 1`.

Add this to §2.2's `loron` CTE:

```sql
loron AS (
    SELECT d::date AS data
    FROM parametru,
         generate_series(
             make_date(tinan, fulan, 1),
             (make_date(tinan, fulan, 1) + INTERVAL '1 month - 1 day')::date,
             INTERVAL '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) <> 7
      AND (
            (EXTRACT(DAY FROM d)::int
             + (EXTRACT(ISODOW FROM make_date(tinan, fulan, 1))::int - 1) - 1) / 7 + 1
          ) = 2                                  -- 🔧 semana 1..6
),
```

### 2.4 The evidence behind one day (photo + GPS modal)

This one is a genuine `INNER JOIN` chain — you only want days that have punches.

```sql
SELECT
    u.naran_kompletu                            AS profesor,
    p.data,
    m.sesaun, m.tipu,
    'ORAS_' || m.sesaun || '_' || m.tipu        AS kolumna,
    to_char(m.oras, 'HH24:MI:SS')               AS oras,
    CASE
      WHEN m.tipu = 'FILA' THEN NULL
      WHEN m.sesaun = 'DADER'     THEN m.oras > TIME '08:00'
      ELSE m.oras > TIME '13:30'
    END                                         AS atrazadu,
    m.foto,                                     -- path under MEDIA_ROOT
    m.latitude, m.longitude,
    round(m.distansia_metru::numeric, 1)        AS distansia_metru,
    m.iha_eskola,
    m.presizaun,
    m.rejistu_iha
FROM attendance_marka m
INNER JOIN attendance_prezensa p        ON p.id = m.prezensa_id
INNER JOIN attendance_listaprezensa l   ON l.id = p.lista_id
INNER JOIN accounts_user u              ON u.id = l.profesor_id
WHERE p.data = DATE '2026-08-06'        -- 🔧
  AND u.id  = 1                         -- 🔧 (drop this line for all teachers)
ORDER BY m.oras;
```

### 2.5 Punches made outside the school (geofence review)

```sql
SELECT u.naran_kompletu, p.data, m.sesaun, m.tipu,
       to_char(m.oras,'HH24:MI') AS oras,
       round(m.distansia_metru::numeric, 1) AS metru_husi_eskola,
       m.latitude, m.longitude, m.foto
FROM attendance_marka m
INNER JOIN attendance_prezensa p      ON p.id = m.prezensa_id
INNER JOIN attendance_listaprezensa l ON l.id = p.lista_id
INNER JOIN accounts_user u            ON u.id = l.profesor_id
WHERE m.iha_eskola IS FALSE
ORDER BY p.data DESC, m.oras;
```

---

## 3. Screen: Relatóriu

Mirrors `lib/relatoriu.ts` exactly: **loron servisu** = every working day in the
period, marked or not; **atrazadu** = *days* where either arrival was late (not
the number of late punches); **%** = `round(prezente / loron servisu * 100)`.

### 3.1 The per-teacher table

```sql
-- 🔧 period
WITH parametru AS (SELECT 8 AS fulan, 2026 AS tinan),
loron AS (
    SELECT d::date AS data
    FROM parametru,
         generate_series(
             make_date(tinan, fulan, 1),
             (make_date(tinan, fulan, 1) + INTERVAL '1 month - 1 day')::date,
             INTERVAL '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) <> 7
),
profesor AS (
    SELECT id, naran_kompletu, kargu
    FROM accounts_user
    WHERE role IN ('PROFESSOR','ADMIN') AND is_active
),
loron_profesor AS (
    SELECT
        profesor.id, profesor.naran_kompletu, profesor.kargu,
        loron.data,
        p.status,
        COALESCE(bool_or(m.oras > TIME '08:00') FILTER (WHERE m.sesaun='DADER'     AND m.tipu='TAMA'), FALSE)
        OR
        COALESCE(bool_or(m.oras > TIME '13:30') FILTER (WHERE m.sesaun='LOROKRAIK' AND m.tipu='TAMA'), FALSE)
            AS atrazadu
    FROM loron
    CROSS JOIN profesor
    LEFT JOIN attendance_listaprezensa l
           ON l.profesor_id = profesor.id
          AND l.fulan = EXTRACT(MONTH FROM loron.data)
          AND l.tinan = EXTRACT(YEAR  FROM loron.data)
    LEFT JOIN attendance_prezensa p
           ON p.lista_id = l.id AND p.data = loron.data
    LEFT JOIN attendance_marka m
           ON m.prezensa_id = p.id
    GROUP BY profesor.id, profesor.naran_kompletu, profesor.kargu, loron.data, p.status
)
SELECT
    naran_kompletu                                              AS "PROFESÓR",
    COALESCE(NULLIF(kargu,''), '')                              AS "KARGU",
    count(*)                                                    AS "LORON SERVISU",
    count(*) FILTER (WHERE status = 'PRESENT')                  AS "PREZENTE",
    count(*) FILTER (WHERE status = 'PRESENT' AND atrazadu)     AS "ATRAZADU",
    count(*) FILTER (WHERE status = 'ABSENT')                   AS "FALTA",
    count(*) FILTER (WHERE status = 'LEAVE')                    AS "LISENSA",
    count(*) FILTER (WHERE status = 'MISSION')                  AS "MISAUN",
    round(100.0 * count(*) FILTER (WHERE status = 'PRESENT') / NULLIF(count(*),0))
                                                                AS "%"
FROM loron_profesor
GROUP BY id, naran_kompletu, kargu
ORDER BY naran_kompletu;
```

### 3.2 The four stat cards (PREZENSA % · ATRAZADU · FALTA · LISENSA + MISAUN)

Same CTEs as §3.1, different final SELECT:

```sql
SELECT
    round(100.0 * count(*) FILTER (WHERE status='PRESENT') / NULLIF(count(*),0)) AS "PREZENSA %",
    count(*) FILTER (WHERE status='PRESENT' AND atrazadu)                        AS "ATRAZADU",
    count(*) FILTER (WHERE status='ABSENT')                                      AS "FALTA",
    count(*) FILTER (WHERE status IN ('LEAVE','MISSION'))                        AS "LISENSA + MISAUN"
FROM loron_profesor;
```

### 3.3 Year mode ("Tinan")

Replace the `loron` CTE with the whole year:

```sql
loron AS (
    SELECT d::date AS data
    FROM parametru,
         generate_series(make_date(tinan,1,1), make_date(tinan,12,31), INTERVAL '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) <> 7
),
```

---

## 4. Screen: Painel (today)

```sql
WITH ohin AS (SELECT CURRENT_DATE AS loron),           -- 🔧 or DATE '2026-08-07'
profesor AS (
    SELECT id, naran_kompletu, kargu, nu_kontaktu
    FROM accounts_user
    WHERE role IN ('PROFESSOR','ADMIN') AND is_active
),
estadu_ohin AS (
    SELECT profesor.id, profesor.naran_kompletu, profesor.kargu, profesor.nu_kontaktu,
           p.id AS prezensa_id,
           count(m.id) AS marka_total
    FROM ohin
    CROSS JOIN profesor
    LEFT JOIN attendance_listaprezensa l
           ON l.profesor_id = profesor.id
          AND l.fulan = EXTRACT(MONTH FROM ohin.loron)
          AND l.tinan = EXTRACT(YEAR  FROM ohin.loron)
    LEFT JOIN attendance_prezensa p ON p.lista_id = l.id AND p.data = ohin.loron
    LEFT JOIN attendance_marka   m ON m.prezensa_id = p.id
    GROUP BY profesor.id, profesor.naran_kompletu, profesor.kargu, profesor.nu_kontaktu, p.id
)
-- The stat cards
SELECT count(*)                                   AS "TOTÁL",
       count(*) FILTER (WHERE marka_total > 0)    AS "MARKA ONA",
       count(*) FILTER (WHERE marka_total = 0)    AS "SEIDAUK MARKA"
FROM estadu_ohin;

-- The "Seidauk marka ohin" list (with the contact the dashboard joins in)
-- ...same CTEs, then:
SELECT naran_kompletu AS "PROFESÓR",
       COALESCE(NULLIF(kargu,''),'—')       AS "KARGU",
       COALESCE(NULLIF(nu_kontaktu,''),'—') AS "KONTAKTU"
FROM estadu_ohin
WHERE marka_total = 0
ORDER BY naran_kompletu;
```

Today's punch feed ("Marka foun ohin loron", newest first):

```sql
SELECT u.naran_kompletu, m.sesaun, m.tipu,
       to_char(m.oras,'HH24:MI') AS oras, m.iha_eskola, m.foto
FROM attendance_marka m
INNER JOIN attendance_prezensa p      ON p.id = m.prezensa_id
INNER JOIN attendance_listaprezensa l ON l.id = p.lista_id
INNER JOIN accounts_user u            ON u.id = l.profesor_id
WHERE p.data = CURRENT_DATE
ORDER BY m.rejistu_iha DESC;
```

---

## 5. Modal "Rejistu Lisensa" — write a status over a date range

Same effect as `POST /api/prezensa/status/`: skips Sundays, opens the monthly
sheet if missing, writes `status` + `obs`.

> ⚠️ **Never bury punches.** Run the conflict check first — the API refuses the
> whole range when any day already has a `marka`, because those rows are
> evidence.

```sql
-- STEP 1 — conflict check. Must return zero rows before you continue.
SELECT p.data, count(m.id) AS marka
FROM attendance_prezensa p
INNER JOIN attendance_listaprezensa l ON l.id = p.lista_id
INNER JOIN attendance_marka m         ON m.prezensa_id = p.id
WHERE l.profesor_id = 1                             -- 🔧 teacher id
  AND p.data BETWEEN DATE '2026-08-10' AND DATE '2026-08-12'   -- 🔧 husi / to'o
GROUP BY p.data
ORDER BY p.data;
```

```sql
-- STEP 2 — write the range (one transaction, Sundays skipped)
BEGIN;

WITH parametru AS (
    SELECT 1                     AS profesor_id,   -- 🔧
           DATE '2026-08-10'     AS husi,          -- 🔧
           DATE '2026-08-12'     AS too,           -- 🔧
           'LEAVE'               AS status,        -- 🔧 LEAVE|MISSION|HOLIDAY|ABSENT
           'Moras — atestadu médiku' AS obs        -- 🔧
),
loron AS (
    SELECT d::date AS data, parametru.*
    FROM parametru, generate_series(parametru.husi, parametru.too, INTERVAL '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) <> 7
),
-- open the monthly sheet(s) if they do not exist yet
lista_foun AS (
    INSERT INTO attendance_listaprezensa (profesor_id, kargu, fulan, tinan, kriadu_iha, atualiza_iha)
    SELECT DISTINCT loron.profesor_id,
           COALESCE(u.kargu, ''),
           EXTRACT(MONTH FROM loron.data)::smallint,
           EXTRACT(YEAR  FROM loron.data)::smallint,
           NOW(), NOW()
    FROM loron JOIN accounts_user u ON u.id = loron.profesor_id
    ON CONFLICT (profesor_id, fulan, tinan) DO NOTHING
    RETURNING id, profesor_id, fulan, tinan
),
lista AS (
    SELECT id, profesor_id, fulan, tinan FROM lista_foun
    UNION
    SELECT l.id, l.profesor_id, l.fulan, l.tinan
    FROM attendance_listaprezensa l
    WHERE l.profesor_id = (SELECT profesor_id FROM parametru)
)
INSERT INTO attendance_prezensa (lista_id, data, status, obs)
SELECT lista.id, loron.data, loron.status, loron.obs
FROM loron
JOIN lista
  ON lista.profesor_id = loron.profesor_id
 AND lista.fulan = EXTRACT(MONTH FROM loron.data)
 AND lista.tinan = EXTRACT(YEAR  FROM loron.data)
ON CONFLICT (lista_id, data)
DO UPDATE SET status = EXCLUDED.status, obs = EXCLUDED.obs
RETURNING lista_id, data, status, obs;

-- Check the RETURNING output, then:
COMMIT;    -- or ROLLBACK; if it looks wrong
```

```sql
-- STEP 3 — "Hasai rejistu": undo one hand-written day.
-- Refuses (0 rows) if the day has punches or is PRESENT — same rule as the API.
DELETE FROM attendance_prezensa p
USING attendance_listaprezensa l
WHERE l.id = p.lista_id
  AND l.profesor_id = 1                     -- 🔧
  AND p.data = DATE '2026-08-10'            -- 🔧
  AND p.status <> 'PRESENT'
  AND NOT EXISTS (SELECT 1 FROM attendance_marka m WHERE m.prezensa_id = p.id)
RETURNING p.id, p.data, p.status;
```

---

## 6. Useful checks

```sql
-- Who exists, and what are they?
SELECT id, numeru_id, naran_kompletu, email, role, kargu, is_active, is_staff
FROM accounts_user ORDER BY role, naran_kompletu;

-- Who can open the dashboard? (EhAdmin = is_staff OR role='ADMIN')
SELECT numeru_id, naran_kompletu, email, role, is_staff
FROM accounts_user
WHERE is_active AND (is_staff OR role = 'ADMIN');

-- Sheets opened per teacher
SELECT u.naran_kompletu, l.tinan, l.fulan, l.kargu,
       count(p.id) AS loron_rejistadu
FROM attendance_listaprezensa l
INNER JOIN accounts_user u        ON u.id = l.profesor_id
LEFT  JOIN attendance_prezensa p  ON p.lista_id = l.id
GROUP BY u.naran_kompletu, l.tinan, l.fulan, l.kargu
ORDER BY l.tinan DESC, l.fulan DESC, u.naran_kompletu;

-- Full punch history of one teacher
SELECT p.data, m.sesaun, m.tipu, to_char(m.oras,'HH24:MI') AS oras,
       m.iha_eskola, round(m.distansia_metru::numeric,1) AS metru
FROM attendance_marka m
INNER JOIN attendance_prezensa p      ON p.id = m.prezensa_id
INNER JOIN attendance_listaprezensa l ON l.id = p.lista_id
WHERE l.profesor_id = 1                 -- 🔧
ORDER BY p.data DESC, m.oras;

-- Orphan check: days that claim PRESENT but hold no punch
SELECT u.naran_kompletu, p.data, p.status
FROM attendance_prezensa p
INNER JOIN attendance_listaprezensa l ON l.id = p.lista_id
INNER JOIN accounts_user u            ON u.id = l.profesor_id
WHERE p.status = 'PRESENT'
  AND NOT EXISTS (SELECT 1 FROM attendance_marka m WHERE m.prezensa_id = p.id);

-- Row counts
SELECT 'accounts_user' AS tabela, count(*) FROM accounts_user
UNION ALL SELECT 'attendance_listaprezensa', count(*) FROM attendance_listaprezensa
UNION ALL SELECT 'attendance_prezensa',      count(*) FROM attendance_prezensa
UNION ALL SELECT 'attendance_marka',         count(*) FROM attendance_marka;
```

---

## 7. Backup & restore

Target directory: **`C:\workplace\eti-dili`** · plain `.sql` files.

`pg_dump` is **not on PATH** on this machine — it ships with the server at
`C:\Program Files\PostgreSQL\18\bin`. Every command below uses the full path;
adjust `18` if you upgrade PostgreSQL.

> The connection values are the same ones in `eti-api/.env`
> (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_NAME`). **Never put `DB_PASSWORD` in a
> script or a scheduled task file** — set `PGPASSWORD` for the session, or use
> a [`pgpass.conf`](https://www.postgresql.org/docs/current/libpq-pgpass.html)
> at `%APPDATA%\postgresql\pgpass.conf`.

### 7.1 Back up now — run this, nothing to edit

Every value below is already yours (`eti_2026_db`, `localhost:5432`, `postgres`,
target `C:\workplace\eti-dili`). **The only thing to type is your password**
where it says `PASSWORD-ITA-NIAN`. Paste the whole block.

**PowerShell** — the file is dated automatically, e.g.
`eti_2026_db_2026-08-08.sql`:

```powershell
$env:PGPASSWORD = "PASSWORD-ITA-NIAN"
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -p 5432 -U postgres -d eti_2026_db --format=plain --encoding=UTF8 --create --clean --if-exists --no-owner --no-privileges --file="C:\workplace\eti-dili\eti_2026_db_$(Get-Date -Format yyyy-MM-dd).sql"
$env:PGPASSWORD = ""
```

**Command Prompt (cmd.exe)** — fixed file name:

```bat
set PGPASSWORD=PASSWORD-ITA-NIAN
"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -p 5432 -U postgres -d eti_2026_db --format=plain --encoding=UTF8 --create --clean --if-exists --no-owner --no-privileges --file="C:\workplace\eti-dili\eti_2026_db_backup.sql"
set PGPASSWORD=
```

Success prints **nothing**. Check the file exists and is not empty:

```powershell
Get-ChildItem C:\workplace\eti-dili\*.sql | Select-Object Name, Length, LastWriteTime
```

An 82 KB file with 3 teachers is normal; the size grows with punches, not with
photos (those are files, see §7.4).

Run it **whenever you want** — before a migration, before deleting a teacher,
at the end of a month. Automating it daily is optional: §7.5.

Why each flag matters — drop one and the restore stops being complete:

Why each flag matters — drop one and the restore stops being complete:

| Flag | Why |
| --- | --- |
| `--format=plain` | a readable `.sql` you can restore with `psql`, as asked |
| `--encoding=UTF8` | Tetun and Portuguese accents (`Profesór`, `Juñu`, `Sábadu`) survive. Without it Windows may write cp1252 and mangle them |
| `--create` | the dump creates the database itself, so it restores onto a bare server |
| `--clean --if-exists` | drops what is there first, so a re-restore is not a half-merge |
| `--no-owner --no-privileges` | restores under whatever role you use, instead of failing on a missing `postgres` role on another machine |

This dumps **all 15 tables**, not just the four app ones — `django_migrations`,
`auth_permission`, `django_content_type`, the session and JWT-blacklist tables
come along. That matters: a dump of only `accounts_*` and `attendance_*` would
restore rows that Django then refuses to run against, because it would believe
no migration had ever been applied.

It also includes sequence positions, all primary/foreign/unique keys and every
index — verified: 15 PK, 14 FK, 13 UNIQUE after a test restore.

### 7.2 Restore

The dump contains `DROP DATABASE` + `CREATE DATABASE`, so **connect to
`postgres`, not to the database being replaced** — you cannot drop the database
you are connected to.

```bat
set PGPASSWORD=your-password
set PGCLIENTENCODING=UTF8
"C:\Program Files\PostgreSQL\18\bin\psql.exe" ^
  -h localhost -p 5432 -U postgres -d postgres ^
  -v ON_ERROR_STOP=1 ^
  -f "C:\workplace\eti-dili\eti_2026_db_backup.sql"
set PGPASSWORD=
```

`ON_ERROR_STOP=1` is not optional: without it `psql` keeps going after a failed
statement and reports success on a half-restored database.

**Restore under a different name** (to test a backup without touching
production) — the dump names the database in a few places, so rename them all:

```powershell
(Get-Content "C:\workplace\eti-dili\eti_2026_db_backup.sql") `
  -replace 'eti_2026_db', 'eti_restore_test' `
  | Set-Content -Encoding utf8 "C:\workplace\eti-dili\_restore_test.sql"
```

then restore that file the same way and point `DB_NAME` at it.

### 7.3 Verify the restore (do this at least once)

```sql
-- 1. Row counts must match the source
SELECT 'accounts_user' AS tabela, count(*) FROM accounts_user
UNION ALL SELECT 'attendance_listaprezensa', count(*) FROM attendance_listaprezensa
UNION ALL SELECT 'attendance_prezensa',      count(*) FROM attendance_prezensa
UNION ALL SELECT 'attendance_marka',         count(*) FROM attendance_marka
UNION ALL SELECT 'django_migrations',        count(*) FROM django_migrations;

-- 2. Accents survived
SELECT naran_kompletu, kargu FROM accounts_user ORDER BY id LIMIT 5;

-- 3. Keys and indexes are back
SELECT count(*) FILTER (WHERE contype='p') AS pk,
       count(*) FILTER (WHERE contype='f') AS fk,
       count(*) FILTER (WHERE contype='u') AS uniq
FROM pg_constraint WHERE connamespace = 'public'::regnamespace;

-- 4. Sequences continue where they left off — otherwise the next INSERT
--    collides with an existing id
SELECT last_value FROM accounts_user_id_seq;
```

Then from `eti-api/`, the checks that matter most:

```bash
python manage.py migrate --check   # schema matches the models, nothing pending
python manage.py runserver         # log in — password hashes are restored intact
```

A full round-trip was run against this database: all row counts matched,
accents survived, sequences and constraints restored, `migrate --check` passed
and the ORM read the whole `Marka → Prezensa → ListaPrezensa → User` chain.

### 7.4 The database alone is **not** a complete backup

`Marka.foto` and `User.foto` store a **path**, not the image. Restore the
database without the files and every punch photo — the evidence that replaced
the signature — is a broken link.

Back up the media directory in the same run:

```powershell
Compress-Archive -Path "C:\workplace\eti-dili\eti-api\media\*" `
  -DestinationPath "C:\workplace\eti-dili\media_$(Get-Date -Format yyyy-MM-dd).zip" -Force
```

A complete backup is **two** artefacts: the `.sql` and the media archive. Keep
them together — a `.sql` from Monday with photos from Friday restores rows
pointing at files that do not exist yet.

Also outside the dump: `.env` (secrets — back it up somewhere private, never in
git) and the code itself (already in git).

### 7.5 Daily automatic backup — **optional**

Nothing above depends on this. §7.1 is the whole backup; set this up only if
you would rather not remember to run it.

Save as `C:\workplace\eti-dili\backup-eti.ps1`:

```powershell
# Daily backup of the ETI PREZENSA database and its photos.
$ErrorActionPreference = "Stop"
$loron  = Get-Date -Format yyyy-MM-dd
$alvu   = "C:\workplace\eti-dili"
$pgbin  = "C:\Program Files\PostgreSQL\18\bin"

# Password comes from %APPDATA%\postgresql\pgpass.conf, never from this file.
& "$pgbin\pg_dump.exe" -h localhost -p 5432 -U postgres -d eti_2026_db `
  --format=plain --encoding=UTF8 --create --clean --if-exists `
  --no-owner --no-privileges `
  --file="$alvu\eti_2026_db_$loron.sql"

Compress-Archive -Path "C:\workplace\eti-dili\eti-api\media\*" `
  -DestinationPath "$alvu\media_$loron.zip" -Force

# Keep 30 days; a backup you never prune fills the disk and then stops running.
Get-ChildItem "$alvu\eti_2026_db_*.sql", "$alvu\media_*.zip" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
  Remove-Item -Force
```

Schedule it (run once, as Administrator):

```powershell
schtasks /create /tn "ETI PREZENSA backup" /sc daily /st 19:00 ^
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\workplace\eti-dili\backup-eti.ps1"
```

19:00 is after the last scheduled punch (17:30), so a backup never lands in the
middle of the school day.

> **A backup you have never restored is not a backup.** Restore into
> `eti_restore_test` once a term, run §7.3, then drop it.

---

## 8. Things SQL cannot do for you

| Task | Why | Do this instead |
| --- | --- | --- |
| Set a usable password | Django stores a PBKDF2 hash | Create through the dashboard, or `manage.py shell` → `u.set_password(...)` |
| Insert a punch (`attendance_marka`) | `foto` must be a real file under `MEDIA_ROOT`, and `distansia_metru`/`iha_eskola` are computed on save | Punch from the mobile app |
| Delete a teacher's photos | Rows cascade, files on disk do not | Remove from `MEDIA_ROOT` manually |
| Change `status` to `PRESENT` by hand | Only a punch may produce it | Leave it to the app |
