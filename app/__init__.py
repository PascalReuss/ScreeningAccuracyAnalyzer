"""Flask presentation layer: app factory + routes + Plotly chart builders."""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask

from config import Config

from .routes import bp


def create_app(config: Config | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__)
    app.config["SCREENING_CONFIG"] = config or Config.from_env()
    app.register_blueprint(bp)
    return app
