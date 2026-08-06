# Atlas Remote MCP Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a standalone, publicly-reachable MCP server (all of Atlas's email/calendar/document-search/memory tools, plus a new `upload_document` tool) that any Microsoft account holder can connect to from an MCP client, authenticating via a new multi-tenant Entra ID app registration and server-side On-Behalf-Of exchange — without changing anything in the existing `atlas-platform` repo.

**Architecture:** A single FastMCP app (`mcp==1.28.1`'s built-in `streamable-http` transport) acting as an OAuth 2.1 Resource Server (via FastMCP's `TokenVerifier`/`AuthSettings`), running as its own Azure Container App in the same environment/VNet as `atlas-platform`, reading/writing the same Postgres/Blob/Search resources. Code that must exist in both repos (Graph clients, OBO exchange) is copied, not shared, per the design doc's accepted-duplication decision.

**Tech Stack:** Python 3.12, `mcp` SDK (FastMCP, streamable-http transport), SQLAlchemy async + asyncpg, `python-jose` for JWT validation, `msal` for OBO, `httpx` for Graph calls, `azure-storage-blob`/`azure-search-documents`/`openai` (Azure OpenAI embeddings) for document search, `pytest`/`pytest-asyncio`.

---

## Prerequisites (manual, portal/GitHub work — not code)

### Task 1: Rename the existing GitHub repo and fix the OIDC trust

This must happen as one atomic sequence — pushing to `atlas-platform`'s CI/CD between the rename and the fix will fail.

- [ ] **Step 1: Rename the GitHub repo**

  GitHub → your `atlas-ai-assistant` repo → Settings → (top of General tab) **Rename** → type `atlas-platform` → confirm. GitHub keeps the old URL working as a redirect, but the identity string used by OIDC changes immediately.

- [ ] **Step 2: Update the git remote in your local clone**

  ```bash
  git remote set-url origin https://github.com/<your-username>/atlas-platform.git
  git remote -v
  ```
  Expected: both `fetch` and `push` lines show the new URL.

- [ ] **Step 3: Update the Azure federated credential's subject**

  Azure Portal → Entra ID → App registrations → the app registration used for GitHub Actions OIDC login (the one referenced by `AZURE_CLIENT_ID` in your CI workflow secrets) → **Certificates & secrets** → **Federated credentials** tab → click the existing credential → edit the **Subject identifier** from
  `repo:<your-username>/atlas-ai-assistant:ref:refs/heads/master`
  to
  `repo:<your-username>/atlas-platform:ref:refs/heads/master`
  → Save.

- [ ] **Step 4: Verify CI still authenticates**

  Push any trivial commit (e.g. this plan file, once committed) to `master` and confirm the `deploy` job's "Log in to Azure (OIDC, no stored secret)" step succeeds in the Actions run.

### Task 2: Create the umbrella repo and the connector repo, wire up submodules

- [ ] **Step 1: Create two new empty GitHub repos**

  Via github.com → New repository:
  - `atlas` — no README, no .gitignore (leave completely empty so the initial commit can set it up cleanly).
  - `atlas-mcp-connector` — same, completely empty.

