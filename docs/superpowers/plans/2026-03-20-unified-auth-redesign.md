# Unified Auth Redesign — Self-Service API Key Provisioning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-env-var auth gate with DB-backed per-user API keys so users can self-provision keys through a first-run setup flow and the Settings UI.

**Architecture:** Remove `AGENTED_API_KEY` env var as the auth mechanism. Instead, the `_require_api_key` middleware validates `X-API-Key` against the existing `user_roles` table. A new public `/health/setup` endpoint generates the first admin key when no keys exist (bootstrap). The frontend shows a setup wizard on first run and integrates RBAC management into Settings.

**Tech Stack:** Flask + SQLite (existing), Vue 3 + TypeScript (existing), secrets module for key generation

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/__init__.py:339-369` | Replace env-var auth gate with DB-backed lookup |
| Modify | `backend/app/routes/health.py` | Add `/health/setup` endpoint, update `auth-status` and `verify-key` to use DB |
| Modify | `backend/app/db/rbac.py` | Add `get_user_role_by_api_key()` returning full record, add `generate_api_key()` |
| Modify | `backend/app/services/rbac_service.py` | Update `_is_authenticated_request` helper if shared |
| Modify | `backend/app/models/rbac.py` | Add `SetupRequest` model |
| Modify | `backend/tests/test_rbac.py` | Add tests for new auth flow |
| Create | `backend/tests/test_auth_setup.py` | Tests for setup endpoint and unified auth gate |
| Modify | `frontend/src/services/api/system.ts` | Add `setup()` API call |
| Modify | `frontend/src/components/layout/ApiKeyBanner.vue` | Add "Generate Key" flow for first-run |
| Modify | `frontend/src/views/SettingsPage.vue` | Add "Security" tab |
| Modify | `frontend/src/views/RbacSettingsPage.vue` | Add key generation button, integrate as Settings tab component |
| Modify | `frontend/src/App.vue` | Update auth check to handle setup mode |

---

## Task 1: Add `generate_api_key` helper and cache for `has_any_keys`

**Files:**
- Modify: `backend/app/db/rbac.py`
- Test: `backend/tests/test_rbac.py`

- [ ] **Step 1: Write failing tests for new DB functions**

In `backend/tests/test_rbac.py`, add:

```python
class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_api_key_returns_64_hex_chars(self):
        from app.db.rbac import generate_api_key
        key = generate_api_key()
        assert len(key) == 64
        assert all(c in '0123456789abcdef' for c in key)

    def test_generate_api_key_unique(self):
        from app.db.rbac import generate_api_key
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100


class TestHasAnyKeys:
    """Tests for cached has_any_keys check."""

    def test_false_when_empty(self, isolated_db):
        from app.db.rbac import has_any_keys, _has_any_keys_cache
        _has_any_keys_cache.clear()
        assert has_any_keys() is False

    def test_true_after_create(self, isolated_db):
        from app.db.rbac import has_any_keys, _has_any_keys_cache
        _has_any_keys_cache.clear()
        create_user_role("k1", "Admin", "admin")
        _has_any_keys_cache.clear()
        assert has_any_keys() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_rbac.py::TestGenerateApiKey tests/test_rbac.py::TestHasAnyKeys -v`
Expected: FAIL — functions don't exist

- [ ] **Step 3: Implement the functions**

In `backend/app/db/rbac.py`, add:

```python
import secrets
import time
import threading

def generate_api_key() -> str:
    """Generate a cryptographically secure 64-character hex API key."""
    return secrets.token_hex(32)


# Cache for has_any_keys() — avoids a DB query on every request.
# TTL of 5 seconds: after a key is created, it takes at most 5s for auth to kick in.
_has_any_keys_cache: dict = {}  # {"result": bool, "ts": float}
_HAS_ANY_KEYS_TTL = 5.0

def has_any_keys() -> bool:
    """Check if any API keys exist in the database. Cached with 5s TTL."""
    now = time.monotonic()
    cached = _has_any_keys_cache.get("result")
    ts = _has_any_keys_cache.get("ts", 0.0)
    if cached is not None and (now - ts) < _HAS_ANY_KEYS_TTL:
        return cached
    result = count_user_roles() > 0
    _has_any_keys_cache["result"] = result
    _has_any_keys_cache["ts"] = now
    return result


