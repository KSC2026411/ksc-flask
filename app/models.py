from .extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


# -------------------
# USER MODEL
# -------------------
class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(50), nullable=True)
    _password = db.Column("password", db.String(255), nullable=False)
    is_active = db.Column(
    "active",
    db.Boolean,
    nullable=False,
    default=True,
    server_default=db.text("true")
    )
    failed_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    next_allowed_login = db.Column(db.DateTime, nullable=True)
    role = db.Column(
        db.String(20),
        nullable=False,
        default="customer",
        server_default="customer"
    )
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    packages = db.relationship(
        "Package",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    @property
    def password(self):
        raise AttributeError("Password is write-only")
    @password.setter
    def password(self, plain_password):
        self._password = generate_password_hash(plain_password)
    def check_password(self, plain_password):
        return check_password_hash(self._password, plain_password)
    def has_role(self, role_name):
        return self.role == role_name
    @property
    def is_admin_user(self):
        return self.role == "admin"
    def make_admin(self):
        self.role = "admin"
    def activate_account(self):
        self.is_active = True
        db.session.commit()
    def deactivate_account(self):
        self.is_active = False
        db.session.commit()
    def reset_login_attempts(self):
        self.failed_attempts = 0
        self.next_allowed_login = None
        db.session.commit()
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    def __repr__(self):
        return f"<User {self.id} | {self.email} | {self.role}>"



# -------------------
# PACKAGE MODEL
# -------------------
class Package(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(20), unique=True, nullable=True)
    # CMA CGM tracking
    cma_cgm_booking_reference = db.Column(db.String(50), nullable=True)
    cma_cgm_container_number = db.Column(db.String(20), nullable=True)
    cma_cgm_last_status = db.Column(db.String(100), nullable=True)
    cma_cgm_last_location = db.Column(db.String(255), nullable=True)
    cma_cgm_vessel = db.Column(db.String(255), nullable=True)
    cma_cgm_eta = db.Column(db.DateTime, nullable=True)
    cma_cgm_last_updated = db.Column(db.DateTime, nullable=True)
    description = db.Column(db.String(255), nullable=False)
    street = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(50), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    pickup_date = db.Column(db.Date, nullable=False)
    admin_suggested_date = db.Column(db.Date, nullable=True)
    expected_delivery = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default="Scheduled")
    deposit_paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    received_by = db.Column(db.String(120), nullable=True)
    reschedule_attempts = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship(
        "User",
        back_populates="packages"
    )
    photos = db.relationship(
        "PackagePhoto",
        back_populates="package",
        cascade="all, delete-orphan"
    )
    # NEW
    status_history = db.relationship(
        "PackageStatusHistory",
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="PackageStatusHistory.created_at.asc()"
    )
    container_assignments = db.relationship(
    "PackageContainer",
    back_populates="package",
    cascade="all, delete-orphan"
)

class PackageStatusHistory(db.Model):
    __tablename__ = "package_status_history"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    package_id = db.Column(
        db.Integer,
        db.ForeignKey("package.id"),
        nullable=False
    )

    status = db.Column(
        db.String(50),
        nullable=False
    )

    source = db.Column(
        db.String(50),
        nullable=False,
        default="ADMIN"
    )

    note = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    package = db.relationship(
        "Package",
        back_populates="status_history"
    )

class PackagePhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer,
        db.ForeignKey("package.id"),
        nullable=False
    )
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    delete_at = db.Column(db.DateTime, nullable=True)
    package = db.relationship(
        "Package",
        back_populates="photos"
    )
    def __repr__(self):
        return f"<PackagePhoto {self.id} | Package {self.package_id}>"

    
# -------------------
# ANNOUNCEMENT MODEL
# -------------------
class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    subscription = db.Column(db.Text, nullable=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(255))
    details = db.Column(db.Text)

    ip_address = db.Column(db.String(100))
    status = db.Column(db.String(50))  # success / failed

    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class Container(db.Model):
    __tablename__ = "container"
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    carrier = db.Column(db.String(50), nullable=False, default="CMA CGM")
    booking_number = db.Column(db.String(100), nullable=True)
    container_number = db.Column(db.String(100), nullable=True)
    bill_of_lading = db.Column(db.String(100), nullable=True)
    vessel_name = db.Column(db.String(255), nullable=True)
    voyage_number = db.Column(db.String(100), nullable=True)
    origin = db.Column(db.String(255), nullable=True)
    destination = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="Preparing")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    package_assignments = db.relationship(
        "PackageContainer",
        back_populates="container",
        cascade="all, delete-orphan"
    )
    events = db.relationship(
        "ContainerEvent",
        back_populates="container",
        cascade="all, delete-orphan",
        order_by="ContainerEvent.event_time.asc()"
    )



class PackageContainer(db.Model):
    __tablename__ = "package_container"
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
    container_id = db.Column(db.Integer, db.ForeignKey("container.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    removed_at = db.Column(db.DateTime, nullable=True)
    package = db.relationship(
        "Package",
        back_populates="container_assignments"
    )
    container = db.relationship(
        "Container",
        back_populates="package_assignments"
    )


class ContainerEvent(db.Model):
    __tablename__ = "container_event"
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.Integer, db.ForeignKey("container.id"), nullable=False)
    source = db.Column(db.String(50), nullable=False, default="CMA_CGM")
    event_code = db.Column(db.String(100), nullable=True)
    event_type = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    event_time = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    raw_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    container = db.relationship("Container", back_populates="events")
    container = db.relationship(
    "Container",
    back_populates="events"
)    


# -------------------
# SERIALIZER
# -------------------
def model_to_dict(obj):
    from sqlalchemy.inspection import inspect
    return {
        c.key: getattr(obj, c.key)
        for c in inspect(obj).mapper.column_attrs
    }