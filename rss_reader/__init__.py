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
        DATABASE=str(Path(app.instance_path) / "rss_feeds.db"),
    )

    if test_config is not None:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "testing-only-secret"
        else:
            raise RuntimeError(
                "SECRET_KEY is required. Add it to your environment or .env file."
            )

    from .routes import web

    app.register_blueprint(web)
    return app