def invalidate_key_cache():
    """Clear the has_any_keys cache (call after creating/deleting keys)."""
    _has_any_keys_cache.clear()
```

Also update `create_user_role` and `delete_user_role` to call `invalidate_key_cache()` after their `conn.commit()` calls.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_rbac.py::TestGenerateApiKey tests/test_rbac.py::TestHasAnyKeys -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/rbac.py backend/tests/test_rbac.py
git commit -m "feat(auth): add generate_api_key helper and cached has_any_keys check"
```

---

## Task 2: Replace env-var auth gate with DB-backed lookup

**Files:**
- Modify: `backend/app/__init__.py:339-369`
- Create: `backend/tests/test_auth_setup.py`

- [ ] **Step 1: Write failing tests for the new auth gate**

Create `backend/tests/test_auth_setup.py`:

```python
"""Tests for unified DB-backed auth gate."""

from app.db.rbac import create_user_role, generate_api_key


class TestUnifiedAuthGate:
    """Auth gate uses user_roles table instead of env var."""

    def test_no_roles_in_db_allows_all_requests(self, client, isolated_db):
        """When no API keys exist, all requests pass (bootstrap mode)."""
        resp = client.get("/admin/triggers")
        assert resp.status_code != 401

    def test_with_roles_rejects_missing_key(self, client, isolated_db):
        """When keys exist, requests without X-API-Key are rejected."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/admin/triggers")
        assert resp.status_code == 401

    def test_with_roles_rejects_invalid_key(self, client, isolated_db):
        """When keys exist, invalid X-API-Key is rejected."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/admin/triggers", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_with_roles_accepts_valid_key(self, client, isolated_db):
        """When keys exist, valid X-API-Key is accepted."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/admin/triggers", headers={"X-API-Key": key})
        assert resp.status_code != 401

    def test_health_endpoints_bypass_auth(self, client, isolated_db):
        """Health endpoints always bypass auth."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        for path in ["/health/liveness", "/health/readiness", "/health/auth-status"]:
            resp = client.get(path)
            assert resp.status_code != 401, f"{path} should bypass auth"

    def test_docs_bypass_auth(self, client, isolated_db):
        """Docs endpoints bypass auth."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/docs")
        # docs may 404 but should not 401
        assert resp.status_code != 401

    def test_env_var_still_works_as_fallback(self, client, isolated_db, monkeypatch):
        """AGENTED_API_KEY env var still works for backward compat."""
        monkeypatch.setenv("AGENTED_API_KEY", "env-key-123")
        resp = client.get("/admin/triggers", headers={"X-API-Key": "env-key-123"})
        assert resp.status_code != 401
```

- [ ] **Step 2: Run tests to verify current behavior**

Run: `cd backend && uv run pytest tests/test_auth_setup.py -v`
Expected: Some pass (bootstrap), some fail (DB lookup not yet implemented)

- [ ] **Step 3: Rewrite `_require_api_key` in `__init__.py`**

Replace lines 339-369 in `backend/app/__init__.py`:

```python
    # Paths that bypass authentication (public endpoints)
    _AUTH_BYPASS_PREFIXES = ("/health", "/docs", "/openapi", "/api/webhooks/github")

    @app.before_request
    def _require_api_key():
        # Allow CORS preflight requests through
        if request.method == "OPTIONS":
            return None

        # Only enforce auth on /admin and /api routes
        if not (request.path.startswith("/admin") or request.path.startswith("/api")):
            return None

        # Bypass paths (specific /api sub-paths that are public)
        for prefix in _AUTH_BYPASS_PREFIXES:
            if request.path == prefix or request.path.startswith(prefix + "/"):
                return None

        # Bootstrap mode: no keys in DB and no env var = auth disabled
        from .db.rbac import has_any_keys, get_role_for_api_key
        db_has_keys = has_any_keys()
        env_key = os.environ.get("AGENTED_API_KEY", "")

        if not db_has_keys and not env_key:
            return None

        # Validate X-API-Key header
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key:
            return jsonify({"error": "Unauthorized"}), 401

        # Check DB first (primary), then env var (backward compat fallback)
        if db_has_keys and get_role_for_api_key(provided_key):
            return None

        if env_key and hmac.compare_digest(provided_key, env_key):
            return None

        return jsonify({"error": "Unauthorized"}), 401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_setup.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd backend && uv run pytest`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/__init__.py backend/tests/test_auth_setup.py
