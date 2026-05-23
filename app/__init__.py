import os
from pathlib import Path
from flask import Flask

from app.db import init_db


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent.parent / "static"),
        template_folder=str(Path(__file__).parent.parent / "templates"),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    app.config["VAPID_PUBLIC_KEY"] = os.environ.get("VAPID_PUBLIC_KEY", "")

    init_db()

    from app.routes import bp

    app.register_blueprint(bp)

    return app
