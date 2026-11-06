import os
from datetime import datetime

from flask import Flask
from dotenv import load_dotenv
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

from .extensions import db, migrate, socketio, csrf
from .models import User, Announcement
from . import events

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("⚠️ OPENAI_API_KEY not set. Smart Description and Chatbot will not work.")


def create_app():
    app = Flask(__name__)

    # SECURITY CONFIGURATION
    secret_key = os.getenv("SECRET_KEY")

    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required.")

    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["DEV_MODE"] = os.getenv("DEV_MODE", "false").lower() == "true"

    # OPENAI CONFIGURATION
    app.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

    if app.config["OPENAI_API_KEY"]:
        app.openai_client = OpenAI(
            api_key=app.config["OPENAI_API_KEY"]
        )
        print("✅ OpenAI client initialized.")
    else:
        app.openai_client = None
        print("⚠️ OpenAI client disabled.")

    # PUSH NOTIFICATIONS
    app.config["VAPID_PUBLIC_KEY"] = os.getenv("VAPID_PUBLIC_KEY")
    app.config["VAPID_PRIVATE_KEY"] = os.getenv("VAPID_PRIVATE_KEY")
    app.config["VAPID_SUBJECT"] = os.getenv("VAPID_SUBJECT")

    # EXTERNAL API
    CMA_CGM_API_KEY = os.getenv("CMA_CGM_API_KEY")
    CMA_CGM_API_BASE = "https://apis.cma-cgm.net"

    # DATABASE CONFIGURATION
    database_url = os.getenv("DATABASE_URL") or "sqlite:///site.db"

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if database_url.startswith("postgresql://"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"sslmode": "require"},
            "pool_pre_ping": True
        }

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # SOCKET.IO CONFIGURATION
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="gevent"
    )

    # REDIS / FLASK-LIMITER CONFIGURATION
    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable is not configured.")

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=redis_url,
        storage_options={
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "health_check_interval": 30
        },
        default_limits=[
            "200 per day",
            "50 per hour"
        ]
    )

    app.limiter = limiter

    print("✅ Flask-Limiter initialized with Redis.")

    # LOGIN MANAGER
    login_manager = LoginManager()
    login_manager.login_view = "main.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ROUTES
    from .routes import main
    app.register_blueprint(main)

    # SOCKET.IO EVENTS
    events.register_socketio_events(app)

    # REGISTERED ROUTES
    print("📌 REGISTERED ROUTES:")

    for rule in app.url_map.iter_rules():
        print(rule.endpoint, rule)

    # CLEANUP EXPIRED ANNOUNCEMENTS
    def cleanup_expired_announcements():
        with app.app_context():
            try:
                now = datetime.utcnow()

                expired = Announcement.query.filter(
                    Announcement.expires_at <= now
                ).all()

                if expired:
                    for item in expired:
                        db.session.delete(item)

                    db.session.commit()

                    print(
                        f"🧹 Cleaned {len(expired)} expired announcements"
                    )

            except Exception as e:
                db.session.rollback()
                print(f"⚠️ Announcement cleanup failed: {e}")

    # BACKGROUND SCHEDULER
    scheduler = BackgroundScheduler()

    if (
        not app.debug
        or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        scheduler.add_job(
            func=cleanup_expired_announcements,
            trigger="interval",
            minutes=10,
            id="cleanup_expired_announcements",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.start()

        print("✅ Background scheduler started.")

    return app