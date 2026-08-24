from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, current_app
from flask_login import login_required, login_user, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text, or_
from bs4 import BeautifulSoup
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload


from datetime import datetime, timedelta, date
import json
import re
import os
import uuid
from openai import OpenAI

from itsdangerous import URLSafeTimedSerializer

from .models import User, Package, PackageContainer, Announcement, PushSubscription, AuditLog, PackagePhoto, PackageStatusHistory 
from .extensions import db, socketio
from .decorators import admin_required
from .utils import generate_tracking, send_push_notification

main = Blueprint("main", __name__)
csrf = CSRFProtect()

# ----------------------------
# Global OpenAI client
# ----------------------------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------
# Email validation regex
# -------------------------
EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'

# -------------------------
# Minimum password length
# -------------------------
MIN_PASSWORD_LENGTH = 8


# -------------------------
# Generate activation token
# -------------------------
def generate_activation_token(email, secret_key, salt='email-confirm'):
    serializer = URLSafeTimedSerializer(secret_key)
    return serializer.dumps(email, salt=salt)

def confirm_activation_token(token, secret_key, expiration=3600, salt='email-confirm'):
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        email = serializer.loads(token, salt=salt, max_age=expiration)
    except Exception:
        return None
    return email

def schedule_photo_deletion(package):
    if not package.delivered_at:
        package.delivered_at = datetime.utcnow()
    delete_at = package.delivered_at + timedelta(days=15)
    for photo in package.photos:
        photo.delete_at = delete_at

# US Federal Holidays dictionary
US_FEDERAL_HOLIDAYS = {
    "01-01": "Happy New Year! 🎉",
    "01-20": "Happy Martin Luther King Jr. Day! ✊",
    "02-17": "Happy Presidents' Day! 🇺🇸",
    "05-25": "Happy Memorial Day! 🇺🇸",
    "06-19": "Happy Juneteenth! ✊",
    "07-04": "Happy Independence Day! 🎆",
    "09-07": "Happy Labor Day! 🛠️",
    "10-12": "Happy Columbus Day! ⛵",
    "11-11": "Happy Veterans Day! 🇺🇸",
    "11-26": "Happy Thanksgiving! 🦃",
    "12-25": "Merry Christmas! 🎄"
}

UPLOAD_FOLDER = os.environ.get(
    "PACKAGE_PHOTO_UPLOAD_FOLDER",
    "/app/package_uploads"
)

MAX_CONTENT_LENGTH = 10 * 1024 * 1024
######                        #######
###### PUBLIC ROUTES #######
######                        #######

@main.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception as e:
        return {"status": "error", "details": str(e)}, 500


@main.route("/debug/user-columns")
def debug_user_columns():
    from sqlalchemy import inspect

    inspector = inspect(db.engine)

    columns = inspector.get_columns("user")

    result = []

    for column in columns:
        result.append({
            "name": column["name"],
            "type": str(column["type"]),
            "nullable": column["nullable"],
            "default": str(column["default"])
        })

    return {
        "database_url_host": db.engine.url.host,
        "columns": result
    }

@main.route("/debug/fix-user-schema")
def fix_user_schema():
    from sqlalchemy import text

    db.session.execute(
        text('ALTER TABLE "user" DROP COLUMN IF EXISTS "is_active"')
    )
    db.session.commit()

    return {
        "status": "success",
        "message": "Legacy is_active column removed."
    }
    

    
@main.route("/test")
def test():
    return "TEST OK"


@main.route("/offline")
def offline():
    return render_template("public/offline.html")


@main.route("/", methods=["GET", "POST"])
def home():
    now = datetime.utcnow()

    try:
        # -----------------------------------
        # Delete expired announcements
        # -----------------------------------
        expired = Announcement.query.filter(
            Announcement.expires_at.isnot(None),
            Announcement.expires_at <= now
        ).all()

        for a in expired:
            db.session.delete(a)

        db.session.commit()

        # -----------------------------------
        # Fetch active announcements
        # -----------------------------------
        announcements = Announcement.query.filter(
            Announcement.expires_at.isnot(None),
            Announcement.expires_at > now
        ).order_by(
            Announcement.created_at.desc()
        ).all()

    except Exception as e:
        db.session.rollback()
        print("DB ERROR:", e)
        announcements = []

    # -----------------------------------
    # Package Search Logic
    # -----------------------------------
    packages = []
    search_query = ""

    # Handle GET search
    if request.method == "GET":
        search_query = request.args.get(
            "search", ""
        ).strip()

    # Handle POST search
    elif request.method == "POST":
        search_query = request.form.get(
            "search", ""
        ).strip()

    # Run package search
    if search_query:
        try:
            packages = Package.query.filter(
                or_(
                    Package.tracking_number.ilike(
                        f"%{search_query}%"
                    ),
                    Package.last_name.ilike(
                        f"%{search_query}%"
                    )
                )
            ).order_by(
                Package.id.desc()
            ).all()

            print(f"SEARCH QUERY: {search_query}")
            print(f"PACKAGES FOUND: {len(packages)}")

        except Exception as e:
            print("PACKAGE SEARCH ERROR:", e)
            packages = []

    # -----------------------------------
    # Holiday Logic
    # -----------------------------------
    today_str = datetime.now().strftime("%m-%d")
    holiday_message = US_FEDERAL_HOLIDAYS.get(today_str)

    # -----------------------------------
    # Render Page
    # -----------------------------------
    return render_template(
        "public/home.html",
        announcements=announcements,
        now=now,
        holiday_message=holiday_message,
        packages=packages,
        search_query=search_query
    )


