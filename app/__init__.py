import os
from flask import Flask
from dotenv import load_dotenv
from .extensions import db, migrate, socketio
from flask_login import LoginManager
from .models import User
from sqlalchemy import text

def create_app():
    load_dotenv()

    app = Flask(__name__)

    # -------------------
    # CONFIG
    # -------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["DEV_MODE"] = os.getenv("DEV_MODE", "false").lower() == "true"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # -------------------
    # INIT EXTENSIONS
    # -------------------
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")  # Threading mode works with long-polling

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
    # DATABASE CONNECTION TEST
    # -------------------
    with app.app_context():
        try:
            db.session.execute(text("SELECT 1"))
            print("✅ Database connected successfully!")
        except Exception as e:
            print("❌ Database connection failed:", e)

    # -------------------
    # IMPORT SOCKETIO EVENTS
    # -------------------
    from . import events  # All SocketIO event handlers live here

    return app