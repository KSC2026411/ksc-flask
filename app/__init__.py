# app/__init__.py

import os
from flask import Flask
from dotenv import load_dotenv
from datetime import datetime

from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

from .extensions import db, migrate, socketio
from .models import User, Announcement
from . import events


# -------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()

# Optional: load OpenAI key into environment for use in routes
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  OPENAI_API_KEY not set. Smart Description and Chatbot will not work.")


def create_app():
    app = Flask(__name__)

    # =====================================================
    # CONFIG
    # =====================================================
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["DEV_MODE"] = os.getenv("DEV_MODE", "false").lower() == "true"
    
    app.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    app.openai_client = OpenAI(api_key=app.config["OPENAI_API_KEY"])

    # -------------------------------------------------
    # PUSH NOTIFICATIONS (VAPID)
    # -------------------------------------------------
    app.config["VAPID_PUBLIC_KEY"] = os.getenv("VAPID_PUBLIC_KEY")
    app.config["VAPID_PRIVATE_KEY"] = os.getenv("VAPID_PRIVATE_KEY")

    CMA_CGM_API_KEY = os.getenv("CMA_CGM_API_KEY")
    CMA_CGM_API_BASE = "https://apis.cma-cgm.net"

    # -------------------------------------------------
    # DATABASE CONFIG (Railway-safe)
    # -------------------------------------------------
    database_url = os.getenv("DATABASE_URL") or "sqlite:///site.db"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if database_url.startswith("postgresql://"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"sslmode": "require"},
            "pool_pre_ping": True
        }

    # =====================================================
    # INIT EXTENSIONS
    # =====================================================
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(
    app,
    cors_allowed_origins="*",
    async_mode="gevent"
    )

    # =====================================================
    # RATE LIMITER (GLOBAL SECURITY)
    # =====================================================
    redis_url = os.getenv("REDIS_URL")

    limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=redis_url,
    default_limits=["200 per day", "50 per hour"]
        )

    app.limiter = limiter

    # =====================================================
    # LOGIN MANAGER
    # =====================================================
    login_manager = LoginManager()
    login_manager.login_view = "main.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # =====================================================
    # BLUEPRINTS
    # =====================================================
    from .routes import main
    app.register_blueprint(main)

    # =====================================================
    # SOCKET EVENTS
    # =====================================================
    events.register_socketio_events(app)

    # =====================================================
    # DEBUG ROUTES
    # =====================================================
    print("📌 REGISTERED ROUTES:")
    for rule in app.url_map.iter_rules():
        print(rule.endpoint, rule)

    # =====================================================
    # BACKGROUND TASKS
    # =====================================================
    def cleanup_expired_announcements():
        with app.app_context():
            now = datetime.utcnow()
            expired = Announcement.query.filter(Announcement.expires_at <= now).all()
            if expired:
                for item in expired:
                    db.session.delete(item)
                db.session.commit()
                print(f"🧹 Cleaned {len(expired)} expired announcements")

    scheduler = BackgroundScheduler()
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        scheduler.add_job(
            func=cleanup_expired_announcements,
            trigger="interval",
            minutes=10
        )
        scheduler.start()

    return app