- [ ] **Step 2: Initialize `atlas-mcp-connector` locally**

  ```bash
  cd ~
  mkdir atlas-mcp-connector && cd atlas-mcp-connector
  git init
  git remote add origin https://github.com/<your-username>/atlas-mcp-connector.git
  ```
  (Leave this as the working directory for all of Tasks 4–15 below — every file path in this plan from here on is relative to this repo's root.)

- [ ] **Step 3: Create the `atlas` umbrella repo with both submodules**

  ```bash
  cd ~
  mkdir atlas && cd atlas
  git init
  git remote add origin https://github.com/<your-username>/atlas.git
  git submodule add https://github.com/<your-username>/atlas-platform.git platform
  git submodule add https://github.com/<your-username>/atlas-mcp-connector.git mcp-connector
  ```

- [ ] **Step 4: Write the umbrella README**

  Create `~/atlas/README.md`:
  ```markdown
  # Atlas

  An AI executive assistant, split across two repos:

  - [`platform/`](https://github.com/<your-username>/atlas-platform) — the
    web app, API, and chat agent. Start here.
  - [`mcp-connector/`](https://github.com/<your-username>/atlas-mcp-connector) —
    a standalone remote MCP server exposing Atlas's tools (email, calendar,
    document search, memory) to any MCP client (e.g. Claude Desktop),
    authenticated via Microsoft sign-in.

  Both submodules are independently deployable and have their own CI/CD.
  ```

- [ ] **Step 5: Commit and push the umbrella repo**

  ```bash
  git add README.md .gitmodules platform mcp-connector
  git commit -m "Initial commit: atlas-platform and atlas-mcp-connector as submodules"
  git push -u origin master
  ```
  Expected: push succeeds; the `atlas` repo on GitHub shows `platform` and `mcp-connector` as linked-repo folders.

### Task 3: Create the multi-tenant Entra ID app registration

- [ ] **Step 1: Register the app**

  Azure Portal → switch to your `atlasdev123.onmicrosoft.com` directory (same one your existing app registrations live in) → Entra ID → App registrations → **New registration**:
  - Name: `Atlas MCP Connector`
  - Supported account types: **"Accounts in any organizational directory and personal Microsoft accounts"**
  - Redirect URI: leave blank for now (MCP clients register their own dynamically or use a fixed one you'll add once you know your Container App's URL — revisit after Task 15's deployment).
  - Click **Register**.

- [ ] **Step 2: Note the identifiers**

  From the app's **Overview** page, copy:
  - **Application (client) ID** → this is `MCP_CONNECTOR_CLIENT_ID`
  - Directory (tenant) ID is not needed here since this app is multi-tenant.

- [ ] **Step 3: Create a client secret**

  **Certificates & secrets** → **New client secret** → any description, 6-month expiry → **Add** → immediately copy the **Value** (not the Secret ID) → this is `MCP_CONNECTOR_CLIENT_SECRET`. You will not be able to see it again after leaving this page.

- [ ] **Step 4: Add API permissions**

  **API permissions** → **Add a permission** → Microsoft Graph → Delegated permissions → add: `User.Read`, `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `offline_access`. (Matches the scopes your existing `atlas-platform` app already requests — same Graph capabilities, new app registration.)

  Do **not** click "Grant admin consent" — this app is multi-tenant/personal-accounts, so each connecting user consents for themselves on first sign-in; there is no tenant admin to consent on their behalf.

- [ ] **Step 5: Record both values somewhere safe**

  You'll need `MCP_CONNECTOR_CLIENT_ID` and `MCP_CONNECTOR_CLIENT_SECRET` in Task 4 (local `.env`) and Task 15 (Key Vault/Bicep). Do not commit either to git.

---

## Connector implementation (all paths relative to `atlas-mcp-connector/`)

### Task 4: Repo scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Create `requirements.txt`**

  ```
  mcp==1.28.1
  httpx>=0.27
  sqlalchemy[asyncio]>=2.0
  asyncpg>=0.30
  pydantic>=2.9
  pydantic-settings>=2.6
  python-jose[cryptography]>=3.3
  msal>=1.31
  azure-identity>=1.19
  azure-storage-blob>=12.24
  azure-search-documents>=11.5
  openai>=1.54
  pytest>=8.3
  pytest-asyncio>=0.24
  ruff==0.15.22
  ```

- [ ] **Step 2: Create `pyproject.toml`**

  ```toml
  [project]
  name = "atlas-mcp-connector"
  version = "0.1.0"
  description = "Standalone remote MCP server exposing Atlas's tools over Microsoft sign-in"
  requires-python = ">=3.12"

  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]

  [tool.ruff]
  line-length = 110
  ```

- [ ] **Step 3: Create `.gitignore`**

  ```
  __pycache__/
  *.pyc
  .venv/
  .env
  ```

- [ ] **Step 4: Create `.env.example`**

  ```
  DATABASE_URL=postgresql+asyncpg://atlasadmin:PASSWORD@HOST:5432/atlas
  AZURE_STORAGE_ACCOUNT_URL=https://ACCOUNT.blob.core.windows.net
  AZURE_STORAGE_DOCUMENTS_CONTAINER=documents
  AZURE_SEARCH_ENDPOINT=https://SEARCH.search.windows.net
  AZURE_SEARCH_INDEX_NAME=documents
  AZURE_OPENAI_ENDPOINT=https://OPENAI.openai.azure.com
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
  MCP_CONNECTOR_CLIENT_ID=
  MCP_CONNECTOR_CLIENT_SECRET=
  MCP_SERVER_PUBLIC_URL=http://localhost:8100
  ```

- [ ] **Step 5: Create `README.md`**

  ```markdown
  # atlas-mcp-connector

  A standalone remote MCP server exposing Atlas's tools (email, calendar,
  document search, memory) to any MCP client, authenticated via Microsoft
  sign-in (any Microsoft account, not just Atlas's existing users).

  Reads/writes the same Postgres/Blob Storage/Azure AI Search that
  [atlas-platform](https://github.com/<your-username>/atlas-platform) uses —
  a first-time user here starts with empty documents/preferences until they
  populate them via this server's own tools (including `upload_document`).

  ## Run locally

  ```bash
  python -m venv .venv
  .venv/Scripts/activate  # or source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env  # fill in real values
  python server.py
  ```
  ```

- [ ] **Step 6: Set up the virtualenv and install**

  ```bash
  python -m venv .venv
  .venv/Scripts/pip install -r requirements.txt
  ```
  Expected: installs cleanly, no errors.

- [ ] **Step 7: Commit**

  ```bash
  git add pyproject.toml requirements.txt .gitignore .env.example README.md
  git commit -m "Scaffold atlas-mcp-connector repo"
  ```

### Task 5: Config

**Files:**
- Create: `config.py`

- [ ] **Step 1: Write `config.py`**

  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict


  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")

      database_url: str

      azure_storage_connection_string: str = ""
      azure_storage_account_url: str = ""
      azure_storage_documents_container: str = "documents"

      azure_search_endpoint: str = ""
      azure_search_api_key: str = ""
      azure_search_index_name: str = "documents"

      azure_openai_endpoint: str = ""
      azure_openai_api_key: str = ""
      azure_openai_api_version: str = "2024-10-21"
      azure_openai_embedding_deployment: str = "text-embedding-3-small"

      mcp_connector_client_id: str
      mcp_connector_client_secret: str
      mcp_server_public_url: str = "http://localhost:8100"

      # Entra ID's multi-tenant "common" endpoint accepts tokens from any
      # tenant plus personal Microsoft accounts — unlike atlas-platform,
      # there is no single fixed tenant_id here.
      @property
      def entra_authority(self) -> str:
          return "https://login.microsoftonline.com/common"

      @property
      def entra_jwks_uri(self) -> str:
          return "https://login.microsoftonline.com/common/discovery/v2.0/keys"

      @property
      def entra_issuer_prefix(self) -> str:
          # v2.0 tokens' issuer is tenant-specific:
          # https://login.microsoftonline.com/{tenant-id}/v2.0 — validated
          # by prefix + shape, not an exact string, since any tenant is valid.
          return "https://login.microsoftonline.com/"


  settings = Settings()
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add config.py
  git commit -m "Add settings"
  ```

### Task 6: Database layer

**Files:**
- Create: `database.py`
- Create: `models.py`

- [ ] **Step 1: Write `database.py`**

  ```python
  from collections.abc import AsyncGenerator

  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
  from sqlalchemy.orm import DeclarativeBase

  from config import settings

  engine = create_async_engine(settings.database_url, pool_pre_ping=True)
  async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


  class Base(DeclarativeBase):
      pass


  async def get_session() -> AsyncGenerator[AsyncSession, None]:
      async with async_session_factory() as session:
          yield session
  ```

- [ ] **Step 2: Write `models.py`**

  Same shape as `atlas-platform`'s `document_models.py`/`preference_models.py` — this connector reads/writes the identical tables, so column names and types must match exactly.

  ```python
  import uuid
  from datetime import datetime

  from sqlalchemy import UniqueConstraint, func
  from sqlalchemy.orm import Mapped, mapped_column

  from database import Base


  class DocumentModel(Base):
      __tablename__ = "documents"

      id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
      user_oid: Mapped[str] = mapped_column(index=True)
      filename: Mapped[str]
      blob_path: Mapped[str]
      status: Mapped[str] = mapped_column(default="processing")
      error_message: Mapped[str | None] = mapped_column(nullable=True)
      created_at: Mapped[datetime] = mapped_column(server_default=func.now())


  class PreferenceModel(Base):
      __tablename__ = "preferences"
      __table_args__ = (UniqueConstraint("user_oid", "key", name="uq_preferences_user_oid_key"),)

      id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
      user_oid: Mapped[str] = mapped_column(index=True)
      key: Mapped[str]
      value: Mapped[str]
      updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
  ```

  No Alembic migrations here — this connector never creates these tables itself, only reads/writes rows in tables `atlas-platform`'s own migrations already created. Running the connector against a database that hasn't had `atlas-platform`'s migrations applied is not a supported configuration.

- [ ] **Step 3: Commit**

  ```bash
  git add database.py models.py
  git commit -m "Add database layer (shared schema with atlas-platform)"
  ```

### Task 7: Multi-tenant token verification

**Files:**
- Create: `auth.py`
- Test: `tests/test_auth.py`

This is the security-critical piece — write the test first.

- [ ] **Step 1: Write the failing test**

  Create `tests/test_auth.py`:

  ```python
  import time

  import pytest
  from jose import jwt

  from auth import EntraTokenVerifier, InvalidTokenError

  _PRIVATE_KEY_PEM = None  # set by the fixture below


  @pytest.fixture
  def rsa_keypair():
      from cryptography.hazmat.primitives.asymmetric import rsa
      from cryptography.hazmat.primitives import serialization

      private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
      private_pem = private_key.private_bytes(
          encoding=serialization.Encoding.PEM,
          format=serialization.PrivateFormat.PKCS8,
          encryption_algorithm=serialization.NoEncryption(),
      ).decode()
      public_numbers = private_key.public_key().public_numbers()
      jwk = {
          "kty": "RSA",
          "kid": "test-key-1",
          "use": "sig",
          "alg": "RS256",
          "n": jwt.encode.__globals__["base64url_encode"](
              public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")
          ).decode(),
          "e": jwt.encode.__globals__["base64url_encode"](
              public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")
          ).decode(),
      }
      return private_pem, jwk


  def _make_token(private_pem: str, kid: str, **claim_overrides) -> str:
      claims = {
          "aud": "test-client-id",
          "iss": "https://login.microsoftonline.com/some-tenant-id/v2.0",
          "oid": "user-oid-123",
          "name": "Test User",
          "preferred_username": "test@example.com",
          "exp": int(time.time()) + 3600,
          **claim_overrides,
      }
      return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


  async def test_valid_token_returns_access_token(monkeypatch, rsa_keypair):
      private_pem, jwk = rsa_keypair
      verifier = EntraTokenVerifier(expected_audience="test-client-id")

      async def fake_get_jwks():
          return {"keys": [jwk]}

      monkeypatch.setattr(verifier, "_get_jwks", fake_get_jwks)

      token = _make_token(private_pem, kid="test-key-1")
      result = await verifier.verify_token(token)

      assert result is not None
      assert result.subject == "user-oid-123"
      assert result.client_id == "test-client-id"


  async def test_wrong_audience_rejected(monkeypatch, rsa_keypair):
      private_pem, jwk = rsa_keypair
      verifier = EntraTokenVerifier(expected_audience="test-client-id")

      async def fake_get_jwks():
          return {"keys": [jwk]}

      monkeypatch.setattr(verifier, "_get_jwks", fake_get_jwks)

      token = _make_token(private_pem, kid="test-key-1", aud="some-other-app")
      result = await verifier.verify_token(token)

      assert result is None


  async def test_wrong_issuer_shape_rejected(monkeypatch, rsa_keypair):
      private_pem, jwk = rsa_keypair
      verifier = EntraTokenVerifier(expected_audience="test-client-id")

      async def fake_get_jwks():
          return {"keys": [jwk]}

      monkeypatch.setattr(verifier, "_get_jwks", fake_get_jwks)

      token = _make_token(private_pem, kid="test-key-1", iss="https://evil.example.com/v2.0")
      result = await verifier.verify_token(token)

      assert result is None


  async def test_missing_oid_claim_rejected(monkeypatch, rsa_keypair):
      private_pem, jwk = rsa_keypair
      verifier = EntraTokenVerifier(expected_audience="test-client-id")

      async def fake_get_jwks():
          return {"keys": [jwk]}

      monkeypatch.setattr(verifier, "_get_jwks", fake_get_jwks)

      token = _make_token(private_pem, kid="test-key-1", oid=None)
      del_token_claims = jwt.get_unverified_claims(token)
      del_token_claims.pop("oid", None)
      token = jwt.encode(del_token_claims, private_pem, algorithm="RS256", headers={"kid": "test-key-1"})

      result = await verifier.verify_token(token)

      assert result is None
  ```

  Note: `python-jose`'s public JWK export needs the raw `n`/`e` values base64url-encoded — `jwt.encode.__globals__["base64url_encode"]` reaches into jose's internals to reuse its own encoder rather than re-implementing base64url padding rules by hand. This is a test-only convenience, not something `auth.py` itself does.

- [ ] **Step 2: Run tests to verify they fail**

  Run: `.venv/Scripts/pytest tests/test_auth.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'auth'` (or `ImportError: cannot import name 'EntraTokenVerifier'`).

- [ ] **Step 3: Add `cryptography` as a test dependency**

  Add to `requirements.txt`:
  ```
  cryptography>=43.0
  ```
  Run: `.venv/Scripts/pip install -r requirements.txt`

- [ ] **Step 4: Write `auth.py`**

  ```python
  import time

  import httpx
  from jose import jwt
  from jose.exceptions import JWTError
  from mcp.server.auth.provider import AccessToken, TokenVerifier

  from config import settings


  class InvalidTokenError(Exception):
      pass


  class EntraTokenVerifier(TokenVerifier):
      """Validates inbound bearer tokens against Entra ID's multi-tenant
      JWKS. Unlike atlas-platform's single-tenant EntraJwtValidator, this
      accepts tokens issued by ANY Entra ID tenant (or a personal Microsoft
      account), since this connector is open to any Microsoft account —
      the audience check (not the issuer) is what actually restricts which
      tokens are accepted: only tokens issued FOR this specific app
      registration are valid, regardless of which tenant issued them.
      """

      def __init__(self, expected_audience: str, jwks_ttl_seconds: int = 3600) -> None:
          self._expected_audience = expected_audience
          self._jwks_ttl_seconds = jwks_ttl_seconds
          self._jwks_cache: dict | None = None
          self._jwks_fetched_at: float = 0.0

      async def _get_jwks(self) -> dict:
          now = time.monotonic()
          if self._jwks_cache is None or (now - self._jwks_fetched_at) > self._jwks_ttl_seconds:
              async with httpx.AsyncClient() as client:
                  response = await client.get(settings.entra_jwks_uri)
                  response.raise_for_status()
                  self._jwks_cache = response.json()
                  self._jwks_fetched_at = now
          return self._jwks_cache

      async def verify_token(self, token: str) -> AccessToken | None:
          try:
              claims = await self._validate(token)
          except InvalidTokenError:
              return None

          return AccessToken(
              token=token,
              client_id=self._expected_audience,
              scopes=[],
              subject=claims["oid"],
              claims=claims,
          )

      async def _validate(self, token: str) -> dict:
          jwks = await self._get_jwks()
          try:
              unverified_header = jwt.get_unverified_header(token)
              key = next(
                  (k for k in jwks["keys"] if k["kid"] == unverified_header.get("kid")),
                  None,
              )
              if key is None:
                  raise InvalidTokenError("Signing key not found in JWKS")

              claims = jwt.decode(
                  token,
                  key,
                  algorithms=["RS256"],
                  options={"verify_aud": False, "verify_iss": False},
              )
          except JWTError as exc:
              raise InvalidTokenError(str(exc)) from exc

          expected_audiences = {self._expected_audience, f"api://{self._expected_audience}"}
          if claims.get("aud") not in expected_audiences:
              raise InvalidTokenError(f"Unexpected audience: {claims.get('aud')!r}")

          issuer = claims.get("iss", "")
          if not issuer.startswith(settings.entra_issuer_prefix) or not issuer.endswith("/v2.0"):
              raise InvalidTokenError(f"Unexpected issuer shape: {issuer!r}")

          if not claims.get("oid"):
              raise InvalidTokenError("Token missing 'oid' claim")

          return claims
  ```

- [ ] **Step 5: Run tests to verify they pass**

  Run: `.venv/Scripts/pytest tests/test_auth.py -v`
  Expected: 4 passed.

- [ ] **Step 6: Commit**

  ```bash
  git add auth.py tests/test_auth.py requirements.txt
  git commit -m "Add multi-tenant token verification"
  ```

### Task 8: On-Behalf-Of Graph token exchange

**Files:**
- Create: `obo.py`
- Test: `tests/test_obo.py`

- [ ] **Step 1: Write the failing test**

  Create `tests/test_obo.py`:

  ```python
  import pytest

  from obo import ObTokenExchangeError, ObTokenProvider


  class FakeConfidentialClientApplication:
      def __init__(self, result: dict) -> None:
          self._result = result
          self.last_call: tuple | None = None

      def acquire_token_on_behalf_of(self, user_assertion, scopes):
          self.last_call = (user_assertion, tuple(scopes))
          return self._result


  async def test_successful_exchange_caches_token():
      app = FakeConfidentialClientApplication({"access_token": "graph-token-abc", "expires_in": 3600})
      provider = ObTokenProvider(confidential_app=app)

      token = await provider.get_graph_token(user_oid="user-1", user_assertion="raw-jwt")

      assert token == "graph-token-abc"
      assert app.last_call == ("raw-jwt", tuple(provider.graph_scopes))


  async def test_cached_token_skips_second_exchange():
      app = FakeConfidentialClientApplication({"access_token": "graph-token-abc", "expires_in": 3600})
      provider = ObTokenProvider(confidential_app=app)

      await provider.get_graph_token(user_oid="user-1", user_assertion="raw-jwt")
      app.last_call = None
      token = await provider.get_graph_token(user_oid="user-1", user_assertion="raw-jwt")

      assert token == "graph-token-abc"
      assert app.last_call is None  # cache hit, no second exchange


  async def test_failed_exchange_raises():
      app = FakeConfidentialClientApplication({"error": "invalid_grant", "error_description": "bad token"})
      provider = ObTokenProvider(confidential_app=app)

      with pytest.raises(ObTokenExchangeError):
          await provider.get_graph_token(user_oid="user-1", user_assertion="raw-jwt")
  ```

- [ ] **Step 2: Run test to verify it fails**

  Run: `.venv/Scripts/pytest tests/test_obo.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'obo'`.

- [ ] **Step 3: Write `obo.py`**

  Uses a plain in-process dict cache rather than Redis — this connector has no Redis dependency (unlike `atlas-platform`), and a single-replica, scale-to-zero Container App has no cross-instance cache-sharing need to justify adding one.

  ```python
  import time

  import msal

  from config import settings

  _EXPIRY_SAFETY_MARGIN_SECONDS = 60


  class ObTokenExchangeError(Exception):
      pass


  class ObTokenProvider:
      """Exchanges a validated Atlas MCP Connector token for a Graph-scoped
      token via On-Behalf-Of — same technique atlas-platform's
      MsalOboTokenProvider uses, reimplemented here since the two repos
      don't share code (see design doc's accepted-duplication decision).
      In-memory cache instead of Redis: this connector runs as a single
      replica with no cross-instance cache-sharing requirement."""

      graph_scopes = [
          "https://graph.microsoft.com/User.Read",
          "https://graph.microsoft.com/Mail.ReadWrite",
          "https://graph.microsoft.com/Mail.Send",
          "https://graph.microsoft.com/Calendars.ReadWrite",
      ]

      def __init__(self, confidential_app: msal.ConfidentialClientApplication | None = None) -> None:
          self._confidential_app = confidential_app or msal.ConfidentialClientApplication(
              client_id=settings.mcp_connector_client_id,
              client_credential=settings.mcp_connector_client_secret,
              authority=settings.entra_authority,
          )
          self._cache: dict[str, tuple[str, float]] = {}  # user_oid -> (token, expires_at_monotonic)

      async def get_graph_token(self, user_oid: str, user_assertion: str) -> str:
          cached = self._cache.get(user_oid)
          if cached and cached[1] > time.monotonic():
              return cached[0]

          result = self._confidential_app.acquire_token_on_behalf_of(
              user_assertion=user_assertion,
              scopes=self.graph_scopes,
          )

          if "access_token" not in result:
              error = result.get("error_description", result.get("error", "unknown error"))
              raise ObTokenExchangeError(f"On-Behalf-Of token exchange failed: {error}")

          access_token: str = result["access_token"]
          expires_in: int = result.get("expires_in", 3600)
          ttl = max(expires_in - _EXPIRY_SAFETY_MARGIN_SECONDS, 0)
          if ttl > 0:
              self._cache[user_oid] = (access_token, time.monotonic() + ttl)

          return access_token
  ```

- [ ] **Step 4: Run tests to verify they pass**

  Run: `.venv/Scripts/pytest tests/test_obo.py -v`
  Expected: 3 passed.

- [ ] **Step 5: Commit**

  ```bash
  git add obo.py tests/test_obo.py
  git commit -m "Add On-Behalf-Of Graph token exchange"
  ```

### Task 9: Blob storage client

**Files:**
- Create: `storage.py`

Direct copy of `atlas-platform`'s `AzureBlobStorageClient`, adjusted imports only — no behavior change, so no new test (the behavior is already covered by `atlas-platform`'s own test suite and this is a verbatim port).

- [ ] **Step 1: Write `storage.py`**

  ```python
  from azure.core.exceptions import ResourceExistsError
  from azure.identity import DefaultAzureCredential
  from azure.storage.blob.aio import BlobServiceClient

  from config import settings


  def _build_client() -> BlobServiceClient:
      if settings.azure_storage_connection_string:
          return BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
      return BlobServiceClient(account_url=settings.azure_storage_account_url, credential=DefaultAzureCredential())


  class AzureBlobStorageClient:
      def __init__(self) -> None:
          self._client = _build_client()

      async def upload(self, blob_path: str, content: bytes) -> None:
          container_client = self._client.get_container_client(settings.azure_storage_documents_container)
          try:
              await container_client.create_container()
          except ResourceExistsError:
              pass
          await container_client.upload_blob(name=blob_path, data=content, overwrite=True)
  ```

  Only `upload` is ported — this connector never deletes or downloads blobs (no delete-document or send-email-with-attachment tool here).

- [ ] **Step 2: Commit**

  ```bash
  git add storage.py
  git commit -m "Add blob storage client"
  ```

### Task 10: Document upload logic

**Files:**
- Create: `documents.py`
- Test: `tests/test_documents.py`

- [ ] **Step 1: Write the failing test**

  Create `tests/test_documents.py`:

  ```python
  import base64
  import uuid

  import pytest

  from documents import FileTooLargeError, UnsupportedFileTypeError, upload_document_from_base64


  class FakeDocumentRepository:
      def __init__(self) -> None:
          self.created: list[tuple] = []

      async def create_document(self, document_id, user_oid, filename, blob_path):
          self.created.append((document_id, user_oid, filename, blob_path))


  class FakeBlobStorageClient:
      def __init__(self) -> None:
          self.uploaded: list[tuple] = []

      async def upload(self, blob_path, content):
          self.uploaded.append((blob_path, content))


  async def test_valid_pdf_uploads_and_creates_row():
      repo = FakeDocumentRepository()
      blob = FakeBlobStorageClient()
      content_b64 = base64.b64encode(b"pdf bytes").decode()

      result_id = await upload_document_from_base64(
          user_oid="user-1", filename="resume.pdf", content_base64=content_b64,
          document_repository=repo, blob_storage_client=blob,
      )

      uuid.UUID(result_id)  # must be a real UUID
      assert len(blob.uploaded) == 1
      blob_path, content = blob.uploaded[0]
      assert content == b"pdf bytes"
      assert blob_path == f"user-1/{result_id}-resume.pdf"
      assert repo.created == [(result_id, "user-1", "resume.pdf", blob_path)]


  async def test_rejects_unsupported_extension():
      repo = FakeDocumentRepository()
      blob = FakeBlobStorageClient()
      content_b64 = base64.b64encode(b"MZ...").decode()

      with pytest.raises(UnsupportedFileTypeError):
          await upload_document_from_base64(
              user_oid="user-1", filename="malware.exe", content_base64=content_b64,
              document_repository=repo, blob_storage_client=blob,
          )
      assert blob.uploaded == []


  async def test_rejects_oversized_file():
      repo = FakeDocumentRepository()
      blob = FakeBlobStorageClient()
      oversized = base64.b64encode(b"x" * (20 * 1024 * 1024 + 1)).decode()

      with pytest.raises(FileTooLargeError):
          await upload_document_from_base64(
              user_oid="user-1", filename="big.pdf", content_base64=oversized,
              document_repository=repo, blob_storage_client=blob,
          )
      assert blob.uploaded == []
  ```

- [ ] **Step 2: Run test to verify it fails**

  Run: `.venv/Scripts/pytest tests/test_documents.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'documents'`.

- [ ] **Step 3: Write `documents.py`**

  Same validation rules as `atlas-platform`'s `UploadDocumentUseCase` (`app/application/upload_document.py`) — same allowed extensions, same 20MB cap — reimplemented here as a plain function rather than a class, since this connector has no dependency-injection framework wiring it up.

  ```python
  import base64
  import uuid

  _ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heif", ".heic"}
  _MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


  class UnsupportedFileTypeError(Exception):
      pass


  class FileTooLargeError(Exception):
      pass


  async def upload_document_from_base64(
      user_oid: str,
      filename: str,
      content_base64: str,
      document_repository,
      blob_storage_client,
  ) -> str:
      extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
      if extension not in _ALLOWED_EXTENSIONS:
          raise UnsupportedFileTypeError(extension or "(no extension)")

      content = base64.b64decode(content_base64)
      if len(content) > _MAX_UPLOAD_BYTES:
          raise FileTooLargeError(len(content))

      document_id = str(uuid.uuid4())
      blob_path = f"{user_oid}/{document_id}-{filename}"
      await blob_storage_client.upload(blob_path, content)
      await document_repository.create_document(document_id, user_oid, filename, blob_path)
      return document_id
  ```

- [ ] **Step 4: Run tests to verify they pass**

  Run: `.venv/Scripts/pytest tests/test_documents.py -v`
  Expected: 3 passed.

- [ ] **Step 5: Commit**

  ```bash
  git add documents.py tests/test_documents.py
  git commit -m "Add upload_document logic"
  ```

### Task 11: Preference repository

**Files:**
- Create: `preferences.py`

Direct port of `atlas-platform`'s `SqlAlchemyPreferenceRepository` — no behavior change, no new test (already covered upstream).

- [ ] **Step 1: Write `preferences.py`**

  ```python
  from sqlalchemy.dialects.postgresql import insert
  from sqlalchemy.ext.asyncio import AsyncSession

  from models import PreferenceModel


  class PreferenceRepository:
      def __init__(self, session: AsyncSession) -> None:
          self._session = session

      async def set_preference(self, user_oid: str, key: str, value: str) -> None:
          statement = insert(PreferenceModel).values(user_oid=user_oid, key=key, value=value)
          statement = statement.on_conflict_do_update(
              constraint="uq_preferences_user_oid_key",
              set_={"value": statement.excluded.value},
          )
          await self._session.execute(statement)
          await self._session.commit()
  ```

  Only `set_preference` is ported — this connector's `remember_preference` tool only ever writes (same as `atlas-platform`'s own `memory_server.py`, which deliberately doesn't expose a read tool either — see that file's module docstring).

