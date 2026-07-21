# Atlas — AI Executive Assistant

Phase 1: project skeleton, Clean Architecture layering, health check.
Phase 2: Entra ID authentication + Microsoft Graph (On-Behalf-Of flow).
Phase 3: Azure deployment (Container Apps, Key Vault, Postgres, Redis, ACR) via `azd`.
Phase 4: LLM integration — streaming chat via Azure OpenAI (AI Foundry).
Phase 5: Conversation memory — Postgres-backed history, Redis cache-aside.
Phase 6: Email/calendar tools — Graph-backed OpenAI tool calling.
Phase 7: MCP integration — tools extracted into standalone MCP servers.
Phase 8: RAG & document processing — blob upload, async OCR/embed/index pipeline, document search tool.
Phase 9: Long-term memory — durable preferences, auto-loaded every turn.
Phase 10: Monitoring & secure networking — distributed tracing, VNet + private endpoints.

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

### RAG & document processing (Phase 8)

Event-driven, exactly per the plan: `POST /documents` (`app/api/routers/documents.py`)
only uploads the raw file to Blob Storage and writes a `processing` row to
Postgres (`documents` table) — it returns immediately, it does **not** wait
for OCR. Everything slow happens asynchronously in a separate,
independently-scaled process:

```
POST /documents → Blob Storage (documents/{user_oid}/{document_id}-{filename})
                → triggers azure_functions/document_processor (blob trigger)
                       → Document Intelligence (OCR) → chunk_text() → embed each
                         chunk (Azure OpenAI) → index in Azure AI Search
                         (+ user_oid on every chunk) → flip Postgres row to
                         ready/failed
```

`GET /documents` lets the frontend poll a document's status. Once a
document is `ready`, `mcp_servers/docs_server.py` (a fourth MCP server,
registered exactly like `notes_server.py` — zero orchestrator changes)
exposes a `search_documents` tool: it embeds the user's question, does a
vector search against Azure AI Search filtered to `user_oid eq '<caller>'`,
and returns matching chunks with their source filename so the model can
cite them (`ATLAS_SYSTEM_PROMPT` explicitly asks it to).

**Isolation, not credentials**: every user's chunks live in the *same*
Azure AI Search index — there's no per-user index — isolation is enforced
entirely by the `user_oid` filter applied at query time. This is why
`ToolProvider.execute_tool` takes a `context: dict[str, str]` now instead
of a single Graph token: the docs server needs `USER_OID` injected as an
env var the same way the graph server needs `GRAPH_ACCESS_TOKEN`, and both
are things the model must never see or supply itself.

`azure_functions/document_processor/chunking.py` holds the two pure
functions (`chunk_text`, `parse_blob_path`) with zero Azure imports,
specifically so they're unit-testable without the Functions runtime or any
Azure SDK — see `tests/test_document_chunking.py`.

**Running/deploying the Function is not covered by local `uvicorn`/`docker
compose` testing** — it's a separate deployable unit, with its own venv. To
run it locally:

```bash
cd azure_functions/document_processor
py -3.11 -m venv .venv   # NOT 3.12 — see note below
.venv\Scripts\activate
pip install -r requirements.txt
cp local.settings.json.example local.settings.json   # fill in the Azure endpoints/keys
func start   # requires Azure Functions Core Tools: `npm i -g azure-functions-core-tools@4`
```

**Use Python 3.11 for this venv, not 3.12.** The Azure Functions Python
worker (as of Core Tools 4.12.1) hits `AttributeError:
'_SixMetaPathImporter' object has no attribute '_path'` on startup under
3.12 — a worker/importlib compatibility issue, not anything in this repo's
code. 3.11 starts cleanly. The main FastAPI app has no such restriction and
stays on 3.12.

You'll also need to provision, in the Azure Portal (same pattern as the
AI Foundry setup — a resource group, no admin-tenant gymnastics this time):

- **Azure AI Search** — **Free tier works** (it does support vector search,
  just capped at 25 MB/3 indexes — plenty for testing)
- **Azure AI Document Intelligence** — `S0` tier, `FormRecognizer` kind
- **An embeddings model deployment** in the same AI Foundry project as your
  chat model — deploy `text-embedding-3-small` with that exact deployment
  name (matching `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`). Easy to miss since
  Phase 4 only walks through deploying the chat model — forgetting this
  surfaces as a `DeploymentNotFound` error on the document once it fails.
- A **Blob Storage container** named `documents` (Azurite covers this
  locally; `docker compose up -d` already starts it) — the API creates the
  container itself on first upload if it doesn't exist yet.

