# PS-05 — Disaster Early-Warning & Resource Coordination

Django + React + Postgres. An ops room sees every incident on a live map, and the
dispatcher decides which unit goes where — optimised against nearest-available,
side by side, with the difference on screen.

> **Maintainers:** replace `<your-org>` with the real GitHub owner everywhere in
> this file before sharing it. If the repo isn't published yet, see
> [Publishing the repo](#publishing-the-repo-maintainers-once) at the bottom —
> nobody can fork until that's done once.

---

## What state is this in?

**The scaffold is complete and core services are implemented.** Every model,
endpoint, serializer, URL, permission, WebSocket consumer and the whole auth
chain are wired and working. The core service layer (dispatch, alerts, resources,
reports) has been implemented with all business logic filled in.

That means when you first run this:

- Logging in works. The dashboard loads. The socket connects.
- API endpoints return real data. The dispatch cycle runs end-to-end.
- The database comes up **empty**. Add rows through `/admin/` or use the API.

Every function carries its full contract in its docstring: what it receives field
by field, what it must return, which functions to call, what to do in the
database, and what to broadcast.

---

## Before you start

| | Version | Check with |
|---|---|---|
| Python | 3.11+ (3.13 known good) | `python3 --version` / `python --version` |
| Node | 18+ (22 known good) | `node --version` |
| PostgreSQL | 14+ (18 known good) | `psql --version` |
| Redis | optional — see [below](#redis-is-optional) | `redis-cli ping` |

<details>
<summary><b>macOS — install everything</b></summary>

```bash
brew install python@3.13 node postgresql@18 redis
brew services start postgresql@18
brew services start redis          # optional
```
</details>

<details>
<summary><b>Windows — install everything</b></summary>

```powershell
winget install Python.Python.3.13
winget install OpenJS.NodeJS.LTS
winget install PostgreSQL.PostgreSQL.17
```

Or download the installers from [python.org](https://www.python.org/downloads/),
[nodejs.org](https://nodejs.org/) and
[postgresql.org](https://www.postgresql.org/download/windows/). During the
Postgres install, **note the password you set for the `postgres` user** — you'll
need it in `.env`.

Tick *"Add Python to PATH"* in the Python installer, or `python` won't be found.

Redis has no official Windows build — skip it, see [below](#redis-is-optional).
</details>

---

## 1. Fork and clone

Fork the repo on GitHub (**Fork** button, top right), then:

```bash
git clone https://github.com/<your-username>/disha.git
cd disha/website
git remote add upstream https://github.com/<your-org>/disha.git
```

The `upstream` remote is how you pull in other people's work later. Everything
below runs from `disha/website`.

---

## 2. Create the database

**macOS**

```bash
createdb disha
```

**Windows** (PowerShell — `psql` lives in `C:\Program Files\PostgreSQL\17\bin`,
add it to PATH or `cd` there first)

```powershell
psql -U postgres -c "CREATE DATABASE disha;"
```

---

## 3. Backend

**macOS / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

> If PowerShell blocks the activate script, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
>
> On **cmd.exe** the activate line is `.venv\Scripts\activate.bat` instead.

### Fill in `backend/.env`

Only these four actually need your attention:

```ini
DB_NAME=disha
DB_USER=          # macOS: your mac username.  Windows: postgres
DB_PASSWORD=      # macOS: usually blank.      Windows: what you set at install
SECRET_KEY=       # any long random string for local dev
```

Everything else has a working default. `.env` is gitignored — **never commit it.**

### Migrate and create your login

```bash
python manage.py migrate
python manage.py createsuperuser
```

(On Windows use `python`; on macOS use `python` too once the venv is active.)

`migrate` creating 12 tables across 6 apps means your database connection is
good. If it fails, the error is almost always `DB_USER` / `DB_PASSWORD`.

### Run it

```bash
python manage.py runserver
```

→ **http://localhost:8000** · admin at **/admin/**

`daphne` is first in `INSTALLED_APPS`, so `runserver` serves **HTTP *and*
WebSockets** — you do not need a separate ASGI server in development.

---

## 4. Frontend

Open a **second terminal** (leave the backend running):

**macOS / Linux**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

**Windows (PowerShell)**

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

→ **http://localhost:5173** — log in with the superuser you just created.

`frontend/.env` needs no edits unless you changed the backend port.

---

## 5. Check it actually worked

| What you should see | What it proves |
|---|---|
| Login succeeds, dashboard loads | JWT issue + storage works |
| Network tab: `Bearer …` on every `/api/` call | The axios request interceptor is attaching tokens |
| Network tab: `/ws/ops` in status **101** | WebSocket + query-string JWT auth works |
| Dashboard shows incidents, resources, shelters | Services are implemented and returning data |

If the last row shows `401` instead of `501`, your token isn't reaching the
server. If it shows `CORS` errors, check `CORS_ALLOWED_ORIGINS` in `backend/.env`
matches the port Vite actually started on.

---

## How the project is laid out

```
website/
├── backend/          Django · one app per feature, one owner per app
│   ├── config/       settings · urls · asgi · websocket routing
│   ├── accounts/     JWT login, roles, permissions
│   ├── reports/      incidents — everything downstream reads from here
│   ├── resources/    units, shelters, depots, stock
│   ├── dispatch/     assignments, zones, and the delivered allocator
│   │   ├── engine.py   ← already written. Pure Python, zero Django imports
│   │   └── services.py ← the orchestrator. Fully implemented.
│   ├── alerts/       CAP warnings in, notifications out
│   ├── ingest/       SMS + IVR — the no-internet path
│   └── realtime/     websocket consumers + broadcast(). Imports nothing
└── frontend/         React + Vite · one folder per feature
    └── src/
        ├── shared/   axios client, socket, live store — cross-feature only
        └── features/ auth · map · heatmap · fleet · dispatch · resources
                      zones · alerts · supply · timeline
```

**Two architectural rules.** Break either and you get import errors on day 4:

1. **Never import upward.** `reports` must not import `dispatch`. If a report
   should trigger a dispatch, the layer *above* calls both in order — which is
   why `reports/views.py` calls `run_cycle()` and `reports/services.py` doesn't.
2. **Pass dictionaries across app boundaries, not model objects.**
   `realtime.broadcast()` takes plain dicts, needs no imports, and that is what
   keeps it out of every dependency cycle.

The same idea on the frontend: a feature owns its `api.js`, `hooks.js`,
`store.js`, `pages/` and `components/`, and exports only through `index.js`.
Features never reach into each other's internals — shared code lives in
`shared/`.

---

## Picking up work

1. Find remaining stubs by name:

   ```bash
   grep -rn "raise NotImplementedError" backend      # find remaining stubs
   grep -rn 'throw new Error("TODO'   frontend/src   # JS stubs
   ```

2. Open it and read the docstring. It tells you the inputs field by field, the
   exact return shape, which functions to call, what to do in the database, and
   what to broadcast.
3. Write the body. **Don't change the signature or the return shape** — other
   people are coding against it right now.
4. Branch, commit, push, open a PR against `upstream`:

   ```bash
   git checkout -b flood/create-incident
   git commit -am "reports: implement create_incident"
   git push origin flood/create-incident
   ```

**If you must change a contract, say so in writing first.** The stub headers are
what let five people work in parallel without talking; a silent signature change
breaks somebody else's afternoon.

### Staying in sync

```bash
git fetch upstream
git rebase upstream/main
```

---

## Redis is optional

The WebSocket layer runs without it. Leave `REDIS_URL` **empty** in
`backend/.env` and Django falls back to an in-memory channel layer:

```ini
REDIS_URL=
```

That works for a single dev server — which is every laptop — and is the simplest
path on **Windows, where Redis has no official build**. It does *not* work across
multiple worker processes, because groups live in one process's memory. Use real
Redis for anything deployed.

Windows users who want real Redis: run it under WSL2, or install
[Memurai](https://www.memurai.com/).

---

## Common problems

| Symptom | Cause and fix |
|---|---|
| `501 not_implemented` from an endpoint | That service function is still a stub. The body names which one. |
| `password authentication failed` | `DB_USER` / `DB_PASSWORD` in `backend/.env`. Windows usually needs `DB_USER=postgres`. |
| `ModuleNotFoundError: django` | The venv isn't active. Re-run the activate line for your shell. |
| `.venv\Scripts\Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then reopen PowerShell. |
| CORS error in the browser console | `CORS_ALLOWED_ORIGINS` must match Vite's actual port — it moves to 5174 if 5173 is taken. |
| `/ws/ops` closes with **4401** | Access token expired or missing. The client refreshes and reconnects on its own; a repeat means login is broken. |
| `/ws/ops` closes with **4403** | You're a responder trying to open another unit's channel. |
| `Error 61 connecting to 127.0.0.1:6379` | Redis isn't running. Start it, or blank out `REDIS_URL`. |
| Everything renders in the Bay of Bengal | `lat`/`lon` swapped. GeoJSON is `[lon, lat]`; everything else here is `lat, lon`. |
| `ImportError: cannot import name` | You imported upward. See the two rules above. |

---

## Publishing the repo (maintainers, once)

The project isn't on GitHub yet, so there is nothing to fork. Run this once from
`disha/website`:

```bash
git init -b main
git add .
git commit -m "PS-05 scaffold: Django + React + Postgres"
git remote add origin https://github.com/<your-org>/disha.git
git push -u origin main
```

Before that first push, confirm the secrets are actually excluded:

```bash
git status --short | grep -E "\.env$"     # must print NOTHING
```

`.gitignore` already excludes `backend/.env`, `frontend/.env`, `.venv/`,
`node_modules/`, `docs/` and `ps05/`. The `.env.example` files **are** committed —
that's intentional, they're the template with no secrets in them.