@main.route("/save-subscription", methods=["POST"])
@login_required
def save_subscription():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No data"}), 400

        subscription_json = json.dumps(data)

        existing = PushSubscription.query.filter_by(
            user_id=current_user.id
        ).first()

        if existing:
            existing.subscription = subscription_json
        else:
            db.session.add(PushSubscription(
                user_id=current_user.id,
                subscription=subscription_json
            ))

        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        print("❌ SAVE SUBSCRIPTION ERROR:", e)
        return jsonify({"success": False}), 500
    

    
@main.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        # -------------------------
        # Get form data
        # -------------------------
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # -------------------------
        # Validate names
        # -------------------------
        if (
            not first_name
            or any(char.isdigit() for char in first_name)
        ):
            flash(
                "First name cannot contain numbers and cannot be empty.",
                "warning"
            )
            return redirect(url_for("main.register"))

        if (
            not last_name
            or any(char.isdigit() for char in last_name)
        ):
            flash(
                "Last name cannot contain numbers and cannot be empty.",
                "warning"
            )
            return redirect(url_for("main.register"))

        # -------------------------
        # Validate email format
        # -------------------------
        EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'

        if not email or not re.match(EMAIL_REGEX, email):
            flash(
                "Please provide a valid email address.",
                "warning"
            )
            return redirect(url_for("main.register"))

        # -------------------------
        # Optional domain validation
        # -------------------------
        domain = email.split("@")[1]

        try:
            import socket
            socket.gethostbyname(domain)

        except Exception:
            flash(
                "Email domain does not exist.",
                "warning"
            )
            return redirect(url_for("main.register"))

        # -------------------------
        # Check if email exists
        # -------------------------
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "warning")
            return redirect(url_for("main.register"))

        # -------------------------
        # Validate password
        # -------------------------
        MIN_PASSWORD_LENGTH = 8

        if not password or password != confirm_password:
            flash(
                "Passwords do not match or are empty.",
                "warning"
            )
            return redirect(url_for("main.register"))

        if len(password) < MIN_PASSWORD_LENGTH:
            flash(
                f"Password must be at least "
                f"{MIN_PASSWORD_LENGTH} characters long.",
                "warning"
            )
            return redirect(url_for("main.register"))

        # -------------------------
        # Create user
        # -------------------------
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            role="customer",
            is_active=False
        )

        user.password = password

        db.session.add(user)
        db.session.commit()

        flash(
            "Account created! Your account is pending admin approval.",
            "success"
        )

        return redirect(url_for("main.login"))

    return render_template("public/register.html")


@main.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        email = email.strip().lower() if email else None

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):

            # ----------------------------
            # Check if account is active
            # Treat NULL (old accounts) as active
            # ----------------------------
            if user.is_active is not None and not user.is_active:
                flash("Your account is not activated. Please contact the admin.", "danger")
                return redirect(url_for("main.login"))

            # ----------------------------
            # Log the user in
            # ----------------------------
            login_user(user)
            flash(f"Welcome back, {user.full_name}!", "success")

            # ----------------------------
            # Redirect based on role
            # ----------------------------
            if user.role == "admin":
                return redirect(url_for("main.admin_dashboard"))
            else:
                return redirect(url_for("main.dashboard"))

        # ----------------------------
        # Invalid credentials
        # ----------------------------
        flash("Invalid email or password", "danger")

    return render_template("public/login.html")


@main.route("/logout")
@login_required
def logout():

    logout_user()

    flash("Logged out.", "info")
    return redirect(url_for("main.home"))


######                        #######
###### CUSTOMER SYSTEM ROUTES #######
######                        #######