- [ ] **Step 2: Commit**

  ```bash
  git add preferences.py
  git commit -m "Add preference repository"
  ```

### Task 12: Graph mail and calendar clients

**Files:**
- Create: `graph_mail.py`
- Create: `graph_calendar.py`

Direct ports of `atlas-platform`'s `HttpxGraphMailClient`/`HttpxGraphCalendarClient` — trimmed to the methods this connector's tools actually call, no retry decorator (that dependency, `tenacity`, isn't in this repo's `requirements.txt`; acceptable simplification for a demo-scope service per the design doc's non-goals). No new tests — these are thin HTTP wrappers with no branching logic beyond what `atlas-platform`'s own test suite already implicitly exercises via its MCP-server-level tests.

- [ ] **Step 1: Write `graph_mail.py`**

  ```python
  import httpx

  _GRAPH_BASE = "https://graph.microsoft.com/v1.0"


  def _auth_header(access_token: str) -> dict[str, str]:
      return {"Authorization": f"Bearer {access_token}"}


  class GraphMailClient:
      async def list_recent_emails(self, access_token: str, top: int, unread_only: bool) -> list[dict]:
          params: dict[str, str | int] = {
              "$top": top,
              "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
              "$orderby": "receivedDateTime desc",
          }
          if unread_only:
              params["$filter"] = "isRead eq false"

          async with httpx.AsyncClient() as client:
              response = await client.get(f"{_GRAPH_BASE}/me/messages", params=params, headers=_auth_header(access_token))
              response.raise_for_status()
              data = response.json()

          return [self._to_summary(item) for item in data.get("value", [])]

      async def search_emails(self, access_token: str, query: str, top: int) -> list[dict]:
          headers = _auth_header(access_token) | {"ConsistencyLevel": "eventual"}
          params: dict[str, str | int] = {
              "$search": f'"{query}"',
              "$top": top,
              "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
          }

          async with httpx.AsyncClient() as client:
              response = await client.get(f"{_GRAPH_BASE}/me/messages", params=params, headers=headers)
              response.raise_for_status()
              data = response.json()

          return [self._to_summary(item) for item in data.get("value", [])]

      async def get_email(self, access_token: str, message_id: str) -> dict:
          async with httpx.AsyncClient() as client:
              response = await client.get(
                  f"{_GRAPH_BASE}/me/messages/{message_id}", headers=_auth_header(access_token)
              )
              response.raise_for_status()
              data = response.json()

          return {
              "id": data["id"],
              "subject": data.get("subject", ""),
              "from_address": self._extract_address(data.get("from")),
              "received_at": data.get("receivedDateTime"),
              "body": data.get("body", {}).get("content", ""),
          }

      async def send_email(self, access_token: str, to: str, subject: str, body: str) -> None:
          message = {
              "subject": subject,
              "body": {"contentType": "Text", "content": body},
              "toRecipients": [{"emailAddress": {"address": to}}],
          }
          async with httpx.AsyncClient() as client:
              response = await client.post(
                  f"{_GRAPH_BASE}/me/sendMail",
                  headers=_auth_header(access_token),
                  json={"message": message, "saveToSentItems": True},
              )
              response.raise_for_status()

      @staticmethod
      def _extract_address(from_field: dict | None) -> str | None:
          if not from_field:
              return None
          return from_field.get("emailAddress", {}).get("address")

      @classmethod
      def _to_summary(cls, item: dict) -> dict:
          return {
              "id": item["id"],
              "subject": item.get("subject", ""),
              "from_address": cls._extract_address(item.get("from")),
              "received_at": item.get("receivedDateTime"),
              "is_read": item.get("isRead", False),
              "preview": item.get("bodyPreview", ""),
          }
  ```

  Note: no attachment support in `send_email` here — this connector's email tool is send-only-with-text, matching only what's needed for a working demo; `atlas-platform`'s attachment-via-blob-lookup logic isn't ported since it depends on that repo's own document/blob wiring, which this connector's `upload_document` tool doesn't currently cross-wire into email sending. (Real limitation, acceptable per design doc scope.)

- [ ] **Step 2: Write `graph_calendar.py`**

  ```python
  from datetime import datetime, timedelta, timezone

  import httpx

  _GRAPH_EVENTS_URL = "https://graph.microsoft.com/v1.0/me/events"
  _GRAPH_CALENDAR_VIEW_URL = "https://graph.microsoft.com/v1.0/me/calendarView"
  _GRAPH_GET_SCHEDULE_URL = "https://graph.microsoft.com/v1.0/me/calendar/getSchedule"
  _UPCOMING_WINDOW_DAYS = 30


  def _iso(dt: datetime) -> str:
      return dt.strftime("%Y-%m-%dT%H:%M:%S")


  class GraphCalendarClient:
      async def create_event(
          self, access_token: str, subject: str, start: str, end: str, attendees: list[str]
      ) -> dict:
          body = {
              "subject": subject,
              "start": {"dateTime": start, "timeZone": "UTC"},
              "end": {"dateTime": end, "timeZone": "UTC"},
              "attendees": [{"emailAddress": {"address": a}, "type": "required"} for a in attendees],
          }
          async with httpx.AsyncClient() as client:
              response = await client.post(
                  _GRAPH_EVENTS_URL, headers={"Authorization": f"Bearer {access_token}"}, json=body
              )
              response.raise_for_status()
              data = response.json()

          return {"id": data["id"], "subject": data.get("subject", subject), "start": start, "end": end}

      async def list_upcoming_events(self, access_token: str, top: int) -> list[dict]:
          now = datetime.now(timezone.utc)
          params: dict[str, str | int] = {
              "startDateTime": _iso(now),
              "endDateTime": _iso(now + timedelta(days=_UPCOMING_WINDOW_DAYS)),
              "$top": top,
              "$select": "id,subject,start,end",
              "$orderby": "start/dateTime",
          }
          async with httpx.AsyncClient() as client:
              response = await client.get(
                  _GRAPH_CALENDAR_VIEW_URL, params=params, headers={"Authorization": f"Bearer {access_token}"}
              )
              response.raise_for_status()
              data = response.json()

          return [
              {
                  "id": item["id"],
                  "subject": item.get("subject", ""),
                  "start": item.get("start", {}).get("dateTime", ""),
                  "end": item.get("end", {}).get("dateTime", ""),
              }
              for item in data.get("value", [])
          ]

      async def update_event(
          self, access_token: str, event_id: str, subject: str | None, start: str | None, end: str | None
      ) -> dict:
          body: dict = {}
          if subject is not None:
              body["subject"] = subject
          if start is not None:
              body["start"] = {"dateTime": start, "timeZone": "UTC"}
          if end is not None:
              body["end"] = {"dateTime": end, "timeZone": "UTC"}

          async with httpx.AsyncClient() as client:
              response = await client.patch(
                  f"{_GRAPH_EVENTS_URL}/{event_id}", headers={"Authorization": f"Bearer {access_token}"}, json=body
              )
              response.raise_for_status()
              data = response.json()

          return {
              "id": data["id"],
              "subject": data.get("subject", ""),
              "start": data.get("start", {}).get("dateTime", ""),
              "end": data.get("end", {}).get("dateTime", ""),
          }

      async def cancel_event(self, access_token: str, event_id: str) -> None:
          async with httpx.AsyncClient() as client:
              response = await client.post(
                  f"{_GRAPH_EVENTS_URL}/{event_id}/cancel",
                  headers={"Authorization": f"Bearer {access_token}"},
                  json={},
              )
              response.raise_for_status()

      async def get_free_busy(self, access_token: str, emails: list[str], start: str, end: str) -> list[dict]:
          body = {
              "schedules": emails,
              "startTime": {"dateTime": start, "timeZone": "UTC"},
              "endTime": {"dateTime": end, "timeZone": "UTC"},
              "availabilityViewInterval": 60,
          }
          async with httpx.AsyncClient() as client:
              response = await client.post(
                  _GRAPH_GET_SCHEDULE_URL, headers={"Authorization": f"Bearer {access_token}"}, json=body
              )
              response.raise_for_status()
              data = response.json()

          results = []
          for schedule in data.get("value", []):
              busy_periods = [
                  {
                      "status": item.get("status", "busy"),
                      "start": item.get("start", {}).get("dateTime", ""),
                      "end": item.get("end", {}).get("dateTime", ""),
                  }
                  for item in schedule.get("scheduleItems", [])
              ]
              results.append({"email": schedule.get("scheduleId", ""), "busy_periods": busy_periods})
          return results
  ```

  Note: unlike `atlas-platform`, this connector's calendar tools call Graph **directly on every request** — there is no propose-then-confirm step, since there is no separate web UI here for a human to review a draft before it's sent. This is a deliberate, real difference from `atlas-platform`'s safety model, called out explicitly in Task 14's tool docstrings so it's visible to whoever connects, not silently different behavior.

- [ ] **Step 3: Commit**

  ```bash
  git add graph_mail.py graph_calendar.py
  git commit -m "Add Graph mail and calendar clients"
  ```

### Task 13: Document search (RAG)

**Files:**
- Create: `search.py`

Direct port of `atlas-platform`'s `docs_server.py` search logic, restructured as a plain async function taking `user_oid`/`access_token`-equivalent explicitly rather than reading `USER_OID` from an environment variable (this connector derives it from the validated request, not a spawned subprocess's env).

