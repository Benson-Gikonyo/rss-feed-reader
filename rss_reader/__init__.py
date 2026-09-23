import math
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure an RSS Feed Reader application instance."""
    load_dotenv()

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
    )
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        DATABASE=os.getenv("DATABASE_PATH", str(Path(app.instance_path) / "rss_feeds.db")),
        FETCH_CONNECT_TIMEOUT=float(os.getenv("FETCH_CONNECT_TIMEOUT", "3")),
        FETCH_READ_TIMEOUT=float(os.getenv("FETCH_READ_TIMEOUT", "10")),
        MAX_FEED_BYTES=int(os.getenv("MAX_FEED_BYTES", "2000000")),
        MAX_FEED_REDIRECTS=int(os.getenv("MAX_FEED_REDIRECTS", "3")),
    )

    if test_config is not None:
        app.config.update(test_config)

    for setting in ("FETCH_CONNECT_TIMEOUT", "FETCH_READ_TIMEOUT", "MAX_FEED_BYTES"):
        if not math.isfinite(app.config[setting]) or app.config[setting] <= 0:
            raise ValueError(f"{setting} must be positive.")
    if app.config["MAX_FEED_REDIRECTS"] < 0:
        raise ValueError("MAX_FEED_REDIRECTS cannot be negative.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "testing-only-secret"
        else:
            raise RuntimeError(
                "SECRET_KEY is required. Add it to your environment or .env file."
            )

    from .database import init_app

    init_app(app)

    from .routes import web

    app.register_blueprint(web)
    return app
