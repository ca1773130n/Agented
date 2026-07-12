# Vendored Swagger UI assets

Same-origin copy of **swagger-ui-dist `5.18.2`** (Apache-2.0), pinned to the
version Litestar 2.21's `SwaggerRenderPlugin` defaults to. Served at
`/schema-assets/*` and referenced by `app_litestar.main._openapi_config` so the
API docs page (`/schema/swagger`) loads no external CDN — keeping the app CSP
self-only (see `middleware._CSP_SCHEMA`).

Files: `swagger-ui-bundle.js`, `swagger-ui.css`, `swagger-ui-standalone-preset.js`.

## Refreshing (bump the version)

Update the version in `main._openapi_config` if the filenames/URLs change, then
re-download the three files, e.g.:

```python
import urllib.request
base = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.18.2"
for f in ("swagger-ui.css", "swagger-ui-bundle.js", "swagger-ui-standalone-preset.js"):
    urllib.request.urlretrieve(f"{base}/{f}", f)
```