- [ ] **Step 1: Write `search.py`**

  ```python
  from azure.core.credentials import AzureKeyCredential
  from azure.identity.aio import DefaultAzureCredential
  from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential, get_bearer_token_provider
  from azure.search.documents.aio import SearchClient
  from azure.search.documents.models import VectorizedQuery
  from openai import AsyncAzureOpenAI

  from config import settings

  _COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


  def _build_search_client() -> SearchClient:
      credential = (
          AzureKeyCredential(settings.azure_search_api_key)
          if settings.azure_search_api_key
          else DefaultAzureCredential()
      )
      return SearchClient(
          endpoint=settings.azure_search_endpoint,
          index_name=settings.azure_search_index_name,
          credential=credential,
      )


  def _build_openai_client() -> AsyncAzureOpenAI:
      if settings.azure_openai_api_key:
          return AsyncAzureOpenAI(
              azure_endpoint=settings.azure_openai_endpoint,
              api_key=settings.azure_openai_api_key,
              api_version=settings.azure_openai_api_version,
          )
      token_provider = get_bearer_token_provider(SyncDefaultAzureCredential(), _COGNITIVE_SERVICES_SCOPE)
      return AsyncAzureOpenAI(
          azure_endpoint=settings.azure_openai_endpoint,
          azure_ad_token_provider=token_provider,
          api_version=settings.azure_openai_api_version,
      )


  async def search_documents(user_oid: str, query: str, top: int = 5) -> list[dict]:
      openai_client = _build_openai_client()
      try:
          embedding_response = await openai_client.embeddings.create(
              model=settings.azure_openai_embedding_deployment, input=query
          )
          query_vector = embedding_response.data[0].embedding
      finally:
          await openai_client.close()

      search_client = _build_search_client()
      try:
          vector_query = VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="content_vector")
          results = await search_client.search(
              search_text=None,
              vector_queries=[vector_query],
              filter=f"user_oid eq '{user_oid}'",
              select=["filename", "chunk_text"],
              top=top,
          )
          return [{"filename": r["filename"], "chunk_text": r["chunk_text"]} async for r in results]
      finally:
          await search_client.close()
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add search.py
  git commit -m "Add document search"
  ```

