import os
from flask import Flask
from dotenv import load_dotenv
from .extensions import db, migrate, socketio
from flask_login import LoginManager
from .models import User
from sqlalchemy import text
from . import events  # Import Socket.IO events


def create_app():
    load_dotenv()

    app = Flask(__name__)

    # -------------------
    # CONFIG
    # -------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["DEV_MODE"] = os.getenv("DEV_MODE", "false").lower() == "true"

    # ---- DATABASE CONFIG ----
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("⚠️ DATABASE_URL missing - using SQLite fallback")
        database_url = "sqlite:///site.db"

    # Fix deprecated postgres:// prefix
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Only apply SSL settings for Postgres (Railway-safe)
    if database_url.startswith("postgresql://"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"sslmode": "require"},
            "pool_pre_ping": True
        }

    # -------------------
    # INIT EXTENSIONS
    # -------------------
    db.init_app(app)
    migrate.init_app(app, db)

    # ✅ Force async mode for SocketIO (prevents Railway guessing issues)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")

    # -------------------
    # IMPORT MODELS
    # -------------------
    from . import models  # noqa: F401

    # -------------------
    # REGISTER BLUEPRINTS
    # -------------------
    from .routes import main
    app.register_blueprint(main)

    # -------------------
    # LOGIN MANAGER
    # -------------------
    login_manager = LoginManager()
    login_manager.login_view = "main.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # -------------------
    # REGISTER SOCKET.IO EVENTS
    # -------------------
    events.register_socketio_events(app)

    return app