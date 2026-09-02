# Deploying DISHA — Neon + Render + Vercel

Three free tiers, no other services.

| Piece | Where | What it runs |
|---|---|---|
| Database | **Neon** | PostgreSQL 16 |
| API + WebSocket | **Render** | Django 5.2 on daphne (ASGI) |
| Dashboard | **Vercel** | React + Vite static build |

Do them in that order — Render needs the Neon URL, Vercel needs the Render URL.

---

## 0. Before you start

```bash
# from the repo root
git add -A && git commit -m "deploy config" && git push
```

Two files must be in the repo:

- `backend/data/roadgraph.bin` (~9.7 MB) — the **compiled** road graph. Production
  loads this; it never calls Overpass. If it is missing, regenerate it from a
  machine that already has the graph in its database:
  ```bash
  cd backend && python manage.py seed_roadgraph --export data/roadgraph.bin
  ```
- `render.yaml` and `frontend/vercel.json` — already committed.

`backend/data/*.osm.json` is gitignored on purpose. It is a 40 MB raw download
that exists only to be compiled once.

---

## 1. Neon — the database

1. https://neon.tech → new project, region **AWS ap-southeast-1 (Singapore)**
   (closest to a Render Singapore service; latency shows up in every dispatch solve).
2. Dashboard → **Connection string** → copy the **Pooled connection** URI. It looks like:
   ```
   postgresql://user:PASSWORD@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
3. Keep it. That single string is `DATABASE_URL`.

> Use the **pooled** endpoint, not the direct one. Render's free tier sleeps and
> wakes; each wake opens a fresh pool, and Neon's direct endpoint runs out of
> connections faster than the pooler does.

---

## 2. Render — the API

### 2a. Create the service

Render → **New → Blueprint** → point it at this repo. It reads `render.yaml`
and creates one web service named `disha-api`.

If you would rather click through it manually, the settings that matter are:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Runtime | Python 3 |
| Build command | `./build.sh` |
| Start command | `daphne -b 0.0.0.0 -p $PORT config.asgi:application` |
| Health check path | `/api/health` |

**The start command must be daphne, not gunicorn.** The dashboard's live updates
run over a WebSocket at `/ws/ops`, and a WSGI server cannot serve one.

### 2b. Environment variables

Set these in the Render dashboard (`sync: false` in the blueprint means Render
will prompt you for them):

| Key | Value |
|---|---|
| `DATABASE_URL` | the Neon pooled URI from step 1 |
| `SECRET_KEY` | leave it — the blueprint generates one |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `disha-api.onrender.com` (your actual Render host) |
| `CORS_ALLOWED_ORIGINS` | `https://disha.vercel.app` — your Vercel URL, **no trailing slash** |
| `CSRF_TRUSTED_ORIGINS` | same as above |
| `REDIS_URL` | `""` (empty) — see the warning below |
| `USE_ROAD_GRAPH` | `True` |
| `USE_WEBSOCKETS` | `True` |
| `SEED_DEMO` | `true` for the **first** deploy only |
| `AUTO_DISPATCH` | `False` — an operator presses Dispatch. `True` makes every report dispatch itself |

You will not know the Vercel URL yet. Deploy Vercel first with a placeholder API
URL, or come back and fill these two in after step 3 — Render redeploys in
about a minute.

> **`REDIS_URL=""` means the in-memory channel layer**, and that is only correct
> while the service runs a **single instance**. WebSocket groups live in one
> process's memory, so with two instances a broadcast from instance A never
> reaches a browser connected to instance B — the dashboard silently stops
> updating for half your users. Render's free tier is single-instance, so this
> is fine for a demo. The moment you scale, add a Render Key Value (Redis)
> instance and put its internal URL here.

### 2c. First deploy

`build.sh` runs in order: install → `collectstatic` → `migrate` →
load the road graph from `data/roadgraph.bin` → seed the demo district if
`SEED_DEMO=true`.

Watch the log for:

```
loaded 'puri': 420397 nodes, 854017 edges
place check: every seeded point is within 1 km of a road
seeded 28 units, 11 shelters, 10 hospitals, 31 users, 43 incidents
```

Then **set `SEED_DEMO` back to `false`.** Left on, every future deploy wipes
live incidents and reseeds the demo.

Verify:
```bash
curl https://disha-api.onrender.com/api/health
# {"ok": true, "db": true}
```

---

## 3. Vercel — the dashboard