git commit -m "feat(auth): replace env-var auth gate with DB-backed user_roles lookup"
```

---

## Task 3: Add `/health/setup` endpoint for first-run key generation

**Files:**
- Modify: `backend/app/routes/health.py`
- Modify: `backend/app/models/rbac.py`
- Modify: `backend/tests/test_auth_setup.py`

- [ ] **Step 1: Write failing tests for setup endpoint**

Add to `backend/tests/test_auth_setup.py`:

```python
class TestSetupEndpoint:
    """POST /health/setup generates the first admin API key."""

    def test_setup_creates_admin_key_when_no_keys_exist(self, client, isolated_db):
        """First call creates admin key and returns it."""
        resp = client.post("/health/setup", json={"label": "My Admin Key"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert "api_key" in data
        assert len(data["api_key"]) == 64
        assert data["role"] == "admin"
        assert data["label"] == "My Admin Key"

    def test_setup_rejected_when_keys_exist(self, client, isolated_db):
        """Setup is locked after first key is created."""
        client.post("/health/setup", json={"label": "First"})
        resp = client.post("/health/setup", json={"label": "Second"})
        assert resp.status_code == 403
        data = resp.get_json()
        assert "already configured" in data["error"].lower()

    def test_setup_default_label(self, client, isolated_db):
        """Label defaults to 'Admin' when not provided."""
        resp = client.post("/health/setup", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["label"] == "Admin"

    def test_setup_key_works_for_auth(self, client, isolated_db):
        """The generated key can be used to authenticate."""
        setup_resp = client.post("/health/setup", json={"label": "Admin"})
        key = setup_resp.get_json()["api_key"]
        resp = client.get("/admin/triggers", headers={"X-API-Key": key})
        assert resp.status_code != 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_auth_setup.py::TestSetupEndpoint -v`
Expected: FAIL — endpoint doesn't exist

- [ ] **Step 3: Implement the setup endpoint**

Add to `backend/app/routes/health.py`:

```python
@health_bp.post("/setup")
def setup():
    """Public endpoint: generate the first admin API key.

    Only works when no API keys exist in the database (first-run bootstrap).
    Returns the generated key — this is the only time it will be shown.
    """
    from ..db.rbac import generate_api_key, invalidate_key_cache
    from ..db.connection import get_connection

    data = request.get_json(silent=True) or {}
    label = data.get("label", "Admin")

    api_key = generate_api_key()

    # Atomic check-and-insert to prevent race conditions
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0]
        if existing > 0:
            return {"error": "Already configured. Use the admin API to manage keys."}, 403

        from ..db.ids import _get_unique_role_id
        role_id = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, ?)",
            (role_id, api_key, label, "admin"),
        )
        conn.commit()

    invalidate_key_cache()

    if not role_id:
        return {"error": "Failed to create admin key"}, 500

    return {
        "api_key": api_key,
        "role_id": role_id,
        "role": "admin",
        "label": label,
        "message": "Admin API key created. Save this key — it will not be shown again.",
    }, 201
```

- [ ] **Step 4: Update `auth-status` to reflect DB state**

Replace the `auth_status` function in `backend/app/routes/health.py`:

```python
@health_bp.get("/auth-status")
def auth_status():
    """Public endpoint: tells the frontend whether auth is configured.

    Returns:
      - needs_setup: true when no API keys exist (first-run)
      - auth_required: true when keys exist and request isn't authenticated
      - authenticated: true when request carries a valid key
    """
    from ..db.rbac import has_any_keys

    has_db_keys = has_any_keys()
    env_key_set = bool(os.environ.get("AGENTED_API_KEY", ""))
    auth_configured = has_db_keys or env_key_set
    authenticated = _is_authenticated_request()

    return {
        "needs_setup": not auth_configured,
        "auth_required": auth_configured,
        "authenticated": authenticated,
    }, HTTPStatus.OK
