# Dygine settings screen — 5 files

Without these you have no way to enter the Dygine key secret. I wrote the
service method that stores it but never exposed an endpoint or a form, so the
credentials were unreachable from the UI. This closes that.

Copy each file over the one already in your repo, keeping the same path:

```
backend/app/api/v1/endpoints/master.py          + PUT /master/settings/dygine-secrets
backend/app/schemas/organization.py             + DygineSecretsUpdate
frontend/src/pages/master/DygineCard.jsx        NEW — the settings card
frontend/src/pages/master/MasterSettings.jsx    renders the card
frontend/src/services/api/platformSettingsApi.js + setDygineSecrets()
```

Then:

```powershell
git add .
git commit -m "dygine settings screen"
git push origin main
```

No migration. The columns already went in with 0019.

Both secrets are write-only, the same as the SMTP password: the API reports
whether one is stored, never what it is. The fields stay empty even when a value
exists, and leaving one empty on save keeps what is there.
