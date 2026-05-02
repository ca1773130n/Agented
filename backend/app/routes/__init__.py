"""Back-compat shim — Flask blueprints retired in wave 80.

The route surface lives on Litestar at `app_litestar.routes.*`. This
package keeps `from app.routes import ...` from raising
ModuleNotFoundError on the package; submodule imports raise the more
informative ImportError instead.

Legacy tests that did `monkeypatch.setattr("app.routes.X.Y", ...)` need
to be updated to target `app_litestar.routes.<wave_module>.Y`
(or the originating service module they were really mocking).
"""