```

- [ ] **Step 5: Update `_is_authenticated_request` to check DB**

Replace in `backend/app/routes/health.py`:

```python
def _is_authenticated_request() -> bool:
    """Check if request carries a valid API key (DB or env var)."""
    from ..db.rbac import has_any_keys, get_role_for_api_key

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return False

    # Check DB keys first
    if has_any_keys() and get_role_for_api_key(api_key):
        return True

    # Fallback: check env var
    secret = os.environ.get("AGENTED_API_KEY", "")
    if secret and hmac.compare_digest(api_key, secret):
        return True

    return False
```

- [ ] **Step 6: Update `verify-key` to check DB**

Replace the `verify_key` function:

```python
@health_bp.post("/verify-key")
def verify_key():
    """Public endpoint: verify whether a provided API key is valid."""
    from ..db.rbac import has_any_keys, get_role_for_api_key

    data = request.get_json(silent=True) or {}
    provided = data.get("api_key", "")

    if not provided:
        return {"valid": False, "message": "No key provided"}, HTTPStatus.OK

    # Check DB
    if has_any_keys() and get_role_for_api_key(provided):
        return {"valid": True, "message": "Valid"}, HTTPStatus.OK

    # Fallback: env var
    secret = os.environ.get("AGENTED_API_KEY", "")
    if secret and hmac.compare_digest(provided, secret):
        return {"valid": True, "message": "Valid"}, HTTPStatus.OK

    # No auth configured at all
    if not has_any_keys() and not secret:
        return {"valid": True, "message": "No authentication configured"}, HTTPStatus.OK

    return {"valid": False, "message": "Invalid API key"}, HTTPStatus.OK
```

- [ ] **Step 7: Run tests**

Run: `cd backend && uv run pytest tests/test_auth_setup.py -v`
Expected: ALL PASS

- [ ] **Step 8: Run full backend test suite**

Run: `cd backend && uv run pytest`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/routes/health.py backend/app/models/rbac.py backend/tests/test_auth_setup.py
git commit -m "feat(auth): add /health/setup endpoint and update auth-status to use DB"
```

---

## Task 4: Update frontend ApiKeyBanner for first-run setup

**Files:**
- Modify: `frontend/src/services/api/system.ts`
- Modify: `frontend/src/components/layout/ApiKeyBanner.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add `setup()` method to `healthApi`**

In `frontend/src/services/api/system.ts`, add to `healthApi`:

```typescript
  /** First-run setup: generate the initial admin API key. Public endpoint. */
  setup: (label?: string) =>
    apiFetch<{ api_key: string; role_id: string; role: string; label: string; message: string }>(
      '/health/setup',
      {
        method: 'POST',
        body: JSON.stringify({ label: label || 'Admin' }),
      }
    ),