### Task 14: The FastMCP server itself

**Files:**
- Create: `server.py`

This wires together every piece from Tasks 5–13 into the actual MCP server: tool definitions, per-request identity/token extraction, and the OAuth resource-server settings.

- [ ] **Step 1: Write `server.py`**

  ```python
  from mcp.server.auth.settings import AuthSettings
  from mcp.server.fastmcp import Context, FastMCP

  from auth import EntraTokenVerifier
  from config import settings
  from database import async_session_factory
  from documents import FileTooLargeError, UnsupportedFileTypeError, upload_document_from_base64
  from graph_calendar import GraphCalendarClient
  from graph_mail import GraphMailClient
  from models import DocumentModel
  from obo import ObTokenProvider
  from preferences import PreferenceRepository
  from search import search_documents as _search_documents
  from storage import AzureBlobStorageClient

  _token_verifier = EntraTokenVerifier(expected_audience=settings.mcp_connector_client_id)
  _obo_provider = ObTokenProvider()
  _mail_client = GraphMailClient()
  _calendar_client = GraphCalendarClient()
  _blob_client = AzureBlobStorageClient()

  mcp = FastMCP(
      "atlas",
      token_verifier=_token_verifier,
      auth=AuthSettings(
          issuer_url=settings.entra_authority,
          resource_server_url=settings.mcp_server_public_url,
      ),
  )


  def _identity(ctx: Context) -> tuple[str, str]:
      """Every tool needs both the caller's user_oid (for docs/memory
      isolation) and their raw token (to exchange via OBO for Graph calls).
      FastMCP puts the AccessToken our TokenVerifier returned on the request
      context — this pulls both out of it in one place instead of repeating
      the same two lines in every tool below."""
      access_token = ctx.request_context.request.state.access_token if hasattr(
          ctx.request_context.request.state, "access_token"
      ) else None
      # FastMCP's streamable-http transport attaches the verified AccessToken
      # to the ASGI request state under this exact key — see mcp.server.auth
      # middleware. subject is the oid claim; token is the raw bearer string
      # this connector received, which is what OBO needs as user_assertion.
      if access_token is None:
          raise RuntimeError("No authenticated request context — this should be unreachable given auth=...")
      return access_token.subject, access_token.token


  @mcp.tool()
  async def list_recent_emails(ctx: Context, top: int = 5, unread_only: bool = True) -> list[dict]:
      """List the user's most recent emails, optionally filtered to unread only."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _mail_client.list_recent_emails(graph_token, top=top, unread_only=unread_only)


  @mcp.tool()
  async def search_emails(ctx: Context, query: str, top: int = 10) -> list[dict]:
      """Full-text search the user's mailbox by keyword."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _mail_client.search_emails(graph_token, query=query, top=top)


  @mcp.tool()
  async def read_email(ctx: Context, message_id: str) -> dict:
      """Read the full subject and body of one email by its id."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _mail_client.get_email(graph_token, message_id)


  @mcp.tool()
  async def send_email(ctx: Context, to: str, subject: str, body: str) -> str:
      """Send an email immediately. Unlike the Atlas web app, there is no
      separate confirmation step here — calling this tool sends the email
      right away. Only call it once you and the user are both sure."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      await _mail_client.send_email(graph_token, to=to, subject=subject, body=body)
      return "sent"


  @mcp.tool()
  async def list_calendar_events(ctx: Context, top: int = 10) -> list[dict]:
      """List the user's upcoming calendar events (next 30 days), soonest first."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _calendar_client.list_upcoming_events(graph_token, top=top)


  @mcp.tool()
  async def create_calendar_event(
      ctx: Context, subject: str, start: str, end: str, attendees: list[str] | None = None
  ) -> dict:
      """Create a calendar event immediately. Unlike the Atlas web app,
      there is no separate confirmation step — this creates the event and
      notifies attendees right away."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _calendar_client.create_event(
          graph_token, subject=subject, start=start, end=end, attendees=attendees or []
      )


  @mcp.tool()
  async def reschedule_calendar_event(
      ctx: Context, event_id: str, subject: str | None = None, start: str | None = None, end: str | None = None
  ) -> dict:
      """Change an existing event's subject/start/end immediately. event_id
      must come from list_calendar_events, never invented."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _calendar_client.update_event(graph_token, event_id, subject, start, end)


  @mcp.tool()
  async def cancel_calendar_event(ctx: Context, event_id: str) -> str:
      """Cancel an existing event immediately, notifying attendees. event_id
      must come from list_calendar_events, never invented."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      await _calendar_client.cancel_event(graph_token, event_id)
      return "cancelled"


  @mcp.tool()
  async def check_free_busy(ctx: Context, emails: list[str], start: str, end: str) -> list[dict]:
      """Check whether the given people are busy between start and end."""
      user_oid, raw_token = _identity(ctx)
      graph_token = await _obo_provider.get_graph_token(user_oid, raw_token)
      return await _calendar_client.get_free_busy(graph_token, emails=emails, start=start, end=end)


  @mcp.tool()
  async def search_documents(ctx: Context, query: str, top: int = 5) -> list[dict]:
      """Search the user's uploaded documents for content relevant to the
      query. Returns empty for a user who's never called upload_document."""
      user_oid, _ = _identity(ctx)
      return await _search_documents(user_oid, query, top=top)


  class _SessionDocumentRepository:
      """Adapts a single SQLAlchemy session to the document_repository
      duck-type upload_document_from_base64 expects — exists only for this
      one call site, not a general-purpose repository abstraction."""

      def __init__(self, session) -> None:
          self._session = session

      async def create_document(self, document_id, user_oid, filename, blob_path) -> None:
          self._session.add(
              DocumentModel(
                  id=document_id, user_oid=user_oid, filename=filename, blob_path=blob_path, status="processing"
              )
          )
          await self._session.commit()


  @mcp.tool()
  async def upload_document(ctx: Context, filename: str, content_base64: str) -> str:
      """Upload a document (PDF, JPEG, PNG, BMP, TIFF, or HEIF, up to 20MB)
      so it becomes searchable via search_documents. content_base64 is the
      raw file content, base64-encoded. Processing (OCR, indexing) happens
      in the background — search_documents may not find it for a minute or
      two after this returns."""
      user_oid, _ = _identity(ctx)
      async with async_session_factory() as session:
          try:
              document_id = await upload_document_from_base64(
                  user_oid=user_oid,
                  filename=filename,
                  content_base64=content_base64,
                  document_repository=_SessionDocumentRepository(session),
                  blob_storage_client=_blob_client,
              )
          except UnsupportedFileTypeError as exc:
              return f"error: unsupported file type {exc}"
          except FileTooLargeError:
              return "error: file exceeds the 20MB upload limit"

      return f"uploaded: {document_id}"


  @mcp.tool()
  async def remember_preference(ctx: Context, key: str, value: str) -> str:
      """Remember a durable user preference or fact for future conversations.
      Use a short snake_case key, e.g. key="reply_style", value="concise"."""
      user_oid, _ = _identity(ctx)
      async with async_session_factory() as session:
          repository = PreferenceRepository(session)
          await repository.set_preference(user_oid, key, value)
      return f"Remembered: {key} = {value}"


  if __name__ == "__main__":
      mcp.run(transport="streamable-http")
  ```

  The `upload_document` tool's inline `_SessionDocumentRepository` is intentionally minimal rather than a separate `documents_repository.py` module — it exists only to give `upload_document_from_base64` (Task 10) something matching its `document_repository` duck-typed parameter without introducing a full repository abstraction for a single call site.

