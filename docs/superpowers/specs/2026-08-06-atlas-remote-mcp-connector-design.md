# Atlas Remote MCP Connector — Design

## Context

Atlas currently exposes its tools (email, calendar, document search, memory) only
through four MCP servers spawned as local stdio subprocesses by the Atlas API
itself, per chat turn. They are unreachable from outside the API process.

This project adds a second, standalone, publicly-reachable MCP server —
combining all four existing servers' tools into one — that any Microsoft
account holder can connect to directly from an MCP client (Claude Desktop,
Claude.ai connectors, etc.), authenticating via a real Microsoft sign-in, the
same way a company like PayPal exposes its own remote MCP connector to its
customers.

This is a portfolio/demo piece, not a production service expected to carry
real third-party load or user trust obligations. Design decisions below
reflect that explicitly where it matters (see "Explicit non-goals").

## Goals

- A single remote MCP server exposing all of: Graph email/calendar tools,
  document search, memory (preferences), notes, plus a new `upload_document`
  tool (see below).
- Open to any Microsoft account (personal or work/school), not just accounts
  already invited into Atlas's existing tenant.
- Reuses existing Clean Architecture infrastructure code (Graph clients,
  Search index client, preference repository) rather than reimplementing it.
- The existing Atlas web app (`atlas-platform`) is completely unaffected —
  same chat behavior, same code, same deployment, before and after.
- Lives in its own repo (`atlas-mcp-connector`), deployed as its own Azure
  Container App, sized for near-zero expected load.

## Explicit non-goals

- No document-upload UI, no bulk import — the one `upload_document` MCP tool
  is the only remote ingestion path.
- No rate limiting or abuse monitoring beyond Azure Container Apps' defaults.
- No terms-of-service or privacy-policy page.
- No SLA/uptime expectations — scale-to-zero is intentional; occasional cold
  starts are accepted.

## Architecture

### Auth flow

1. A new Entra ID App Registration, **"Atlas MCP Connector"**, configured as
   multi-tenant + personal Microsoft accounts (distinct from Atlas's existing
   app registrations, which are single-tenant).
2. An MCP client authenticates against this app registration via standard
   OAuth Authorization Code + PKCE, obtaining a token whose audience is this
   app (not Graph).
3. The connector validates that token per-request: signature/expiry against
   the **multi-tenant** JWKS endpoint (`login.microsoftonline.com/common` or
   equivalent — not the single tenant used by `jwt_validator.py` today),
   extracting the caller's `oid` and tenant id.
4. Server-side, the validated token is exchanged for a Graph-scoped access
   token via **On-Behalf-Of**, reusing `MsalOboTokenProvider` unchanged from
   `atlas-platform` (copied into the new repo, configured against the new app
   registration's client id/secret) — mirroring exactly how the existing web
   app already does this.
5. OAuth discovery metadata (`/.well-known/oauth-protected-resource`, per the
   MCP authorization spec) is published so MCP clients can complete the flow
   against Entra ID without manual client-side configuration.

### Tool surface

All tools currently split across `graph_server.py`, `docs_server.py`,
`memory_server.py`, `notes_server.py`, combined into one FastMCP app running
with `transport="streamable-http"` (confirmed supported by the pinned
`mcp==1.28.1` SDK). Each tool call derives its Graph token / `user_oid` from
the current request's validated identity (no per-process env-var injection,
since this isn't spawned per-call the way local stdio servers are).

**New tool: `upload_document(filename: str, content_base64: str) -> str`**
- Only exposed on the remote connector — never added to `atlas-platform`'s
  local `docs_server.py`, so the web app's chat behavior is unchanged.
- Decodes the base64 payload and calls the existing `UploadDocumentUseCase`
  directly — same file-type/size validation, same blob storage write, same
  Postgres row creation, same downstream OCR/indexing Function pickup as the
  web app's own upload endpoint.
- Known tradeoff: base64 inflates payload size ~33%; the existing 20MB cap
  bounds this to a ~27MB request, well within normal HTTP limits. Accepted
  as-is — no chunked/streaming upload path in this design.

### Data model

No new tables. The connector reads/writes the *same* Postgres/Blob
Storage/Azure AI Search Atlas already uses, scoped by the same `user_oid`
isolation already enforced everywhere else in the system (search filters,
ownership checks) — a first-time remote-only user simply has empty
documents/preferences until they populate them (via `upload_document`
and/or `remember_preference`, both usable purely through the connector).

### Deployment

- New Azure Container App, in the same Container Apps Environment as
  `atlas-platform` (same VNet — reaches private Postgres/Search/Redis without
  new networking).
- Smallest available CPU/memory tier.
- `min replicas: 0` — deliberate scale-to-zero, since real external load is
  expected to be near-zero; cold starts on an infrequent real connection are
  an accepted tradeoff, not a bug.
- Own Bicep module + `azd` service entry, same CI/CD shape as existing
  services (GitHub Actions, OIDC federated login — see "Repo & rename"
  below for the one migration risk this introduces).

### Repo structure

- New umbrella repo **`atlas`** — top-level README + architecture overview
  linking the two child repos.
- Existing repo **renamed** from `atlas-ai-assistant` to **`atlas-platform`**
  (GitHub rename; old URLs redirect automatically) — attached to `atlas` as
  a git submodule.
- New repo **`atlas-mcp-connector`** — the connector's code — attached to
  `atlas` as a second git submodule.
- The connector repo does **not** import from `atlas-platform`; the small
  amount of genuinely shared logic (Graph client wrappers, OBO provider,
  ~150 lines) is copied in, accepted as reasonable duplication given the two
  repos' independent lifecycles.

### Migration risk: GitHub Actions OIDC after rename

`atlas-platform`'s CI/CD authenticates to Azure via OIDC, with a federated
credential in Azure scoped to the exact string `repo:<owner>/<reponame>:...`.
Renaming the GitHub repo changes this string (even though GitHub's own URL
redirect keeps browser links working), so **the very next push after the
rename will fail to authenticate to Azure** until the federated credential's
subject condition is updated to reference `atlas-platform` instead of
`atlas-ai-assistant`. This must happen as one atomic step (rename → update
federated credential) before any further push, not be deferred.

## Testing

Same conventions as `atlas-platform`: fakes/unit tests for the multi-tenant
JWT validation logic and the OBO wiring; no live Entra ID or Graph calls in
tests. `upload_document`'s use-case reuse means its core behavior (file
type/size validation, blob write, row creation) is already covered by
existing `atlas-platform` tests — the connector repo's own tests focus on
the base64-decode-then-delegate wrapper, not re-testing the use case itself.

## Open items for the implementation plan

- Exact package/dependency setup for the new repo (subset of
  `atlas-platform`'s `requirements.txt`, not the whole thing).
- Bicep module for the new Container App + its own Key Vault secrets (OBO
  client secret for the new app registration).
- Step-by-step Entra ID portal walkthrough for creating the new multi-tenant
  app registration (mirrors the Phase 2 walkthrough already done once for
  the existing app registrations).
