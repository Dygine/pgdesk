# Running PGDesk from VS Code

Drop the `.vscode` folder and the `scripts` folder into the project root —
the folder that contains `backend/` and `frontend/`:

```
pgdesk/
├── .vscode/          <- from this bundle
├── scripts/          <- from this bundle
├── backend/
├── frontend/
└── README.md
```

Then open that folder in VS Code (`File > Open Folder`), not a parent of it.
The tasks use `${workspaceFolder}`, so opening the wrong level breaks every path.

---

## Once per machine

PostgreSQL must be installed and the role must exist. If you have not done
this yet:

```
psql -U postgres
```
```sql
CREATE USER pgdesk WITH PASSWORD 'pgdesk' CREATEDB;
CREATE DATABASE pgdesk OWNER pgdesk;
CREATE DATABASE pgdesk_test OWNER pgdesk;
```

Then in VS Code: **Ctrl+Shift+P** → `Tasks: Run Task` → **PGDesk: First-time Setup**

That creates the venv, installs dependencies, writes `backend\.env` with a
generated `SECRET_KEY`, patches the CORS header, runs migrations, seeds demo
data, and installs the frontend packages. It is safe to re-run — every step
checks before acting.

---

## Every day after that

**Ctrl+Shift+B**

That is it. Or the long way: **Ctrl+Shift+P** → `Tasks: Run Task` →
**PGDesk: Start All**.

Three terminals open side by side:

| Terminal | What it is |
|---|---|
| `pgdesk:backend` | uvicorn with `--reload` on port 8000 |
| `pgdesk:frontend` | Vite dev server on port 5173 |
| `pgdesk:open-browser` | polls both, prints the URLs, opens the browser |

The browser opens on its own once both servers answer. The third terminal
also prints your LAN address so you can open the app on your phone, and the
demo logins so you are not hunting for them.

---

## The other tasks

| Task | When |
|---|---|
| **PGDesk: Stop All** | After a crash, when a port is still held and you get "address already in use" |
| **PGDesk: Reseed Database** | Demo data has drifted; wipes tenant data and re-seeds |
| **PGDesk: Backend Tests** | The full pytest suite — needs the `pgdesk_test` database |
| **PGDesk: Frontend Build** | `vite build`, which doubles as the import/static check |

---

## Demo logins

| Role | Email | Password |
|---|---|---|
| Master | master@pgdesk.local | Master@2024 |
| Owner | owner@sunrise.local | Owner@2024 |
| Manager | manager@sunrise.local | Manager@2024 |
| Resident | customer@sunrise.local | Customer@2024 |
| Owner (2nd tenant) | owner@northstar.local | Owner@2024 |

The eight `@sunriselivingpg.com` staff accounts use `demo1234`.

---

## Your changes and the Android app

The Android app opens the live website (https://pgdesk.dygine.com), not your
machine. So:

- `npm run dev` shows your changes **in the browser** straight away.
- The **phone app** shows them only after you `git push` and Render has deployed.
  Nothing else - no APK, no version number.
- A new APK is needed only for native changes: a new Capacitor plugin, a new
  Android permission, the app icon or name, or a new website address.

## When something does not start

**"running scripts is disabled on this system"** — PowerShell execution
policy. The tasks already pass `-ExecutionPolicy Bypass`, so this only hits
you in a manual terminal. Fix for that session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Backend terminal shows a database error** — PostgreSQL is not running, or
`backend\.env` does not match the `pgdesk` role password. Check the service:

```powershell
Get-Service *postgres*
```

Reset the password from the superuser account if needed:

```
psql -U postgres
ALTER USER pgdesk PASSWORD 'pgdesk';
```

**Login screen loads but the button does nothing** — press F12 and look at the
Console tab. A CORS error means `allow_headers` in `backend\app\main.py` is
missing `"X-PGDesk-Auth"`. Running **First-time Setup** again fixes it.

**Phone cannot reach the LAN address** — Windows Firewall blocks inbound 5173
by default. Allow it once, from an Administrator PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Vite dev 5173" -Direction Inbound -LocalPort 5173 -Protocol TCP -Action Allow
```

You will also need to add that address to `CORS_ORIGINS` in `backend\.env`,
because the API only answers the exact origins listed there:

```
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.42:5173
```

**"Permission denied: python.exe"** — you ran `python -m venv .venv` while the
venv was active. Harmless; the venv already exists. Do not re-create it.

---

## What the tasks deliberately do not do

They do not start or stop PostgreSQL. It runs as a Windows service and should
already be running — `Restart-Service postgresql-x64-18` if it is not.
