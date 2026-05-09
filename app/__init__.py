import os
from flask import Flask
from dotenv import load_dotenv

from .extensions import db, migrate, socketio
from flask_login import LoginManager
from .models import User, Announcement
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
# PUSH NOTIFICATIONS
# -------------------
    app.config["VAPID_PUBLIC_KEY"] = os.getenv("VAPID_PUBLIC_KEY")
    app.config["VAPID_PRIVATE_KEY"] = os.getenv("VAPID_PRIVATE_KEY")

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

    # ✅ FIXED: Use threading (no gevent dependency)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading"
    )

    # -------------------
    # MODELS
    # -------------------
    from . import models  # noqa: F401

    # -------------------
    # BLUEPRINTS
    # -------------------
    from .routes import main
    app.register_blueprint(main)

    # ✅ DEBUG: PRINT ALL REGISTERED ROUTES
    print("📌 REGISTERED ROUTES:")
    for rule in app.url_map.iter_rules():
        print(rule.endpoint, rule)

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

    # ✅ Prevent double scheduler in debug / reload
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        scheduler.add_job(
            func=cleanup_expired_announcements,
            trigger="interval",
            minutes=10
        )
        scheduler.start()

    return app