```

- [ ] **Step 2: Rewrite `ApiKeyBanner.vue` to handle both modes**

Replace the full content of `frontend/src/components/layout/ApiKeyBanner.vue`:

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { healthApi, setApiKey } from '../../services/api';

const props = defineProps<{
  needsSetup: boolean;
}>();

const emit = defineEmits<{
  authenticated: [];
}>();

const apiKeyInput = ref('');
const error = ref<string | null>(null);
const verifying = ref(false);
const dismissed = ref(false);
const generatedKey = ref<string | null>(null);
const generating = ref(false);
const copied = ref(false);

async function submit() {
  const key = apiKeyInput.value.trim();
  if (!key) {
    error.value = 'Please enter an API key';
    return;
  }

  verifying.value = true;
  error.value = null;

  try {
    const result = await healthApi.verifyKey(key);
    if (result.valid) {
      setApiKey(key);
      emit('authenticated');
    } else {
      error.value = result.message || 'Invalid API key';
    }
  } catch {
    error.value = 'Failed to verify key. Is the backend running?';
  } finally {
    verifying.value = false;
  }
}

async function generateKey() {
  generating.value = true;
  error.value = null;

  try {
    const result = await healthApi.setup('Admin');
    generatedKey.value = result.api_key;
    setApiKey(result.api_key);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to generate key';
    error.value = message;
  } finally {
    generating.value = false;
  }
}

async function copyAndContinue() {
  if (generatedKey.value) {
    try {
      await navigator.clipboard.writeText(generatedKey.value);
      copied.value = true;
    } catch {
      // Clipboard API may fail in some contexts
    }
    setTimeout(() => {
      generatedKey.value = null;  // Clear from memory
      emit('authenticated');
    }, 300);
  }
}

function dismiss() {
  dismissed.value = true;
}
</script>

<template>
  <div v-if="!dismissed" class="api-key-banner" role="alert">
    <!-- First-run setup mode -->
    <template v-if="needsSetup && !generatedKey">
      <div class="banner-content">
        <div class="banner-icon setup-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
            <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <div class="banner-text">
          <strong>Welcome to Agented</strong>
          <span class="banner-description">No API keys configured. Generate your admin key to get started.</span>
        </div>
        <button class="banner-submit" :disabled="generating" @click="generateKey">
          {{ generating ? 'Generating...' : 'Generate Admin Key' }}
        </button>
      </div>
    </template>

    <!-- Key generated — show it once -->
    <template v-else-if="generatedKey">
      <div class="banner-content">
        <div class="banner-icon success-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div class="banner-text">
          <strong>Admin key created</strong>
          <span class="banner-description">Save this key — it will not be shown again.</span>
        </div>
        <code class="generated-key">{{ generatedKey }}</code>
        <button class="banner-submit" @click="copyAndContinue">
          {{ copied ? 'Copied! Continuing...' : 'Copy & Continue' }}
        </button>
      </div>
    </template>

    <!-- Normal auth mode — enter existing key -->
    <template v-else>
      <div class="banner-content">
        <div class="banner-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
          </svg>
        </div>
        <div class="banner-text">
          <strong>API key required</strong>
          <span class="banner-description">Enter your API key to continue.</span>
        </div>
        <form class="banner-form" @submit.prevent="submit">
          <input
            v-model="apiKeyInput"
            type="password"
            placeholder="Enter API key..."
            class="banner-input"
            autocomplete="off"
            :disabled="verifying"
          />
          <button type="submit" class="banner-submit" :disabled="verifying || !apiKeyInput.trim()">
            {{ verifying ? 'Verifying...' : 'Connect' }}
          </button>
        </form>
        <button class="banner-dismiss" @click="dismiss" aria-label="Dismiss">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </template>

    <div v-if="error" class="banner-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.api-key-banner {
  background: var(--surface-elevated, #1a1a2e);
  border-bottom: 1px solid var(--accent-amber, #f59e0b);
  padding: 10px 20px;
  z-index: 100;
}

.banner-content {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.banner-icon {
  color: var(--accent-amber, #f59e0b);
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.setup-icon {
  color: var(--accent-blue, #3b82f6);
}

.success-icon {
  color: var(--accent-green, #22c55e);
}

.banner-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: var(--text-primary, #e0e0e0);
  min-width: 0;
}

.banner-text strong {
  font-weight: 600;
}

.banner-description {
  color: var(--text-secondary, #999);
  font-size: 12px;
}

.generated-key {
  background: var(--surface-secondary, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 11px;
  color: var(--accent-green, #22c55e);
  font-family: 'GeistMono', monospace;
  word-break: break-all;
  max-width: 400px;
  user-select: all;
}

.banner-form {
  display: flex;
  gap: 8px;
  margin-left: auto;
  flex-shrink: 0;
}

.banner-input {
  background: var(--surface-secondary, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--text-primary, #e0e0e0);
  width: 220px;
  outline: none;
  transition: border-color 0.15s;
}

.banner-input:focus {
  border-color: var(--accent-amber, #f59e0b);
}

.banner-input::placeholder {
  color: var(--text-tertiary, #666);
}

.banner-submit {
  background: var(--accent-amber, #f59e0b);
  color: #000;
  border: none;
  border-radius: 6px;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s;
}

.banner-submit:hover:not(:disabled) {
  opacity: 0.9;
}

.banner-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.banner-dismiss {
  background: none;
  border: none;
  color: var(--text-tertiary, #666);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  transition: color 0.15s;
}

.banner-dismiss:hover {
  color: var(--text-primary, #e0e0e0);
}

.banner-error {
  color: var(--accent-crimson, #ef4444);
  font-size: 12px;
  margin-top: 6px;
  padding-left: 30px;
}
</style>
```