@main.route("/dashboard")
@login_required
def dashboard():

    # ----------------------------
    # ROLE SAFETY CHECK
    # ----------------------------
    role = (current_user.role or "").strip().lower()

    if role != "customer":
        flash("Admins cannot access customer dashboard.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    # ----------------------------
    # CURRENT TIME (UTC SAFE)
    # ----------------------------
    now = datetime.utcnow()

    # ----------------------------
    # ACTIVE ANNOUNCEMENTS
    # ----------------------------
    announcements = (
        Announcement.query.filter(
            Announcement.expires_at.isnot(None),
            Announcement.expires_at > now
        )
        .order_by(Announcement.created_at.desc())
        .all()
    )

    # ----------------------------
    # ALL CUSTOMER PACKAGES
    # ----------------------------
    all_packages = (
        Package.query
        .filter_by(user_id=current_user.id)
        .order_by(Package.created_at.desc())
        .all()
    )

    # Only latest 3 packages for dashboard preview
    packages = all_packages[:3]

    # ----------------------------
    # ANALYTICS
    # ----------------------------
    total_packages = len(all_packages)

    pending_deliveries = sum(
        1 for p in all_packages
        if p.status and "pending" in p.status.lower()
    )

    delivered_packages = sum(
        1 for p in all_packages
        if p.status and (
            "delivered" in p.status.lower()
            or "archived" in p.status.lower()
        )
    )

    in_transit_packages = sum(
        1 for p in all_packages
        if p.status and "transit" in p.status.lower()
    )

    # ----------------------------
    # RENDER DASHBOARD
    # ----------------------------
    return render_template(
        "customer/customer_dashboard.html",
        announcements=announcements,
        packages=packages,
        total_packages=total_packages,
        pending_deliveries=pending_deliveries,
        delivered_packages=delivered_packages,
        in_transit_packages=in_transit_packages
    )

@main.route("/schedule", methods=["GET", "POST"])
@login_required
def schedule():

    if current_user.role == "admin":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    if request.method == "POST":

        description = request.form.get("description", "").strip()
        street = request.form.get("street", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        zip_code = request.form.get("zip", "").strip()
        phone = request.form.get("phone", "").strip()
        pickup_date_str = request.form.get("date", "").strip()

        # Validate required fields
        if not all([
            description,
            street,
            city,
            state,
            zip_code,
            phone,
            pickup_date_str
        ]):
            flash("All fields are required!", "warning")
            return redirect(url_for("main.schedule"))

        # Validate pickup date format
        try:
            pickup_datetime = datetime.strptime(
                pickup_date_str,
                "%Y-%m-%d"
            )
        except ValueError:
            flash("Invalid pickup date!", "danger")
            return redirect(url_for("main.schedule"))

        # Do not allow dates in the past.
        # Today and all future dates are allowed.
        if pickup_datetime.date() < datetime.now().date():
            flash("Pickup date cannot be in the past.", "warning")
            return redirect(url_for("main.schedule"))

        # Get uploaded photos
        photos = [
            photo
            for photo in request.files.getlist("package_photos")
            if photo and photo.filename
        ]

        # Maximum 3 photos
        if len(photos) > 3:
            flash("You can upload a maximum of 3 photos.", "warning")
            return redirect(url_for("main.schedule"))

        allowed_extensions = {
            "jpg",
            "jpeg",
            "png",
            "webp"
        }

        max_file_size = 10 * 1024 * 1024  # 10 MB

        # Validate each photo
        for photo in photos:

            original_name = secure_filename(photo.filename)

            if not original_name:
                flash(
                    "One of the uploaded files is invalid.",
                    "danger"
                )
                return redirect(url_for("main.schedule"))

            extension = (
                original_name.rsplit(".", 1)[1].lower()
                if "." in original_name
                else ""
            )

            if extension not in allowed_extensions:
                flash(
                    "Only JPG, JPEG, PNG, and WEBP photos are allowed.",
                    "warning"
                )
                return redirect(url_for("main.schedule"))

            # Check file size
            photo.seek(0, os.SEEK_END)
            file_size = photo.tell()
            photo.seek(0)

            if file_size > max_file_size:
                flash(
                    f"{original_name} is larger than 10 MB.",
                    "warning"
                )
                return redirect(url_for("main.schedule"))

        # Upload folder
        upload_folder = os.environ.get(
            "UPLOAD_FOLDER",
            os.path.join(
                os.getcwd(),
                "static",
                "uploads",
                "packages"
            )
        )

        os.makedirs(upload_folder, exist_ok=True)

        # Create package
        package = Package(
            tracking_number=None,
            status="Pending Approval",
            description=description,
            street=street,
            city=city,
            state=state,
            zip_code=zip_code,
            user_id=current_user.id,
            pickup_date=pickup_datetime.date()
        )

        saved_files = []

        try:

            db.session.add(package)
            db.session.flush()

            # Save photos
            for photo in photos:

                original_name = secure_filename(photo.filename)

                extension = (
                    original_name.rsplit(".", 1)[1].lower()
                )

                filename = f"{uuid.uuid4().hex}.{extension}"

                file_path = os.path.join(
                    upload_folder,
                    filename
                )

                photo.save(file_path)
                saved_files.append(file_path)

                package_photo = PackagePhoto(
                    package_id=package.id,
                    filename=filename,
                    original_filename=original_name,
                    uploaded_at=datetime.utcnow(),
                    delete_at=None
                )

                db.session.add(package_photo)

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            # Delete any files that were already saved
            for file_path in saved_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass

            print("SCHEDULE PACKAGE ERROR:", e)

            flash(
                "Unable to schedule pickup. Please try again.",
                "danger"
            )

            return redirect(url_for("main.schedule"))

        # Success message
        if photos:
            flash(
                f"Pickup scheduled with {len(photos)} photo(s). "
                "Awaiting admin approval.",
                "success"
            )
        else:
            flash(
                "Pickup scheduled successfully. "
                "Awaiting admin approval.",
                "success"
            )

        return redirect(url_for("main.schedule"))

    return render_template("customer/schedule.html")

# -------------------
# PACKAGE ACTIONS (Customer)
# -------------------

@main.route("/customer/package/<int:package_id>/edit", methods=["GET", "POST"])
@login_required
def edit_package(package_id):
    package = Package.query.get_or_404(package_id)

    # Ownership check
    if package.user_id != current_user.id:
        abort(403)

    # Lock editing for certain statuses
    LOCKED_STATUSES = [
        "Picked Up",
        "In Transit",
        "Out for Delivery",
        "At warehouse",
        "Loaded",
        "Shipped",
        "Delivered",
        "Cancelled"
    ]

    if package.status in LOCKED_STATUSES:
        flash("This package can no longer be edited.", "warning")
        return redirect(url_for("main.customer_packages"))

    if request.method == "POST":
        # Update fields from form
        package.description = request.form.get("description")
        package.street = request.form.get("street")
        package.city = request.form.get("city")
        package.state = request.form.get("state")
        package.zip_code = request.form.get("zip_code")

        # Pickup date validation
        pickup_date = request.form.get("pickup_date")
        if pickup_date:
            pickup_date_obj = datetime.strptime(pickup_date, "%Y-%m-%d").date()
            if pickup_date_obj < date.today():
                flash("Pickup date cannot be in the past.", "danger")
                return redirect(url_for("main.edit_package", package_id=package.id))
            package.pickup_date = pickup_date_obj

        # Admin suggested date validation
        admin_date = request.form.get("admin_suggested_date")
        if admin_date:
            admin_date_obj = datetime.strptime(admin_date, "%Y-%m-%d").date()
            if admin_date_obj < package.pickup_date:
                flash("Admin suggested date cannot be before the pickup date.", "danger")
                return redirect(url_for("main.edit_package", package_id=package.id))
            package.admin_suggested_date = admin_date_obj

        # Deposit checkbox
        deposit_paid = request.form.get("deposit_paid") == "on"
        package.deposit_paid = deposit_paid

        db.session.commit()
        flash("Package updated successfully.", "success")
        return redirect(url_for("main.customer_packages"))

    # Render edit page with today's date for client-side min
    return render_template(
        "customer/edit_package.html",
        package=package,
        today=date.today().strftime("%Y-%m-%d")
    )


@main.route("/customer/package/<int:package_id>/reschedule", methods=["POST"])
@login_required
def reschedule_package(package_id):
    package = Package.query.get_or_404(package_id)
    if package.user_id != current_user.id:
        flash("Unauthorized.")
        return redirect(url_for("main.my_packages"))

    new_date_str = request.form.get("new_date")
    if not new_date_str:
        flash("Select a new date.")
        return redirect(url_for("main.my_packages"))

    try:
        new_date = datetime.strptime(new_date_str,"%Y-%m-%d")
    except ValueError:
        flash("Invalid date format.")
        return redirect(url_for("main.my_packages"))

    if new_date < datetime.now() + timedelta(hours=72):
        flash("Rescheduled date must be at least 72 hours from now.")
        return redirect(url_for("main.my_packages"))

    package.reschedule_attempts = (package.reschedule_attempts or 0) + 1
    if package.reschedule_attempts > 3:
        flash("Maximum reschedules reached.")
        return redirect(url_for("main.my_packages"))

    package.pickup_date = new_date.date()
    package.status = "Pending Reschedule"
    db.session.commit()
    flash("Reschedule request submitted.")
    return redirect(url_for("main.my_packages"))


@main.route("/customer/package/<int:package_id>/cancel", methods=["POST"], endpoint="cancel_package")
@login_required
def cancel_package(package_id):

    package = Package.query.get_or_404(package_id)

    if package.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("main.my_packages"))

    if package.status in ["Picked Up", "Delivered"]:
        flash("Cannot cancel this package.", "warning")
        return redirect(url_for("main.my_packages"))

    if package.pickup_date:
        days_left = (package.pickup_date - datetime.utcnow().date()).days
        if days_left < 3:
            flash("Must cancel at least 72 hours before pickup.", "warning")
            return redirect(url_for("main.my_packages"))

    package.status = "Cancelled"
    db.session.commit()

    flash("Package cancelled.", "success")
    return redirect(url_for("main.my_packages"))


# -------------------
# CUSTOMER RESCHEDULES (accept/reject/propose)
# -------------------

@main.route("/accept_admin_reschedule/<int:package_id>", methods=["POST"])
@login_required
def accept_admin_reschedule(package_id):
    package = Package.query.get_or_404(package_id)
    if package.user_id != current_user.id or package.status != "Admin Suggested Reschedule":
        flash("Unauthorized or invalid action.")
        return redirect(url_for("main.my_packages"))

    if package.updated_at and datetime.utcnow() > package.updated_at + timedelta(hours=24):
        flash("This reschedule offer has expired.")
        return redirect(url_for("main.my_packages"))

    if package.admin_suggested_date:
        package.pickup_date = package.admin_suggested_date
    package.admin_suggested_date = None
    package.status = "Scheduled"
    db.session.commit()
    flash("Reschedule accepted.")
    return redirect(url_for("main.my_packages"))

@main.route("/customer/package/<int:package_id>/reject-reschedule", methods=["POST"])
@login_required
def customer_reject_admin_reschedule(package_id):
    package = Package.query.get_or_404(package_id)
    if package.user_id != current_user.id or package.status != "Admin Suggested Reschedule":
        flash("Unauthorized or invalid action.")
        return redirect(url_for("main.my_packages"))

    if package.updated_at and package.updated_at < datetime.utcnow() - timedelta(hours=24):
        flash("This reschedule offer has expired.")
        return redirect(url_for("main.my_packages"))

    package.admin_suggested_date = None
    package.status = "Scheduled"
    db.session.commit()
    flash("Admin reschedule rejected.")
    return redirect(url_for("main.my_packages"))

@main.route("/propose_reschedule/<int:package_id>", methods=["POST"])
@login_required
def propose_reschedule(package_id):
    package = Package.query.get_or_404(package_id)
    new_date_str = request.form.get("new_date")
    if not new_date_str:
        flash("Select a valid date.", "danger")
        return redirect(url_for("main.my_packages"))

    try:
        new_date = datetime.strptime(new_date_str,"%Y-%m-%d")
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for("main.my_packages"))

    package.pickup_date = new_date.date()
    package.status = "Customer Proposed Reschedule"
    db.session.commit()
    flash("New pickup date proposed.")
    return redirect(url_for("main.my_packages"))

