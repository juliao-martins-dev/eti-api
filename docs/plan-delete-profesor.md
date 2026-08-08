# Plan — `DELETE /api/profesor/{id}/` (simple version)

Status: **proposal, nothing implemented yet.** Backend first, then dashboard.
Supersedes the earlier draft with the two-step `409` confirmation — dropped, as
requested.

---

## 1. What it does

`DELETE /api/profesor/{id}/` removes the teacher **and everything attached to
them**. The three foreign keys are already `on_delete=CASCADE`
(`attendance/models.py:97, 188, 341`), so one delete removes:

```
accounts_user ─> attendance_listaprezensa ─> attendance_prezensa ─> attendance_marka
   teacher            monthly sheets             day rows              punches
```

Plus the punch/profile **photo files** under `MEDIA_ROOT` — otherwise the rows
vanish and the images stay on disk forever. "All delete" means all of it.

**This is irreversible and there is no undo.** That is why the dashboard asks
for the password twice and shows the warning below.

---

## 2. Backend

### Contract

| | |
| --- | --- |
| Route | `DELETE /api/profesor/{id}/` |
| Auth | `IsAuthenticated` + `EhAdmin` (unchanged) |
| Body | `{ "password": "<the signed-in admin's own password>" }` |

| Code | Body | When |
| --- | --- | --- |
| `204` | — | Deleted, cascade complete |
| `400` | `{detail, code: "password_presiza"}` | No `password` in the body |
| `403` | `{detail, code: "password_sala"}` | Wrong password |
| `403` | `{detail, code: "rasik"}` | Trying to delete your own account |
| `403` | — | Caller is not an admin (`EhAdmin`) |
| `404` | — | No such teacher |

**Why the backend checks the password too:** the double entry in the browser is
friction for the human, not security — anyone can call the API directly with
curl. One line (`request.user.check_password(...)`) makes the check real. The
two fields in the UI are about slowing the admin down; this is about the
endpoint being safe.

**`rasik` guard:** deleting your own account would lock the school out of its
own dashboard. Two lines, worth keeping.

### Files

| File | Change |
| --- | --- |
| `accounts/views.py` | add `'delete'` to `http_method_names`; add `destroy()` |
| `accounts/serializers.py` | `ProfesorHasaiSerializer` — one field, `password` |
| `accounts/tests.py` | replace `test_delete_and_put_are_not_allowed`, add §4 cases |
| `docs/plan.md`, `docs/integrate-api.md`, `docs/sql-query.md`, `docs/schema-overview.html` | they currently state "there is no DELETE" |

No migration — the schema does not change.

### Sketch

```python
def destroy(self, request, *args, **kwargs):
    alvo = self.get_object()

    payload = ProfesorHasaiSerializer(data=request.data)
    payload.is_valid(raise_exception=True)              # 400 password_presiza

    if alvo.pk == request.user.pk:
        return erru(403, 'rasik', "La bele hasai konta rasik.")

    if not request.user.check_password(payload.validated_data['password']):
        return erru(403, 'password_sala', "Password sala.")

    fotos = foto_paths(alvo)          # collect before the rows disappear
    alvo.delete()                     # CASCADE does the rest
    remove_files(fotos)
    logger.warning('profesor hasai: actor=%s alvo=%s', request.user.pk, alvo.pk)
    return Response(status=204)
```

---

## 3. Dashboard — `eti-dashboard/`

Screen: **Profesór sira** → edit modal. A red **"Hamos profesór"** button sits
apart from "Dezativa konta", which stays the normal, reversible action.

### The confirmation modal

1. **Warning banner, verbatim, with the teacher's NU. ID in place of `###`:**

   > Karik ita boot hakarak hamos manorin ho id **112** sujere halo backup
   > report molok atu delete atu nunee labele akontese buat neebe ita lakoi!

   Rendered in a red/amber alert box with a warning icon. `###` is the
   `numeru_id` — the "NU. ID" column the admin already sees in the table.

2. **A shortcut to the backup** the message asks for: a link to Relatóriu
   filtered to that teacher, so "halo backup report molok" is one click
   (Export ba PDF / Export ba Excel already exist there).

3. **Two password fields**, both `type="password"`,
   `autoComplete="current-password"`:
   - `Password admin`
   - `Konfirma password`
   The **Hamos** button stays disabled until both are non-empty **and equal**.
   Mismatch shows *"Password la hanesan"* under the second field, and nothing
   is sent.

4. On submit, one `DELETE` with the password in the body.

| Result | Dashboard does |
| --- | --- |
| `204` | toast *"Profesór hamos ho susesu"*, close modal, `karegaProfesor(true)` |
| `403 password_sala` | keep the modal open, clear **both** fields, *"Password sala. Koko fila fali."* |
| `403 rasik` | *"La bele hamos konta rasik."*, close |
| other | existing `mensajenErru()` toast |

The typed password is component state only — never stored, cached or logged.

### Files

| File | Change |
| --- | --- |
| `lib/store.ts` | `hamosProfesor(id, password)` → `api(..., { method: "DELETE", body })`, then `karegaProfesor(true)` |
| `app/(dashboard)/profesor/page.tsx` | button + modal + the two fields + error mapping |
| `lib/types.ts` | nothing new needed (payload is inline) — add a type only if it reads better |

---

## 4. Tests (backend)

| Test | Expect |
| --- | --- |
| Correct password, teacher with no history | `204`, user gone |
| Correct password, teacher **with** sheets/days/punches | `204`; all cascade rows gone; photo files removed |
| No `password` field | `400 password_presiza` |
| Wrong password | `403 password_sala`, **teacher still exists** |
| The *target's* password instead of the admin's | `403 password_sala` |
| Delete self | `403 rasik` |
| Ordinary teacher calls DELETE | `403` |
| Anonymous calls DELETE | `401` |

---

## 5. Order of work

1. Backend: serializer → `destroy()` → tests → full suite (82 today).
2. Docs: the four files that say DELETE is not allowed.
3. Dashboard: `lib/store.ts` → modal in `profesor/page.tsx` → `tsc --noEmit`.
4. Manual pass: wrong password, mismatched fields, then a real delete.

---

## 6. One thing to be aware of

A teacher deleted this way takes their attendance record with them — sheets,
days, punches, photos, everything. If the school ever needs to answer *"was
this person present on 06 Agostu?"*, the answer is gone with no trace that the
row ever existed. That is exactly what the warning message tells the admin, and
why the export shortcut in step 2 is worth including rather than leaving it as
advice.

If you would rather keep the history and only free the `numeru_id`, that is
`PATCH {numeru_id: 9112, is_active: false}` and no delete at all — but you have
asked for the delete, so the plan builds it.

**Say "go" and I start with the backend.**