- [ ] **Step 3: Update `App.vue` auth check to pass `needsSetup` prop**

In `frontend/src/App.vue`, update the `checkAuthStatus` function and banner binding:

Update the `checkAuthStatus` function (around line 95-107):

```typescript
const showApiKeyBanner = ref(false);
const needsSetup = ref(false);

async function checkAuthStatus() {
  try {
    const status = await healthApi.authStatus();
    if (status.needs_setup) {
      needsSetup.value = true;
      showApiKeyBanner.value = true;
    } else if (status.auth_required && !status.authenticated && !getApiKey()) {
      needsSetup.value = false;
      showApiKeyBanner.value = true;
    }
  } catch {
    // Backend unreachable — don't show banner
  }
}
```

In the template, update the `ApiKeyBanner` usage (find the existing `<ApiKeyBanner` tag):

```vue
<ApiKeyBanner
  v-if="showApiKeyBanner"
  :needs-setup="needsSetup"
  @authenticated="onAuthenticated"
/>
```

- [ ] **Step 4: Run type check**

Run: `just build`
Expected: PASS (no TypeScript errors)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api/system.ts frontend/src/components/layout/ApiKeyBanner.vue frontend/src/App.vue
git commit -m "feat(auth): add first-run setup flow to ApiKeyBanner"
```

---

## Task 5: Add "Security" tab to Settings page with key management

**Files:**
- Modify: `frontend/src/views/SettingsPage.vue`
- Modify: `frontend/src/views/RbacSettingsPage.vue` (adapt as embedded component)

- [ ] **Step 1: Add "security" to the Settings tabs**

In `frontend/src/views/SettingsPage.vue`:

Update the `TAB_NAMES` array:
```typescript
const TAB_NAMES = ['general', 'security', 'marketplaces', 'harness', 'mcp', 'grd'] as const;
```

Add the import:
```typescript
import SecuritySettings from '../views/RbacSettingsPage.vue';
```

In the template, add the tab button (alongside other tab buttons in the tab bar):
```vue
<button
  :class="['tab-btn', { active: activeTab === 'security' }]"
  @click="activeTab = 'security'"
>
  Security
</button>
```

Add the tab panel (alongside other tab panels):
```vue
<SecuritySettings v-if="activeTab === 'security'" />
```

- [ ] **Step 2: Update RbacSettingsPage to work as embedded component**

In `frontend/src/views/RbacSettingsPage.vue`, add a "Generate New Key" button that auto-generates keys instead of requiring manual input.

Add a `generateNewKey` function:

```typescript
async function generateNewKey() {
  isCreating.value = true;
  try {
    const key = Array.from(crypto.getRandomValues(new Uint8Array(32)))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
    const result = await rbacApi.createRole({
      api_key: key,
      label: newLabel.value || 'New API Key',
      role: newRole.value,
    });
    showToast('API key created', 'success');
    generatedKeyDisplay.value = key;
    showCreateForm.value = false;
    newLabel.value = '';
    newRole.value = 'viewer';
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to create key';
    showToast(message, 'error');
  } finally {
    isCreating.value = false;
  }
}
```

Add `generatedKeyDisplay` ref and `copyKey` function:
```typescript
const generatedKeyDisplay = ref<string | null>(null);

async function copyKey() {
  if (generatedKeyDisplay.value) {
    try {
      await navigator.clipboard.writeText(generatedKeyDisplay.value);
      showToast('Key copied to clipboard', 'success');
    } catch {
      showToast('Failed to copy — select and copy manually', 'info');
    }
  }
}
```

Add a display section in the template after the create form:
```vue
<div v-if="generatedKeyDisplay" class="generated-key-notice">
  <strong>New API key created — copy it now:</strong>
  <code class="key-display">{{ generatedKeyDisplay }}</code>
  <button class="copy-btn" @click="copyKey">Copy</button>
  <button class="dismiss-btn" @click="generatedKeyDisplay = null">Dismiss</button>
