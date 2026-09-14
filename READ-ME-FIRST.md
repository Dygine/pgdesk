# Fix: the Dygine toggle would not stay on

## What was wrong

`PlatformSettingsUpdate` — the pydantic model that validates `PATCH
/master/settings` — did not declare the Dygine fields. Pydantic drops undeclared
fields **silently**, so the request returned 200 with `dygine_enabled`,
`dygine_base_url` and `dygine_key_id` already stripped out before the service
ever saw them.

The two secrets kept working because they go through their own endpoint. That is
why the screen showed "One is stored" while the toggle flipped back off and the
URL and key id reverted to placeholders.

My mistake: I added the fields to the service's `WRITABLE` set but not to the
schema that gates it. `WRITABLE` is the second gate. The schema is the first,
and it was the one discarding them.

## Two files

```
backend/app/schemas/organization.py     the five missing fields
backend/tests/test_platform_settings.py two regression tests
```

Copy both over the ones in your repo, then:

```powershell
git add .
git commit -m "fix: dygine settings were dropped by the patch schema"
git push origin main
```

No migration. No frontend change.

## The tests

`test_every_writable_field_is_declared_on_the_patch_schema` compares `WRITABLE`
against the schema's declared fields and fails on any mismatch. That catches the
whole class of bug, so the next field added to one and not the other fails
loudly instead of silently reverting.

`test_dygine_settings_survive_a_patch` is the specific case: PATCH the three
values, re-read, assert they persisted.

Both were verified to fail with the bug reintroduced and pass with it fixed.

## After deploying

Master admin → Settings → Dygine Pay:

1. Fill the URL and key id again (they were never saved)
2. The secrets are already stored — leave those two fields empty
3. Turn the toggle on
4. **Save** at the top of the page
5. Reload — the toggle should still be on
6. **Test connection**