@main.route("/admin/package/<int:package_id>/delete", methods=["POST"])
@login_required
def admin_delete_package(package_id):
    # Admin-only protection
    if current_user.role != "admin":
        abort(403)

    package = Package.query.get_or_404(package_id)
    package_id_value = package.id

    # Get photo file paths before deleting the package.
    upload_folder = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(os.getcwd(), "static", "uploads", "packages")
    )

    photo_paths = []

    for photo in package.photos:
        if photo.filename:
            photo_paths.append(
                os.path.join(upload_folder, photo.filename)
            )

    try:
        # SQLAlchemy cascade will remove:
        # - PackagePhoto records
        # - PackageStatusHistory records
        # - PackageContainer records
        db.session.delete(package)
        db.session.commit()

        # Remove physical photo files after successful DB deletion.
        for file_path in photo_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError as e:
                print("PACKAGE PHOTO DELETE ERROR:", e)

        flash(
            f"Package #{package_id_value} was permanently deleted.",
            "success"
        )

    except Exception as e:
        db.session.rollback()
        print("ADMIN PACKAGE DELETE ERROR:", e)

        flash(
            "Unable to delete the package. No changes were made.",
            "danger"
        )

    return redirect(url_for("main.admin_packages"))

@main.route("/my-packages")
@login_required
def my_packages():

    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    packages = Package.query.filter_by(
        user_id=current_user.id
    ).order_by(Package.created_at.desc()).all()

    return render_template("customer/packages.html", packages=packages)


