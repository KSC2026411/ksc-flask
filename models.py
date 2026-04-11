from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    _password = db.Column("password", db.String(200), nullable=False)  # hashed password
    phone = db.Column(db.String(50))  # optional

    # OLD SYSTEM (keep for compatibility)
    is_admin = db.Column(db.Boolean, default=False)

    # NEW SYSTEM (recommended going forward)
    role = db.Column(db.String(20), default="user")  # user, admin, staff

    packages = db.relationship('Package', back_populates='user', cascade="all, delete-orphan")

    # -------------------
    # PASSWORD HANDLING
    # -------------------
    @property
    def password(self):
        raise AttributeError("Password is write-only")

    @password.setter
    def password(self, plain_password):
        self._password = generate_password_hash(plain_password)

    def check_password(self, plain_password):
        return check_password_hash(self._password, plain_password)

    # -------------------
    # ROLE HELPERS (NEW)
    # -------------------
    def has_role(self, role_name):
        return self.role == role_name

    def make_admin(self):
        self.role = "admin"
        self.is_admin = True  # keeps old code working


class Package(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    street = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(50), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    pickup_date = db.Column(db.Date, nullable=False)
    admin_suggested_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default="Scheduled")
    deposit_paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ✅ ADD IT RIGHT HERE
    reschedule_attempts = db.Column(db.Integer, default=0)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', back_populates='packages')


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)