- [ ] **Step 2: Fix Task 5's `.env.example` reference**

  Re-check `config.py`'s `mcp_server_public_url` default (`http://localhost:8100`) matches what you'll actually run locally in Step 3 below.

- [ ] **Step 3: Run the server locally**

  Ensure `.env` (copied from `.env.example` in Task 4) has real `DATABASE_URL`, `MCP_CONNECTOR_CLIENT_ID`, `MCP_CONNECTOR_CLIENT_SECRET` filled in (values from Task 3), then:

  ```bash
  .venv/Scripts/python server.py
  ```
  Expected: starts without exceptions, logs something like "Uvicorn running on http://127.0.0.1:8000" (FastMCP's default streamable-http bind — override via `mcp.settings.port`/`host` if you need 8100 specifically to match `.env`).

- [ ] **Step 4: Verify the OAuth metadata endpoint**

  In a second terminal:
  ```bash
  curl http://127.0.0.1:8000/.well-known/oauth-protected-resource
  ```
  Expected: a JSON body referencing `authorization_servers` pointing at `https://login.microsoftonline.com/common` — confirms FastMCP correctly published the metadata from the `AuthSettings` you configured, without you hand-writing that route.

- [ ] **Step 5: Run the full test suite**

  Run: `.venv/Scripts/pytest -v`
  Expected: all tests from Tasks 7, 8, 10 pass (10 total).

- [ ] **Step 6: Commit**

  ```bash
  git add server.py
  git commit -m "Wire up the FastMCP server: all tools, auth, OBO"
  ```

### Task 15: Containerize and deploy

**Files:**
- Create: `Dockerfile`
- Create: `infra/main.bicep`
- Create: `azure.yaml`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `Dockerfile`**

  ```dockerfile
  FROM python:3.12-slim

  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .

  ENV PORT=8000
  EXPOSE 8000

  CMD ["python", "server.py"]
  ```

- [ ] **Step 2: Write `infra/main.bicep`**

  Looks up the *existing* Container Apps Environment (created by `atlas-platform`'s own Bicep) by name rather than provisioning a new one — this is what "same environment/VNet" from the design doc actually means in Bicep terms.

  ```bicep
  @description('Name of the existing Container Apps Environment created by atlas-platform')
  param existingEnvironmentName string

  @description('Resource group where atlas-platform\'s Container Apps Environment lives')
  param platformResourceGroup string

  @description('Container registry login server (reuse atlas-platform\'s ACR)')
  param containerRegistryLoginServer string

  param location string = resourceGroup().location
  param imageTag string = 'latest'

  @secure()
  param databaseUrl string
  @secure()
  param mcpConnectorClientSecret string
  param mcpConnectorClientId string
  param azureStorageAccountUrl string
  param azureSearchEndpoint string
  param azureOpenAiEndpoint string

  resource existingEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
    name: existingEnvironmentName
    scope: resourceGroup(platformResourceGroup)
  }

  resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
    name: 'id-mcp-connector'
    location: location
  }

  resource mcpConnectorApp 'Microsoft.App/containerApps@2024-03-01' = {
    name: 'ca-mcp-connector'
    location: location
    identity: {
      type: 'UserAssigned'
      userAssignedIdentities: {
        '${identity.id}': {}
      }
    }
    properties: {
      environmentId: existingEnvironment.id
      configuration: {
        ingress: {
          external: true
          targetPort: 8000
        }
        registries: [
          {
            server: containerRegistryLoginServer
            identity: identity.id
          }
        ]
      }
      template: {
        containers: [
          {
            name: 'mcp-connector'
            image: '${containerRegistryLoginServer}/atlas-mcp-connector:${imageTag}'
            resources: {
              cpu: json('0.25')
              memory: '0.5Gi'
            }
            env: [
              { name: 'DATABASE_URL', value: databaseUrl }
              { name: 'MCP_CONNECTOR_CLIENT_ID', value: mcpConnectorClientId }
              { name: 'MCP_CONNECTOR_CLIENT_SECRET', value: mcpConnectorClientSecret }
              { name: 'AZURE_STORAGE_ACCOUNT_URL', value: azureStorageAccountUrl }
              { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
              { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
              { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            ]
          }
        ]
        scale: {
          minReplicas: 0
          maxReplicas: 1
        }
      }
    }
  }

  output MCP_CONNECTOR_URI string = 'https://${mcpConnectorApp.properties.configuration.ingress.fqdn}'
  ```

  Note: this Bicep does not create RBAC role assignments for `identity` against the existing Storage/Search/Postgres resources — those must be granted manually once (Portal → each resource → Access control (IAM) → assign the same roles `atlas-platform`'s own API identity has, to this new `id-mcp-connector` identity), since those resources live in `atlas-platform`'s resource group and this Bicep template intentionally doesn't reach across resource groups to modify them.

- [ ] **Step 3: Write `azure.yaml`**

  ```yaml
  name: atlas-mcp-connector
  services:
    mcp-connector:
      project: .
      language: python
      host: containerapp
      docker:
        path: Dockerfile
  ```

- [ ] **Step 4: Write `.github/workflows/ci.yml`**

  Mirrors `atlas-platform`'s backend job (lint + test) — no separate deploy job in this first version; deployment is manual (`azd up`) until this repo has proven it works at least once.

  ```yaml
  name: CI

  on:
    push:
      branches: [master]
    pull_request:
      branches: [master]

  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: '3.12'
        - run: pip install -r requirements.txt
        - run: ruff check .
        - run: pytest -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add Dockerfile infra/main.bicep azure.yaml .github/workflows/ci.yml
  git commit -m "Add containerization, infra, and CI"
  ```

- [ ] **Step 6: Push the connector repo**

  ```bash
  git push -u origin master
  ```

- [ ] **Step 7: Manual first deploy**

  ```bash
  azd auth login
  azd init  # accept detected azure.yaml
  azd env new atlas-mcp-connector
  azd env set existingEnvironmentName <atlas-platform's Container Apps Environment name>
  azd env set platformResourceGroup <atlas-platform's resource group name>
  azd env set containerRegistryLoginServer <atlas-platform's ACR login server>
  azd up
  ```
  When prompted for the remaining Bicep parameters (`databaseUrl`, `mcpConnectorClientId`, `mcpConnectorClientSecret`, `azureStorageAccountUrl`, `azureSearchEndpoint`, `azureOpenAiEndpoint`), supply the same values you put in `.env` for Task 4/Task 3.
  Expected: `azd up` completes, prints the new Container App's URL.

- [ ] **Step 8: Grant the new identity access to shared resources**

  Portal → Storage account → Access control (IAM) → Add role assignment → same role `atlas-platform`'s API identity has (e.g. Storage Blob Data Contributor) → assign to `id-mcp-connector`. Repeat for the Azure AI Search resource (Search Index Data Reader is sufficient — this connector only reads/embeds-and-queries, never writes to the index) and for Postgres (add `id-mcp-connector`'s identity as an allowed Postgres AAD user, or fall back to password auth via `DATABASE_URL` if Postgres AAD auth isn't already set up for `atlas-platform` either).

- [ ] **Step 9: Update the Entra app registration's redirect URI**

  Now that you have the real Container App URL from Step 7, go back to the "Atlas MCP Connector" app registration (Task 3) → Authentication → Add a platform → Web → redirect URI `https://<container-app-url>/auth/callback` (or whatever exact callback path your MCP client's OAuth flow requests — check the specific client's docs, e.g. Claude Desktop's remote-MCP setup instructions, since this varies by client).

- [ ] **Step 10: End-to-end manual verification**

  Using whatever MCP client you have available (Claude Desktop's remote MCP connector settings, or the `mcp` Python SDK's own test client), point it at `https://<container-app-url>` and go through the sign-in flow. Confirm:
  - You're redirected to a real Microsoft login page.
  - After signing in and consenting, the client lists all 11 tools (`list_recent_emails`, `search_emails`, `read_email`, `send_email`, `list_calendar_events`, `create_calendar_event`, `reschedule_calendar_event`, `cancel_calendar_event`, `check_free_busy`, `search_documents`, `upload_document`, `remember_preference` — 12 total).
  - `list_recent_emails` returns your real inbox.
  - `upload_document` with a small test PDF, followed (after waiting ~1 minute for the existing background Function to process it) by `search_documents`, finds it.

---

## Self-review notes

- **Spec coverage:** auth flow (Task 3, 7, 8), tool surface incl. `upload_document` (Task 14), data model/isolation (Tasks 6, 11, 13, 14 — all keyed by `user_oid` from the validated token, never a tool argument), deployment/scale-to-zero (Task 15), repo structure + rename/OIDC migration risk (Tasks 1, 2). All covered.
- **Known, accepted gap vs. the design doc:** the design doc didn't specify whether remote calendar/email tools get a confirm-first step like `atlas-platform`'s propose/confirm pattern. This plan calls Graph directly with no confirmation step (Task 12/14), since there's no separate remote UI to confirm through — called out explicitly in each tool's docstring so it's visible behavior, not a silent gap. Flag this to the user before/during implementation in case they want a different answer here.
