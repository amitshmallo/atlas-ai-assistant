# Atlas — AI Executive Assistant

Phase 1: project skeleton, Clean Architecture layering, health check.
Phase 2: Entra ID authentication + Microsoft Graph (On-Behalf-Of flow).
Phase 3: Azure deployment (Container Apps, Key Vault, Postgres, Redis, ACR) via `azd`.

See the full PRD/phased plan at `.claude/plans/project-atlas-calm-ember.md` (or wherever it was saved).

## Layout

```
app/
  domain/          entities + abstract interfaces (no framework imports)
  application/      use cases, depend only on domain interfaces
  infrastructure/    concrete implementations: DB, config, logging, Entra ID/Graph
  api/               FastAPI routers + dependency wiring
frontend/            React + Vite SPA, MSAL.js login
```

## Backend quickstart

```bash
cp .env.example .env
docker compose up -d
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

`GET http://localhost:8000/health` should return 200. `GET /me` requires a
valid bearer token (see Entra ID setup below).

## Tests

```bash
pytest
```

## Frontend quickstart

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

---

## Entra ID setup (do this once, manually, in the Azure Portal)

Atlas needs **two** app registrations: one for the API (validates tokens,
does the On-Behalf-Of exchange), one for the SPA (does the interactive
login). This mirrors how real Microsoft-Graph-backed apps are built — the
SPA never talks to Graph directly, it only gets a token scoped to *your*
API, and your API exchanges that for a Graph token server-side.

### 1. Register the API app

1. Azure Portal → **Entra ID** → **App registrations** → **New registration**
2. Name: `Atlas API`. Supported account types: single tenant (your own) is fine for dev. No redirect URI needed here.
3. After creation, note the **Application (client) ID** and **Directory (tenant) ID** — these go in `.env` as `ENTRA_API_CLIENT_ID` and `ENTRA_TENANT_ID`.
4. **Certificates & secrets** → **New client secret** → copy the value immediately (shown once) → `.env` as `ENTRA_API_CLIENT_SECRET`.
5. **Expose an API** → **Add a scope**:
   - Application ID URI: accept the default `api://<api-client-id>`
   - Scope name: `access_as_user`
   - Who can consent: Admins and users
   - Add it.
6. **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** → add `User.Read` (already there by default), `Mail.Read`, `Mail.Send`, `Calendars.ReadWrite`, `offline_access`. Click **Grant admin consent** if you're the tenant admin (you will be, on a personal/dev tenant).

### 2. Register the SPA app

1. **New registration** again. Name: `Atlas Frontend`.
2. Redirect URI: platform **Single-page application**, URI `http://localhost:5173`.
3. Note its **Application (client) ID** → frontend `.env` as `VITE_ENTRA_SPA_CLIENT_ID`. Same tenant ID as before → `VITE_ENTRA_TENANT_ID`.
4. **API permissions** → **Add a permission** → **My APIs** → select `Atlas API` → check `access_as_user` → **Grant admin consent**.
5. In frontend `.env`, set `VITE_API_CLIENT_ID` to the **API app's** client ID (not the SPA's) — this is what builds the `api://<id>/access_as_user` scope the SPA requests.

### 3. Run it

```bash
# terminal 1
docker compose up -d
uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173`, sign in, click "Fetch Graph profile via API".
That round trip proves: SPA login → API-scoped token → API validates JWT via
Entra ID JWKS → API exchanges it On-Behalf-Of for a Graph token (cached in
Redis) → API calls Graph `/me` → response flows back to the browser.

---

## Azure deployment (Phase 3)

### Prerequisites

Install these (not done by the agent — they need an interactive installer/login):

```powershell
winget install -e --id Microsoft.AzureCLI
winget install -e --id Microsoft.Azd
```

Then, in a fresh terminal (PATH only updates for new shells):

```bash
az login
azd auth login
```

### What gets provisioned

`infra/main.bicep` (subscription-scope, orchestrating `infra/modules/*.bicep`):

- Resource group
- Log Analytics workspace (required by Container Apps for logs)
- Azure Container Registry (Basic) — holds the built API image
- Key Vault (RBAC-authorized) — holds `database-url`, `redis-url`, `entra-api-client-secret`
- Azure Database for PostgreSQL – Flexible Server (Burstable B1ms, dev-sized)
- Azure Cache for Redis (Basic) — backs the OBO token cache in prod, same role Docker Compose's `redis` plays locally
- Container Apps environment + the `api` Container App (system-assigned managed identity, scales to zero, pulls secrets straight from Key Vault via `keyVaultUrl` — no secrets ever sit in Container App config as plain env values)

The API container never touches Azure credentials directly — its managed
identity is granted `AcrPull` on the registry and `Key Vault Secrets User`
on the vault, and Container Apps resolves `keyVaultUrl` secrets at runtime
using that identity.

### Deploy

```bash
azd env new atlas-dev
azd env set ENTRA_TENANT_ID <your-tenant-id>
azd env set ENTRA_API_CLIENT_ID <your-api-app-client-id>
azd env set ENTRA_API_CLIENT_SECRET <your-api-app-client-secret>
azd env set POSTGRES_ADMIN_PASSWORD <choose-a-strong-password>

azd up
```

`azd up` provisions everything above, builds the Dockerfile, pushes it to
ACR, and deploys it to Container Apps — then prints `SERVICE_API_URI`.
Verify with:

```bash
curl https://<SERVICE_API_URI>/health
```

**Known first-deploy race**: the Container App's managed identity gets its
Key Vault/ACR role assignments in the same deployment that tries to use
them, so the very first `azd up` can occasionally fail while resolving
`keyVaultUrl` secrets or pulling the image. If that happens, just run
`azd deploy` again — the role assignments will already exist by then.

### Update the SPA redirect URI for the deployed API

Once you have `SERVICE_API_URI`, add it as an additional **Single-page
application** redirect URI on the `Atlas Frontend` app registration (Entra
ID setup, step 2) if you deploy the frontend somewhere too — Phase 3 only
covers the backend; the SPA still runs locally against the deployed API by
pointing `VITE_API_BASE_URL` at `SERVICE_API_URI`.

### Tear down

```bash
azd down --purge
```

`--purge` also removes the soft-deleted Key Vault so the name can be reused
— skip it if you want to keep the vault recoverable for 7 days instead.
