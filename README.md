# Atlas — AI Executive Assistant

Phase 1: project skeleton, Clean Architecture layering, health check.
Phase 2: Entra ID authentication + Microsoft Graph (On-Behalf-Of flow).
Phase 3: Azure deployment (Container Apps, Key Vault, Postgres, Redis, ACR) via `azd`.
Phase 4: LLM integration — streaming chat via Azure OpenAI (AI Foundry).
Phase 5: Conversation memory — Postgres-backed history, Redis cache-aside.
Phase 6: Email/calendar tools — Graph-backed OpenAI tool calling.
Phase 7: MCP integration — tools extracted into standalone MCP servers.

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

`GET http://localhost:8000/health` should return 200. `GET /me` and
`POST /chat` require a valid bearer token (see Entra ID setup below).

To test `/chat` locally, either set `AZURE_OPENAI_API_KEY` in `.env`
alongside `AZURE_OPENAI_ENDPOINT`, or run `az login` first and leave the key
unset — the app falls back to your `az login` credential via
`DefaultAzureCredential` (the same code path the Container App uses with
its managed identity in Azure, see `app/infrastructure/chat_client.py`).

`POST /chat` takes `{ conversation_id: string | null, message: string }` and
streams the reply as plain text, returning the (possibly newly created)
conversation id in the `X-Conversation-Id` response header. Pass that same
id back on the next call to continue the conversation — history is loaded
from Postgres (cached in Redis) before each call, so any API instance can
service any turn of any conversation. `GET /chat/{conversation_id}/messages`
returns the stored history; both endpoints check the conversation's
`user_oid` against the caller's token and 404 if they don't match, so one
user can't read or write another user's conversation by guessing an id.

### Email/calendar tools (Phase 6)

`/chat` now gives the model four tools, dispatched via `GraphToolExecutor`
(`app/application/graph_tools.py`):

- `list_recent_emails`, `read_email` — read-only Graph calls
- `draft_reply` — creates a reply **draft** in the user's Drafts folder via
  Graph's `createReply` + a body PATCH; it never sends anything
- `propose_calendar_event` — does **not** call Graph at all. It just returns
  the proposed subject/start/end/attendees back into the conversation so the
  model can present it and ask the user to confirm

Actually creating a calendar event only happens via `POST /calendar/events`,
a plain REST endpoint the frontend calls directly after the user reviews a
proposal — the model has no way to trigger it itself. This is the
"draft/propose, then explicit approval" pattern from `ATLAS_SYSTEM_PROMPT`
made structurally impossible to bypass, rather than just prompted for.

Tool-calling is a two-step protocol against Azure OpenAI: `complete_with_tools`
(non-streaming, so the full `tool_calls` array is visible) runs first: if the
model wants to call tools, they're executed and their results are appended
to history, then `stream_completion` runs a second time for the actual
streamed answer. If the model doesn't need tools, its first response is
used directly (not streamed token-by-token, since the round trip that
detects tool calls only returns a complete response either way).

### MCP integration (Phase 7)

Phase 6's tools moved out of `app/application/graph_tools.py` (deleted) into
standalone MCP servers under `mcp_servers/`:

- `mcp_servers/graph_server.py` — the four email/calendar tools, reusing the
  same `HttpxGraphMailClient` from Phase 6, unchanged
- `mcp_servers/notes_server.py` — a trivial one-tool stub that exists purely
  to prove extensibility (see below)

`app/infrastructure/mcp_tool_provider.py`'s `McpToolProvider` is now the only
thing `SendChatMessageUseCase` talks to (via the `domain.ToolProvider`
interface) — it spawns each registered server as a subprocess over stdio,
discovers its tools dynamically via `list_tools()`, and dispatches calls via
`call_tool()`. **`application/chat.py` has zero knowledge that Graph, or any
external process, is involved at all.**

The server registry lives in `app/infrastructure/mcp_registry.py` — a plain
list of `(name, command, args, env_keys)`. To prove you can add a tool
without touching the orchestrator: `notes_server.py`'s `remember_note` tool
is registered there and Just Works in chat, with no changes anywhere else.
Try asking Atlas to "remember that I prefer concise replies" — it'll call
`remember_note` exactly like any Graph tool.

The Graph access token is injected into the server subprocess via the
`GRAPH_ACCESS_TOKEN` environment variable at spawn time — never exposed to
the model as a tool argument it could see or fill in itself.

This phase is a pure refactor: chat behavior is identical to Phase 6 (live-
verified), the only thing that changed is *how* tools are wired in. Each
tool call spawns a fresh subprocess rather than reusing a persistent
connection — a deliberate simplicity-over-performance tradeoff; a pooled/
persistent MCP session would be a reasonable Phase 10-style optimization,
not something needed to prove the architecture.

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
6. **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** → add `User.Read` (already there by default), `Mail.ReadWrite`, `Calendars.ReadWrite`, `offline_access`. Click **Grant admin consent** if you're the tenant admin (you will be, on a personal/dev tenant). (`Mail.ReadWrite`, not `Mail.Send` — Atlas creates reply drafts but never sends anything itself, so `Mail.Send` is deliberately not requested.)

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
- Azure AI Foundry (Cognitive Services `AIServices` account) with a `gpt-5-mini` deployment — backs `/chat`. Model versions get retired over time (we hit exactly this with the original `gpt-4o-mini` plan); check the AI Foundry portal for the current model/version before deploying.
- Container Apps environment + the `api` Container App (system-assigned managed identity, scales to zero, pulls secrets straight from Key Vault via `keyVaultUrl` — no secrets ever sit in Container App config as plain env values)

The API container never touches Azure credentials directly — its managed
identity is granted `AcrPull` on the registry, `Key Vault Secrets User` on
the vault, and `Cognitive Services OpenAI User` on the AI Foundry account.
Container Apps resolves `keyVaultUrl` secrets at runtime using that same
identity, and `chat_client.py` authenticates to Azure OpenAI with it too —
no API key is ever deployed to the Container App.

### Deploy

```bash
azd env new atlas-dev
azd env set ENTRA_TENANT_ID <your-tenant-id>
azd env set ENTRA_API_CLIENT_ID <your-api-app-client-id>
azd env set ENTRA_API_CLIENT_SECRET <your-api-app-client-secret>
azd env set POSTGRES_ADMIN_PASSWORD <choose-a-strong-password>
azd env set AI_FOUNDRY_MODEL_VERSION <current gpt-5-mini version string — check the AI Foundry portal>

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
