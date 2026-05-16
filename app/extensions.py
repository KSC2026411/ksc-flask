from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_mail import Mail  # <-- add this

# -------------------
# EXTENSIONS
# -------------------
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO(async_mode="threading", cors_allowed_origins="*")
mail = Mail()  # <-- initialize mail