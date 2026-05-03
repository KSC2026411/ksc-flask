import os
from flask import Flask
from dotenv import load_dotenv

from .extensions import db, migrate, socketio
from flask_login import LoginManager
from .models import User, Announcement
from sqlalchemy import text
from . import events

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime


def create_app():
    load_dotenv()

    app = Flask(__name__)

    # -------------------
    # CONFIG
    # -------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["DEV_MODE"] = os.getenv("DEV_MODE", "false").lower() == "true"

    # -------------------
    # DATABASE CONFIG (Railway-safe)
    # -------------------
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        database_url = "sqlite:///site.db"

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")

    # -------------------
    # MODELS
    # -------------------
    from . import models  # noqa: F401

    # -------------------
    # BLUEPRINTS
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
    # SOCKET EVENTS
    # -------------------
    events.register_socketio_events(app)

    # =====================================================
    # 🧹 AUTO CLEANUP: EXPIRED ANNOUNCEMENTS
    # =====================================================
    def cleanup_expired_announcements():
        with app.app_context():
            now = datetime.utcnow()

            expired = Announcement.query.filter(
                Announcement.expires_at <= now
            ).all()

            if expired:
                for a in expired:
                    db.session.delete(a)

                db.session.commit()
                print(f"🧹 Cleaned {len(expired)} expired announcements")

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=cleanup_expired_announcements,
        trigger="interval",
        minutes=10
    )
    scheduler.start()

    return app