Then fill in `.env`: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY` (or
leave blank to use `az login`/managed identity like Azure OpenAI),
`AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`, `AZURE_DOCUMENT_INTELLIGENCE_API_KEY`.
The Azure AI Search *index* itself doesn't need to be created manually —
the Function creates it on first run if it doesn't exist (see
`_ensure_index_exists` in `function_app.py`).

**Live-verified end to end**: upload a PDF → Function processes it (OCR →
chunk → embed → index) → status flips to `ready` → ask Atlas a question
about it in chat → correctly cited answer. Getting there surfaced a few
real gaps, now fixed: `python-multipart` and `aiohttp` were missing from
`requirements.txt` (needed for file uploads and every async Azure SDK
client's transport, respectively — FastAPI/the SDKs don't fail until you
actually hit the code path that needs them), and the local Azurite image
rejects newer Storage API versions the SDK sends by default, fixed with
`--skipApiVersionCheck` in `docker-compose.yml`.

A frontend upload UI ([Documents.tsx](frontend/src/Documents.tsx)) drives
`POST /documents`, shows each document's status, and polls every 4s while
anything is still `processing`.

### Long-term memory (Phase 9)

Preferences are durable facts about the user (`preferences` table:
`user_oid`, `key`, `value`, unique on `user_oid`+`key`) that persist across
brand-new conversations — not just conversation history, which only
applies within one conversation.

The key design choice: **reading preferences is not a tool.** A brand-new
conversation has no reason to know a `get_preferences` tool exists, so
nothing would ever call it — the whole point of "long-term" memory is that
it applies automatically. Instead `SendChatMessageUseCase` loads
preferences directly via `PreferenceRepository` and appends them to the
system prompt on every single turn, the same way conversation history is
loaded — before the model is ever asked anything.

**Writing** a preference, on the other hand, genuinely is a model decision
— the assistant has to judge "is this worth remembering long-term or just
for this message?" — so that's a tool: `mcp_servers/memory_server.py`
exposes `remember_preference(key, value)`, registered in the MCP registry
exactly like `notes_server.py` and `docs_server.py` before it. `USER_OID`
is injected the same way it is for the docs server, so preferences are
naturally isolated per user without the model ever handling an identifier
itself.

Verified three ways: `test_execute_injects_preferences_into_system_prompt_without_a_tool_call`
proves the auto-load happens with zero tool calls involved,
`test_preference_repository.py` runs against the real Postgres container
to prove the upsert (`ON CONFLICT ... DO UPDATE`) actually works, and
live-tested end to end — stated a preference in one conversation, started
a brand-new one, confirmed it still applied.

### Monitoring & secure networking (Phase 10)

**Distributed tracing.** `app/infrastructure/telemetry.py` is the shared
module both the FastAPI app and every MCP server subprocess call. It's
entirely opt-in: with `APPLICATIONINSIGHTS_CONNECTION_STRING` unset (the
local default), every function in it is a no-op — nothing about normal
operation depends on Application Insights being reachable.

The interesting part is making one chat turn's tool call show up as *one
connected trace* instead of disconnected fragments. When `McpToolProvider`
spawns an MCP server subprocess, it injects the current W3C `traceparent`
as an env var (`app/infrastructure/mcp_tool_provider.py`); each MCP server
extracts it and starts its tool-call span as a child of that context
(`traced_subprocess_span` in `telemetry.py`). The result: API span → MCP
subprocess span → the outbound Graph/Azure OpenAI HTTP call the subprocess
makes (via `HTTPXClientInstrumentor`, since neither the `openai` SDK nor
Graph's httpx-based calls get traced automatically) all land in Application
Insights under the same trace ID. Azure Functions gets its own Application
Insights integration for free from the platform (`host.json` already has
the config) — no code changes needed there, just the connection string.

**VNet + private endpoints.** `infra/modules/network.bicep` creates a VNet
with three subnets: one delegated to Container Apps (the API's VNet
integration), one for private endpoints, and one delegated to
`Microsoft.Web/serverFarms` for the Function's *outbound* VNet integration.
`infra/modules/private-endpoint.bicep` is a generic module reused for
Postgres, Azure AI Search, and Azure AI Foundry — each gets
`publicNetworkAccess: 'Disabled'` and is reachable only via private link
from inside the VNet.

**Storage is deliberately left public** — a real constraint, not an
oversight: Azure Functions' blob-trigger polling mechanism on a
Consumption plan requires the storage account to stay publicly reachable;
making it private would require upgrading to a Premium/Dedicated plan,
a cost tradeoff this project doesn't take. **Azure AI Search moves from
Free to Basic tier** for the same kind of reason — Free (shared,
multi-tenant) doesn't support any VNet features at all, so private
endpoint support requires Basic (~$75/mo) once you actually deploy this
via `azd up`; the manual portal setup for local testing still uses Free,
since that path never touches the VNet.

The Container Apps environment's `vnetConfiguration.internal` stays at its
default (`false`/unset) — VNet integration here is only about the API
being able to *reach* private data services, not about hiding the API
itself, which needs to stay internet-reachable for anyone to log in.

This phase's code compiles cleanly (`az bicep build`, zero warnings) but,
like the rest of the Azure deployment story, has never actually been run
via `azd up` — VNet integration and private DNS resolution are the most
likely things in this whole project to need live debugging when that
finally happens, more so than anything in Phases 3-9.

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
