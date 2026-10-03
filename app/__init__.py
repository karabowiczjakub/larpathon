"""AirRoute Kraków — Flask application factory.

Imports live inside create_app() so that `import app.contracts` (used by every role) stays light.
"""
from __future__ import annotations


def create_app(overrides: dict | None = None, *, modules=None):
    """`modules` (app.providers.Modules) lets tests inject ready-made modules instead of building them."""
    import logging

    from flask import Flask

    from . import config
    from .api import bp as api_bp
    from .engine import Engine
    from .errors import register_error_handlers
    from .json_provider import OrjsonProvider
    from .providers import build_modules

    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.update(config.from_env())
    if overrides:
        app.config.update(overrides)
    logging.basicConfig(level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app.json = OrjsonProvider(app)

    engine = Engine(modules or build_modules(app.config), cache_size=app.config["COST_CACHE_SIZE"])
    if app.config["WARMUP"]:
        engine.warmup()
    app.extensions["engine"] = engine

    register_error_handlers(app)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    return app