# -------------------
# TRACK PACKAGE (CUSTOMER SEARCH FORM)
# -------------------
@main.route("/track", methods=["GET", "POST"], endpoint="track_page")
def track():

    package = None
    tracking_number = None

    if request.method == "POST":
        tracking_number = request.form.get("tracking_number")

        if tracking_number:
            package = Package.query.filter_by(
                tracking_number=tracking_number.strip().upper()
            ).first()

            if not package:
                flash("No package found with that tracking number.", "warning")

    return render_template(
        "customer/track.html",
        package=package,
        tracking_number=tracking_number
    )


@main.route("/track/<tracking_number>", endpoint="track_public_page")
def track_public(tracking_number):

    package = Package.query.filter_by(
        tracking_number=tracking_number.strip().upper()
    ).first()

    if not package:
        return render_template(
            "customer/track.html",
            package=None,
            tracking_number=tracking_number
        )

    return render_template(
        "customer/track.html",
        package=package,
        tracking_number=tracking_number
    )


@main.route("/analytics")
@login_required
def customer_analytics():

    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    packages = Package.query.filter_by(
        user_id=current_user.id
    ).all()

    total_packages = len(packages)

    pending_deliveries = sum(
        1 for p in packages if p.status and "pending" in p.status.lower()
    )

    delivered_packages = sum(
        1 for p in packages if p.status and "delivered" in p.status.lower()
    )

    in_transit_packages = sum(
        1 for p in packages if p.status and "transit" in p.status.lower()
    )

    return render_template(
        "customer/analytics.html",
        total_packages=total_packages,
        pending_deliveries=pending_deliveries,
        delivered_packages=delivered_packages,
        in_transit_packages=in_transit_packages
    )


######                     #######
###### ADMIN SYSTEM ROUTES #######
######                     ####### 

@main.route("/admin/online-users")
@login_required
@admin_required
def admin_online_users():

    return jsonify(
        list(online_users.values())
    )

@main.route("/admin")
@login_required
@admin_required
def admin_dashboard():

    page = request.args.get("page", 1, type=int)

    packages = Package.query.order_by(
        Package.pickup_date.desc()
    ).paginate(page=page, per_page=20)

    announcements = Announcement.query.order_by(
        Announcement.created_at.desc()
    ).limit(50).all()

    base_query = Package.query

    # -------------------
    # ANALYTICS
    # -------------------
    total_packages = base_query.count()

    pending_deliveries = base_query.filter(
        Package.status.ilike("%pending%")
    ).count()

    delivered_today = base_query.filter(
        Package.status.ilike("%delivered%"),
        Package.updated_at >= datetime.utcnow().date()
    ).count()

    active_users = User.query.filter_by(
        role="customer",
        is_active=True
    ).count()

    # -------------------
    # NEW ACCOUNTS PENDING ACTIVATION
    # -------------------
    pending_activations = User.query.filter_by(
        role="customer",
        is_active=False
    ).count()

    return render_template(
        "admin/admin_dashboard.html",
        packages=packages,
        announcements=announcements,
        total_packages=total_packages,
        pending_deliveries=pending_deliveries,
        delivered_today=delivered_today,
        active_users=active_users,
        pending_activations=pending_activations
    )

#
# --------------ADMIN PACKAGES ROUTES--------------
#

@main.route("/admin/packages")
@login_required
@admin_required
def admin_packages():
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("search", "").strip()
    statuses = [
        "Pending Approval",
        "Approved",
        "Pending",
        "Scheduled",
        "In Warehouse",
        "Loaded",
        "Ready for Pickup",
        "Picked Up",
        "In Transit",
        "Shipped",
        "Delivered",
        "Archived",
        "Cancelled",
        "Pending Reschedule",
        "Admin Suggested Reschedule",
        "Rescheduled"
    ]
    query = Package.query.options(
        selectinload(Package.container_assignments).selectinload(PackageContainer.container)
    ).join(
        Package.user,
        isouter=True
    ).filter(
        Package.status != "Delivered",
        Package.status != "Archived"
    )
    if search_query:
        query = query.filter(or_(
            Package.tracking_number.ilike(f"%{search_query}%"),
            Package.description.ilike(f"%{search_query}%"),
            Package.status.ilike(f"%{search_query}%"),
            User.first_name.ilike(f"%{search_query}%"),
            User.last_name.ilike(f"%{search_query}%"),
            User.phone.ilike(f"%{search_query}%")
        ))
    packages = query.order_by(
        Package.created_at.desc()
    ).paginate(
        page=page,
        per_page=20
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "partials/admin_packages_table.html",
            packages=packages,
            statuses=statuses
        )
    return render_template(
        "admin/admin_packages.html",
        packages=packages,
        statuses=statuses
    )