1. Vercel → **Add New → Project** → import the repo.
2. **Root Directory: `frontend`**. Vercel reads `frontend/vercel.json` for the
   rest (Vite preset, SPA rewrites, asset caching).
3. Environment variables — **Production**:

| Key | Value |
|---|---|
| `VITE_API_URL` | `https://disha-api.onrender.com/api` |
| `VITE_WS_URL` | `wss://disha-api.onrender.com/ws` |
| `VITE_MAP_CENTER_LAT` | `19.8135` |
| `VITE_MAP_CENTER_LON` | `85.8312` |
| `VITE_MAP_ZOOM` | `11` |

**`wss://`, not `ws://`.** The page is served over HTTPS and a browser refuses a
plain-ws socket from a secure page — the dashboard would load and then never
update, with the error only visible in the console.

4. Deploy. Copy the resulting URL back into Render's `CORS_ALLOWED_ORIGINS` and
   `CSRF_TRUSTED_ORIGINS`, and redeploy Render.

> Vite inlines `VITE_*` at **build** time. Changing one in Vercel does nothing
> until you redeploy — there is no runtime config to edit.

---

## 4. Check it end to end

```bash
API=https://disha-api.onrender.com

curl -s $API/api/health
curl -s -X POST $API/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"operator1","password":"demo1234"}' | head -c 80
```

Then open the Vercel URL and sign in as `operator1` / `demo1234`. You should see:

- the top bar dot pulsing green (**Live** — the WebSocket is up)
- the KPI band showing `Waiting 26`
- the Live map drawing incidents, units, shelters (🏠) and hospitals (🏥), with
  **no dispatch routes yet** — nothing has been sent
- Avg response / Slowest 10% / Reached in time all reading `--`, because nothing
  has arrived anywhere yet. `Waiting 26` and `No unit assigned 16` in red.
- Dispatch showing 26 cards, each `N unit ready`, and a tinted **FORECAST** band:
  what the strip would read if you committed the whole plan
- Pressing Dispatch on one card sends that scene and drops `Waiting` by one

If the dot says **Reconnecting**, the WebSocket failed — check `VITE_WS_URL` is
`wss://` and that `ALLOWED_HOSTS` contains the Render host.

---

## 5. The mobile app

The app is not deployed to a store; it runs through Expo.

```bash
cd App
# App/.env
EXPO_PUBLIC_API_BASE=https://disha-api.onrender.com/api
npx expo start --clear
```

`--clear` matters: Expo inlines `EXPO_PUBLIC_*` at build time and caches the
bundle, so an edited `.env` is ignored without it.

---

## Known limits of this stack

Be able to say these out loud before someone asks.

| Limit | Effect | Fix when it matters |
|---|---|---|
| **Render free tier sleeps after ~15 min idle** | First request takes 30–60 s to wake, and the road graph reloads into memory. **Hit the URL a few minutes before a demo.** | Paid instance, or a cron ping |
| **In-memory channel layer** | Single instance only; a second one breaks live updates silently | Render Key Value (Redis), set `REDIS_URL` |
| **Render disk is ephemeral** | Uploaded incident photos vanish on redeploy | S3 / Cloudinary via `django-storages` |
| **Neon free tier scales to zero** | First query after idle adds ~1 s | Paid tier keeps it warm |
| **Road graph is ~10 MB in RAM** | Render free tier is 512 MB — it fits, with room | Watch memory if you add a second district |
| **`SEED_DEMO=true` is destructive** | Wipes incidents on every deploy | Keep it `false` |

---

## Troubleshooting

**`DisallowedHost`** — the Render hostname is not in `ALLOWED_HOSTS`. It is a
comma-separated list, no scheme, no trailing slash.

**CORS error in the browser console** — `CORS_ALLOWED_ORIGINS` must be the exact
Vercel origin *with* `https://` and *without* a trailing slash. Vercel preview
deployments get their own hostnames; add them or test on production.

**Admin has no CSS** — `collectstatic` did not run. It is in `build.sh`;
check the build log.

**404 on a hard refresh of `/dispatch`** — the SPA rewrite in `vercel.json` is
not being applied. Confirm the Vercel Root Directory is `frontend`.

**Dashboard loads but never updates** — the WebSocket. `wss://` not `ws://`, and
`USE_WEBSOCKETS=True` on Render.

**`no RoadGraph row exists`** in the log — `data/roadgraph.bin` was not committed.
Routing silently falls back to straight-line ETAs, which still work but are not
the real thing. Export and commit the blob, then redeploy.
