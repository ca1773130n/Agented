"""Agented service package — Flask retired in wave 80.

`app/__init__.py` no longer exposes a `create_app` factory. The runtime
lives in `app_litestar/`. Submodules (`app.config`, `app.database`,
`app.services.*`, `app.db.*`, `app.models.*`, `app.logging_config`)
remain in place because Litestar handlers import them directly.
"""