@main.route("/admin/packages/<int:package_id>/cma-cgm-tracking")
@login_required
@admin_required
def admin_cma_cgm_tracking(package_id):

    package = Package.query.get_or_404(package_id)

    reference = (
        getattr(package, "container_number", None)
        or getattr(package, "tracking_number", None)
    )

    if not reference:
        flash(
            "No CMA CGM tracking reference is assigned to this package.",
            "warning"
        )
        return redirect(url_for("main.admin_packages"))

    try:
        tracking = track_cma_cgm(reference)

    except CmaCgmError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.admin_packages"))

    return render_template(
        "admin/cma_cgm_tracking.html",
        package=package,
        tracking=tracking,
    )

@main.route("/admin/package/<int:package_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_package(package_id):
    print("APPROVE ROUTE HIT")
    package = Package.query.get_or_404(package_id)
    print("PACKAGE FOUND:", package.id)
    if package.tracking_number:
        print("ALREADY HAS TRACKING")
        flash("Package already approved.", "warning")
        return redirect(url_for("main.admin_packages"))
    tracking = generate_tracking()
    print("GENERATED TRACKING:", tracking)
    package.tracking_number = tracking
    package.status = "Scheduled"
    package.updated_at = datetime.utcnow()
    status_history = PackageStatusHistory(
        package_id=package.id,
        status="Scheduled",
        source="ADMIN",
        note="Pickup approved and tracking number generated."
    )
    db.session.add(status_history)
    try:
        db.session.commit()
        print("COMMIT SUCCESS")
    except Exception as e:
        db.session.rollback()
        print("COMMIT FAILED:", e)
        flash("Unable to approve package. Please try again.", "danger")
        return redirect(url_for("main.admin_packages"))
    flash(f"Pickup approved. Tracking #: {package.tracking_number}", "success")
    return redirect(url_for("main.admin_packages"))


@main.route("/admin/package/<int:package_id>/update", methods=["POST"])
@login_required
@admin_required
def admin_update_package(package_id):
    package = Package.query.get_or_404(package_id)
    status = request.form.get("status", "").strip()
    if status:
        old_status = package.status
        package.status = status
        if status == "Delivered":
            if not package.delivered_at:
                package.delivered_at = datetime.utcnow()
            for photo in package.photos:
                photo.delete_at = package.delivered_at + timedelta(days=15)
        else:
            package.delivered_at = None
            for photo in package.photos:
                photo.delete_at = None
        if old_status != status:
            status_history = PackageStatusHistory(
                package_id=package.id,
                status=status,
                source="ADMIN",
                note=f"Status changed from {old_status} to {status}."
            )
            db.session.add(status_history)
    package.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Package updated successfully.", "success")
    return redirect(url_for("main.admin_packages"))



@main.route("/admin/package/<int:package_id>/suggest-reschedule", methods=["POST"])
@login_required
@admin_required
def admin_suggest_reschedule(package_id):

    package = Package.query.get_or_404(package_id)
    new_date_str = request.form.get("new_date")

    if not new_date_str:
        flash("Please provide a date.", "warning")
        return redirect(url_for("main.admin_packages"))

    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for("main.admin_packages"))

    package.admin_suggested_date = new_date
    package.status = "Admin Suggested Reschedule"
    package.updated_at = datetime.utcnow()

    db.session.commit()

    socketio.emit(
        "reschedule_alert",
        {"message": f"New pickup date suggested for {package.tracking_number}"},
        namespace="/customer"
    )

    flash("Reschedule suggestion sent.", "success")
    return redirect(url_for("main.admin_packages"))

@main.route("/admin/package/<int:package_id>/accept-reschedule", methods=["POST"])
@login_required
@admin_required
def admin_accept_reschedule(package_id):
    package = Package.query.get_or_404(package_id)
    if package.admin_suggested_date:
        package.pickup_date = package.admin_suggested_date
    package.admin_suggested_date = None
    package.status = "Scheduled"
    db.session.commit()
    flash("Reschedule accepted.", "success")
    return redirect(url_for("main.admin_packages"))


@main.route("/admin/package/<int:package_id>/reject-reschedule", methods=["POST"])
@login_required
@admin_required
def reject_admin_reschedule(package_id):
    package = Package.query.get_or_404(package_id)
    package.admin_suggested_date = None
    package.status = "Pending"
    db.session.commit()
    flash("Reschedule rejected.", "info")
    return redirect(url_for("main.admin_packages"))

@main.route("/admin/package/<int:package_id>/restore", methods=["POST"])
@login_required
def admin_restore_package(package_id):
    if current_user.role != "admin":
        return "Unauthorized", 403

    package = Package.query.get_or_404(package_id)
    package.status = "Delivered"  # or "Pending" depending on your workflow

    db.session.commit()

    flash("Package restored successfully.", "success")
    return redirect(url_for("main.admin_archived_packages"))

@main.route("/admin/packages/archived")
@login_required
@admin_required
def admin_archived_packages():

    archived = Package.query.filter_by(
        status="Archived"
    ).order_by(Package.id.desc()).all()

    return render_template(
        "admin/admin_archived_packages.html",
        packages=archived
    )


@main.route("/admin/archive-delivered", methods=["POST"])
@login_required
def admin_archive_delivered():
    if current_user.role != "admin":
        return "Unauthorized", 403

    delivered_packages = Package.query.filter_by(status="Delivered").all()

    for p in delivered_packages:
        p.status = "Archived"

    db.session.commit()

    flash("Delivered packages archived successfully.", "success")
    return redirect(url_for("main.admin_packages"))


