import os
from flask import Flask
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_socketio import SocketIO

from app.extensions import db, migrate, socketio

load_dotenv()

# -----------------------
# APP FACTORY STYLE SETUP
# -----------------------
app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static"
)

# -----------------------
# CONFIG
# -----------------------
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")

# ✅ FIX: DATABASE_URL compatibility (Railway/Postgres)
database_url = os.getenv("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"sslmode": "require"},
    "pool_pre_ping": True
}

# -----------------------
# EXTENSIONS INIT
# -----------------------
db.init_app(app)
migrate = Migrate(app, db)
socketio.init_app(app, cors_allowed_origins="*")

# -----------------------
# LOGIN MANAGER
# -----------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "main.login"

# -----------------------
# MODELS IMPORT (AFTER DB)
# -----------------------
from app import models
from app.models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -----------------------
# BLUEPRINT REGISTER
# -----------------------
from app.routes import main
app.register_blueprint(main)

# -----------------------
# CONTEXT PROCESSOR
# -----------------------
@app.context_processor
def inject_user():
    return dict(current_user=current_user)

# -----------------------
# DEBUG ROUTE (REMOVE LATER)
# -----------------------
@app.route("/debug-db")
def debug_db():
    return "App running with DB = " + str(app.config["SQLALCHEMY_DATABASE_URI"])

# ❌ REMOVE THIS BLOCK FOR RAILWAY DEPLOYMENT
# -----------------------
# RUN SERVER
# -----------------------
# if __name__ == "__main__":
#     socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)