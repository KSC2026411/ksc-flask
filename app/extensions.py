from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect

# -------------------
# EXTENSIONS
# -------------------

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

socketio = SocketIO(
    async_mode="gevent",
    cors_allowed_origins="*",
    ping_interval=25,
    ping_timeout=60
)