@main.route("/admin/clear-packages", methods=["POST"])
@login_required
@admin_required
def admin_clear_packages():

    confirm = request.form.get("confirm_text")

    if confirm != "DELETE":
        flash("Type DELETE to confirm.", "danger")
        return redirect(url_for("main.admin_packages"))

    Package.query.delete()
    db.session.commit()

    flash("All packages deleted.", "success")
    return redirect(url_for("main.admin_packages"))

@main.route("/admin/packages/bulk-update", methods=["POST"])
@login_required
@admin_required
def admin_bulk_update_packages():
    package_ids = request.form.getlist("package_ids")

    if not package_ids:
        flash("No packages selected.", "warning")
        return redirect(url_for("main.admin_packages"))

    packages = Package.query.filter(
        Package.id.in_(package_ids)
    ).all()

    status = request.form.get("status")

    if status:
        for package in packages:
            package.status = status

            if status == "Delivered" and not package.delivered_at:
                package.delivered_at = datetime.utcnow()

            elif status != "Delivered":
                package.delivered_at = None

    expected_delivery = request.form.get("expected_delivery")

    if expected_delivery:
        try:
            delivery_date = datetime.strptime(
                expected_delivery, "%Y-%m-%d"
            )

            for package in packages:
                package.expected_delivery = delivery_date

        except ValueError:
            flash("Invalid delivery date.", "danger")
            return redirect(url_for("main.admin_packages"))

    for package in packages:
        package.updated_at = datetime.utcnow()

    db.session.commit()

    flash(
        f"{len(packages)} package(s) updated successfully.",
        "success"
    )

    return redirect(url_for("main.admin_packages"))

#
# --------------ADMIN USERS ROUTES--------------
#

@main.route("/admin/users")
@login_required
@admin_required
def admin_users():

    users = User.query.order_by(User.id.desc()).all()

    return render_template("admin/users.html", users=users)

@main.route("/admin/user/<int:user_id>/promote", methods=["POST"])
@login_required
@admin_required
def promote_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != "admin":
        user.role = "admin"
        db.session.commit()
        flash(f"{user.full_name} is now an admin.", "success")
    else:
        flash(f"{user.full_name} is already an admin.", "info")
    return redirect(url_for("main.admin_users"))


@main.route("/admin/user/<int:user_id>/demote", methods=["POST"])
@login_required
@admin_required
def demote_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        user.role = "customer"
        db.session.commit()
        flash(f"{user.full_name} has been demoted.", "success")
    else:
        flash(f"{user.full_name} is already a customer.", "info")
    return redirect(url_for("main.admin_users"))


@main.route("/admin/user/<int:user_id>/activate", methods=["POST"])
@login_required
@admin_required
def activate_user(user_id):

    user = User.query.get_or_404(user_id)

    user.is_active = True

    db.session.commit()

    flash(f"{user.full_name} activated.", "success")

    return redirect(url_for("main.admin_users"))