</div>
```

- [ ] **Step 3: Run type check**

Run: `just build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/SettingsPage.vue frontend/src/views/RbacSettingsPage.vue
git commit -m "feat(auth): add Security tab to Settings with key management"
```

---

## Task 6: Add CLI command for key generation

**Files:**
- Modify: `backend/justfile` (add `generate-key` recipe)
- Create: `backend/scripts/generate_key.py`

- [ ] **Step 1: Create the CLI script**

Create `backend/scripts/generate_key.py`:

```python
"""Generate an admin API key for Agented.

Usage:
    cd backend && uv run python scripts/generate_key.py [--label LABEL]
"""

import argparse
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.migrations import init_db
from app.db.rbac import count_user_roles, create_user_role, generate_api_key


def main():
    parser = argparse.ArgumentParser(description="Generate an Agented API key")
    parser.add_argument("--label", default="Admin", help="Label for the key (default: Admin)")
    parser.add_argument("--role", default="admin", choices=["viewer", "operator", "editor", "admin"],
                        help="Role for the key (default: admin)")
    args = parser.parse_args()

    # Ensure DB is initialized
    init_db()

    key = generate_api_key()
    role_id = create_user_role(api_key=key, label=args.label, role=args.role)

    if not role_id:
        print("ERROR: Failed to create API key (duplicate?)", file=sys.stderr)
        sys.exit(1)

    print(f"\n  API Key:  {key}")
    print(f"  Role:     {args.role}")
    print(f"  Label:    {args.label}")
    print(f"  Role ID:  {role_id}")
    print(f"\n  Save this key — it will not be shown again.\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add justfile recipe**

In the root `justfile`, add:

```just
# Generate an admin API key
generate-key *ARGS: ensure-backend
    cd backend && uv run python scripts/generate_key.py {{ARGS}}
```

- [ ] **Step 3: Test manually**

Run: `just generate-key --label "Test Key"`
Expected: Prints a 64-char hex key with role info

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/generate_key.py justfile
git commit -m "feat(auth): add CLI command for API key generation"
```

---

## Task 7: Update existing RBAC tests for backward compatibility

**Files:**
- Modify: `backend/tests/test_rbac.py`
- Modify: `backend/tests/test_auth_setup.py`

- [ ] **Step 1: Run full test suite to identify failures**

Run: `cd backend && uv run pytest -v`
Expected: Some existing tests may fail due to auth gate changes

- [ ] **Step 2: Fix any broken tests**

Existing RBAC tests that set `AGENTED_API_KEY` via monkeypatch should still work since the env var fallback is preserved. If any tests break because they expect the old `_require_api_key` behavior, update them to use DB-backed keys instead.

Common fix pattern — if a test sets `AGENTED_API_KEY` and expects auth, it should still work. If a test creates `user_roles` entries, those now also gate access.

- [ ] **Step 3: Run full test suite**

Run: `cd backend && uv run pytest`
Expected: ALL PASS

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && npm run test:run`
Expected: ALL PASS

- [ ] **Step 5: Run type check**

Run: `just build`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "test(auth): update existing tests for unified auth gate"
```

---

## Summary of Changes

1. **DB layer** — Added `generate_api_key()` and `get_user_role_by_api_key()` to `rbac.py`
2. **Auth gate** — `_require_api_key` now checks `user_roles` table first, env var as fallback, bootstrap mode when neither exists
3. **Setup endpoint** — `POST /health/setup` generates first admin key (one-time, public)
4. **Health endpoints** — `auth-status` returns `needs_setup` flag, `verify-key` checks DB
5. **Frontend banner** — Shows "Generate Admin Key" on first run, "Enter key" when keys exist
6. **Settings UI** — Security tab with RBAC key management and auto-generation
7. **CLI** — `just generate-key` for headless key provisioning
8. **Backward compat** — `AGENTED_API_KEY` env var still works as fallback