@main.route("/admin/user/<int:user_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_id):

    user = User.query.get_or_404(user_id)

    user.is_active = False

    db.session.commit()

    flash(f"{user.full_name} deactivated.", "warning")

    return redirect(url_for("main.admin_users"))


@main.route('/admin/announcements', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_announcements():

    if request.method == 'POST':

        title = request.form.get('title')
        message = request.form.get('message')

        if not title or not message:
            flash("All fields are required.", "danger")
            return redirect(url_for('main.admin_announcements'))

        clean_message = BeautifulSoup(
            message,
            "html.parser"
        ).get_text(separator="\n")

        announcement = Announcement(
            title=title,
            message=clean_message,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        db.session.add(announcement)
        db.session.commit()

        socketio.emit(
            'new_announcement',
            {
                'title': announcement.title,
                'message': announcement.message,
                'expires_at': announcement.expires_at.strftime('%Y-%m-%d')
            },
            namespace='/customer'
        )

        flash("Announcement posted.", "success")
        return redirect(url_for('main.admin_announcements'))

    announcements = Announcement.query.filter(
        Announcement.expires_at > datetime.utcnow()
    ).order_by(Announcement.created_at.desc()).all()

    return render_template(
        "admin/admin_announcements.html",
        announcements=announcements,
        now=datetime.utcnow()
    )

@main.route('/admin/announcements/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_announcement(id):

    announcement = Announcement.query.get_or_404(id)

    if request.method == 'POST':
        announcement.title = request.form['title']
        announcement.message = request.form['message']
        db.session.commit()

        flash("Updated successfully.", "success")
        return redirect(url_for('main.admin_announcements'))

    return render_template(
        "admin/edit_announcement.html",
        announcement=announcement
    )


@main.route("/admin/announcements/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_announcement(id):

    announcement = Announcement.query.get_or_404(id)

    db.session.delete(announcement)
    db.session.commit()

    flash("Announcement deleted.", "success")
    return redirect(url_for("main.admin_announcements"))


@main.route("/admin/packages_table")
@login_required
@admin_required
def admin_packages_table():

    search_query = request.args.get("search", "").strip()

    query = Package.query.join(Package.user, isouter=True)

    if search_query:
        query = query.filter(or_(
            Package.tracking_number.ilike(f"%{search_query}%"),
            Package.description.ilike(f"%{search_query}%"),
            Package.status.ilike(f"%{search_query}%"),
            User.first_name.ilike(f"%{search_query}%"),
            User.last_name.ilike(f"%{search_query}%"),
            User.phone.ilike(f"%{search_query}%")
        ))

    packages = query.order_by(
        Package.created_at.desc()
    ).paginate(page=1, per_page=100)

    return render_template(
        "partials/admin_packages_table.html",
        packages=packages
    )


@main.route("/admin/packages/bulk-action", methods=["POST"])
@login_required
@admin_required
def admin_packages_bulk_action():
    package_ids = request.form.getlist("package_ids")
    action = request.form.get("action", "").strip()
    status = request.form.get("status", "").strip()

    if not package_ids:
        flash("Please select at least one package.", "warning")
        return redirect(request.referrer or url_for("main.admin_packages"))

    packages = Package.query.filter(Package.id.in_(package_ids)).all()

    if not packages:
        flash("No valid packages were selected.", "warning")
        return redirect(request.referrer or url_for("main.admin_packages"))

    # BULK APPROVE
    if action == "approve":
        approved_count = 0
        already_approved = 0

        try:
            for package in packages:
                if package.tracking_number:
                    already_approved += 1
                    continue

                package.tracking_number = generate_tracking()
                package.status = "Scheduled"
                package.updated_at = datetime.utcnow()
                approved_count += 1

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("BULK APPROVE FAILED:", e)
            flash("Bulk approval failed. No packages were changed.", "danger")
            return redirect(request.referrer or url_for("main.admin_packages"))

        if approved_count and already_approved:
            flash(f"{approved_count} package(s) approved. {already_approved} already approved.", "success")
        elif approved_count:
            flash(f"{approved_count} package(s) approved successfully.", "success")
        else:
            flash("All selected packages were already approved.", "warning")

        return redirect(request.referrer or url_for("main.admin_packages"))

    # BULK ARCHIVE
    if action == "archive":
        archived_count = 0

        try:
            for package in packages:
                if package.status == "Archived":
                    continue

                package.status = "Archived"
                package.updated_at = datetime.utcnow()
                archived_count += 1

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("BULK ARCHIVE FAILED:", e)
            flash("Bulk archive failed. No packages were changed.", "danger")
            return redirect(request.referrer or url_for("main.admin_packages"))

        if archived_count:
            flash(f"{archived_count} package(s) archived successfully.", "success")
        else:
            flash("All selected packages were already archived.", "warning")

        return redirect(request.referrer or url_for("main.admin_packages"))

    # BULK STATUS UPDATE
    if action == "update":
        updated_count = 0

        try:
            for package in packages:
                if status:
                    package.status = status

                    if status == "Delivered":
                        if not package.delivered_at:
                            package.delivered_at = datetime.utcnow()

                        for photo in package.photos:
                            photo.delete_at = package.delivered_at + timedelta(days=15)

                    elif status != "Delivered":
                        package.delivered_at = None

                        for photo in package.photos:
                            photo.delete_at = None

                package.updated_at = datetime.utcnow()
                updated_count += 1

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("BULK UPDATE FAILED:", e)
            flash("Bulk update failed. No packages were changed.", "danger")
            return redirect(request.referrer or url_for("main.admin_packages"))

        flash(f"{updated_count} package(s) updated successfully.", "success")
        return redirect(request.referrer or url_for("main.admin_packages"))

    flash("Invalid bulk action.", "danger")
    return redirect(request.referrer or url_for("main.admin_packages"))


@main.route("/admin/audit")
@login_required
@admin_required
def audit_dashboard():

    logs = AuditLog.query.order_by(
        AuditLog.created_at.desc()
    ).limit(200).all()

    return render_template(
        "admin/audit_dashboard.html",
        logs=logs
    )

#
# -------------UTILITIES---------------
#

@main.route("/track", methods=["GET", "POST"])
def track():

    package = None
    tracking_number = None

    if request.method == "POST":
        tracking_number = request.form.get("tracking_number")

        if tracking_number:
            package = Package.query.filter_by(
                tracking_number=tracking_number.strip().upper()
            ).first()

            if not package:
                flash("No package found.", "warning")

    return render_template(
        "customer/track.html",
        package=package,
        tracking_number=tracking_number
    )


@main.route("/track/<tracking_number>")
def track_public(tracking_number):

    package = Package.query.filter_by(
        tracking_number=tracking_number.strip().upper()
    ).first()

    return render_template(
        "customer/track.html",
        package=package,
        tracking_number=tracking_number
    )

@main.route("/customer/package/suggest_description", methods=["POST"])
@login_required
def suggest_description():
    data = request.get_json()
    text = data.get("text", "")

    if not text:
        return jsonify({"suggestion": ""})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful logistics assistant."},
                {"role": "user", "content": f"Rewrite this package description clearly and concisely: {text}"}
            ],
            max_tokens=60,
            temperature=0.7
        )

        suggestion = response.choices[0].message.content.strip()
        return jsonify({"suggestion": suggestion})

    except Exception as e:
        print("OpenAI error:", e)
        return jsonify({"suggestion": "Error generating suggestion"}), 500

@main.route("/customer/chatbot", methods=["POST"])
@login_required
def customer_chatbot():

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"answer": "Please ask a question."})

    try:
        context = """
You are a helpful customer support assistant for KSK Cargo.

You help users with:
- Package tracking and status explanations
- Pickup scheduling
- Delivery rescheduling
- Package cancellation
- General shipping questions

Rules:
- Be concise
- Be friendly and professional
- If you don't know package-specific info, ask for tracking number
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": question}
            ],
            temperature=0.6,
            max_tokens=180
        )

        answer = response.choices[0].message.content.strip()

        return jsonify({"answer": answer})

    except Exception as e:

        import traceback

        print("🔥 CHATBOT ERROR:", repr(e))
        traceback.print_exc()

        if "insufficient_quota" in str(e):
            return jsonify({
            "answer": "The AI assistant is temporarily unavailable. Please try again later."
        }), 200

        return jsonify({
        "answer": "Sorry, the AI assistant is currently unavailable."
        }), 500