import os
import random
import string
from datetime import datetime, timedelta
from functools import wraps
from flask_migrate import Migrate

from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash

import stripe
from models import db, User, Package, Announcement

# -------------------
# APP CONFIG
# -------------------
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["DEV_MODE"] = os.environ.get("DEV_MODE", "false").lower() == "true"

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
migrate = Migrate(app, db)

socketio = SocketIO(app, async_mode='eventlet')
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_123")

# -------------------
# HELPERS
# -------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)

        if not (current_user.role == "admin" or current_user.is_admin):
            abort(403)

        return f(*args, **kwargs)

    return decorated_function

def generate_tracking(length=10):
    return "TRK" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# -------------------
# LOGIN MANAGER
# -------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------
# CACHE CONTROL
# -------------------
@app.after_request
def add_header(response):
    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True
    return response

# -------------------
# STATIC FILES
# -------------------
@app.route('/static/css/<path:filename>')
def serve_static_file(filename):
    return send_from_directory('static/css', filename)

# -------------------
# PUBLIC ROUTES
# -------------------
@app.route("/")
def home():
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("home.html", announcements=announcements)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email already registered")
            return redirect(url_for("register"))

        user = User(name=name, email=email, phone=phone)
        user.password = password
        db.session.add(user)
        db.session.commit()
        flash("Account created. Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.name}!")
            return redirect(url_for("admin_dashboard") if user.role == "admin" else url_for("home"))
        flash("Invalid email or password")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully")
    return redirect(url_for("home"))

@app.route("/track", methods=["GET", "POST"])
def track():
    package = None
    if request.method == "POST":
        tracking_number = request.form.get("tracking_number")
        package = Package.query.filter_by(tracking_number=tracking_number).first()
    return render_template("track.html", package=package)

# -------------------
# DEV ADMIN LOGIN (TEMP)
# -------------------
@app.route("/dev-admin-login")
def dev_admin_login():
    if not app.config.get("DEV_MODE"):
        abort(403)

    user = User.query.filter_by(email="admin@test.com").first()

    if not user:
        user = User(
            name="Admin",
            email="admin@test.com",
            phone="0000000000",
            role="admin",
            is_admin=True
        )
        user.password = "admin123"
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(url_for("admin_dashboard"))

# -------------------
# USER ROUTES
# -------------------
@app.route("/schedule", methods=["GET", "POST"])
@login_required
def schedule():
    if request.method == "POST":
        description = request.form.get("description")
        street = request.form.get("street")
        city = request.form.get("city")
        state = request.form.get("state")
        zip_code = request.form.get("zip")
        phone = request.form.get("phone")
        pickup_date_str = request.form.get("date")

        if not all([description, street, city, state, zip_code, phone, pickup_date_str]):
            flash("All fields are required!")
            return redirect(url_for("schedule"))

        try:
            pickup_datetime = datetime.strptime(pickup_date_str, "%Y-%m-%d")
        except ValueError:
            flash("Invalid pickup date!")
            return redirect(url_for("schedule"))

        # ✅ STRICT 72-HOUR RULE
        if pickup_datetime < (datetime.now() + timedelta(hours=72)):
            flash("Pickup must be at least 72 hours (3 days) from now.")
            return redirect(url_for("schedule"))

        # Store only date in DB (your model uses Date)
        pickup_date = pickup_datetime.date()

        package = Package(
            tracking_number=generate_tracking(),
            description=description,
            street=street,
            city=city,
            state=state,
            zip_code=zip_code,
            user_id=current_user.id,
            pickup_date=pickup_date
        )

        db.session.add(package)
        db.session.commit()

        socketio.emit(
            "update_packages",
            {"message": f"New package scheduled by {current_user.name}"},
            namespace="/admin"
        )

        flash("Pickup scheduled! Please pay $50 cash at pickup.")
        return redirect(url_for("home"))

    return render_template("schedule.html")


@app.route("/my-packages")
@login_required
def my_packages():
    packages = Package.query.filter_by(user_id=current_user.id).all()
    return render_template(
        "packages.html",
        packages=packages,
        timedelta=timedelta,
        current_time=datetime.utcnow().date()
    )


@app.route("/customer/package/<int:id>/reschedule", methods=["POST"])
@login_required
def reschedule_package(id):
    # Get the package
    package = Package.query.get_or_404(id)

    # Only the owner can reschedule
    if package.user_id != current_user.id:
        flash("You cannot reschedule this package.")
        return redirect(url_for("my_packages"))

    # Get new date from form
    new_date_str = request.form.get("new_date")
    if not new_date_str:
        flash("Please select a new date.")
        return redirect(url_for("my_packages"))

    try:
        new_datetime = datetime.strptime(new_date_str, "%Y-%m-%d")
    except ValueError:
        flash("Invalid date format.")
        return redirect(url_for("my_packages"))

    # Enforce 72-hour rule for customers only
    if not current_user.is_admin:
        if new_datetime < datetime.now() + timedelta(hours=72):
            flash("Rescheduled date must be at least 72 hours from now.")
            return redirect(url_for("my_packages"))

    # Optional: track reschedule attempts
    package.reschedule_attempts = (package.reschedule_attempts or 0) + 1
    if package.reschedule_attempts > 3:
        flash("You have reached the maximum number of reschedules.")
        return redirect(url_for("my_packages"))

    # Update pickup date
    package.pickup_date = new_datetime.date()
    package.status = "Pending Reschedule"

    db.session.commit()

    flash("Package reschedule request submitted successfully.")
    return redirect(url_for("my_packages"))


@app.route('/customer/package/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_package(id):
    package = Package.query.get_or_404(id)

    if package.status in ['Picked Up', 'Delivered']:
        flash("Cannot cancel a package already picked up or delivered.")
        return redirect(url_for('my_packages'))

    now = datetime.utcnow().date()
    if (package.pickup_date - now).days < 3:
        flash("Cancellations allowed only 72 hours before pickup date.")
        return redirect(url_for('my_packages'))

    package.status = "Cancelled"
    db.session.commit()

    socketio.emit('update_packages', {'message': f'Package {package.tracking_number} was cancelled'}, namespace='/admin')
    flash(f"Package {package.tracking_number} has been cancelled.")
    return redirect(url_for('my_packages'))

@app.route('/customer/package/<int:id>/accept-reschedule', methods=['POST'])
@login_required
def customer_accept_admin_reschedule(id):
    package = Package.query.get_or_404(id)

    if package.user_id != current_user.id:
        flash("Unauthorized action.")
        return redirect(url_for("my_packages"))

    if package.status != "Admin Suggested Reschedule":
        flash("No admin reschedule to accept.")
        return redirect(url_for("my_packages"))

    # ⛔ 24-hour expiry check
    if package.updated_at and package.updated_at < datetime.utcnow() - timedelta(hours=24):
        flash("This reschedule offer has expired.")
        return redirect(url_for("my_packages"))

    if package.admin_suggested_date:
        package.pickup_date = package.admin_suggested_date

    package.status = "Scheduled"
    package.admin_suggested_date = None

    db.session.commit()

    flash("Reschedule accepted.")
    return redirect(url_for("my_packages"))

@app.route('/customer/package/<int:id>/reject-reschedule', methods=['POST'])
@login_required
def customer_reject_admin_reschedule(id):
    package = Package.query.get_or_404(id)

    if package.user_id != current_user.id:
        flash("Unauthorized action.")
        return redirect(url_for("my_packages"))

    if package.status != "Admin Suggested Reschedule":
        flash("No admin reschedule to reject.")
        return redirect(url_for("my_packages"))

    # ⛔ 24-hour expiry check
    if package.updated_at and package.updated_at < datetime.utcnow() - timedelta(hours=24):
        flash("This reschedule offer has expired.")
        return redirect(url_for("my_packages"))

    package.admin_suggested_date = None
    package.status = "Scheduled"

    db.session.commit()

    flash("Admin reschedule rejected.")
    return redirect(url_for("my_packages"))


# -------------------
# ADMIN ROUTES
# -------------------
@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    packages = Package.query.order_by(Package.pickup_date.desc()).all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin_dashboard.html", packages=packages, announcements=announcements)

@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template("users.html", users=users)

@app.route("/admin/announcements", methods=["GET", "POST"])
@login_required
@admin_required
def admin_announcements():
    if request.method == "POST":
        announcement = Announcement(
            title=request.form["title"],
            message=request.form["message"]
        )
        db.session.add(announcement)
        db.session.commit()
        flash("Announcement posted")

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("announcements.html", announcements=announcements)

@app.route("/admin/packages")
@login_required
@admin_required
def admin_packages():
    packages = Package.query.all()
    return render_template("admin_packages.html", packages=packages)

@app.route('/admin/package/<int:id>/update', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_update_package(id):
    package = Package.query.get_or_404(id)
    new_status = request.form.get("status")

    if new_status:
        package.status = new_status
        db.session.commit()
        flash("Package updated successfully")

    return redirect(url_for("admin_packages"))

@app.route("/admin/package/<int:id>/accept-reschedule", methods=["POST"])
@login_required
@admin_required
def accept_admin_reschedule(id):
    package = Package.query.get_or_404(id)

    # Apply admin suggested date
    if package.admin_suggested_date:
        package.pickup_date = package.admin_suggested_date

    # Reset suggestion + status
    package.admin_suggested_date = None
    package.status = "Scheduled"

    db.session.commit()

    flash("Reschedule accepted.")
    return redirect(url_for("admin_packages"))

@app.route("/admin/package/<int:id>/reject-reschedule", methods=["POST"])
@login_required
@admin_required
def reject_admin_reschedule(id):
    package = Package.query.get_or_404(id)

    # Clear admin suggestion
    package.admin_suggested_date = None

    # Allow customer to reschedule again
    package.status = "Pending"

    db.session.commit()

    flash("Reschedule rejected. Customer can choose a new date.")
    return redirect(url_for("admin_packages"))

@app.route("/admin/packages_table")
@login_required
@admin_required
def admin_packages_table():
    search_query = request.args.get("search", "").strip()
    if search_query:
        packages = Package.query.filter(Package.tracking_number.ilike(f"%{search_query}%")).all()
    else:
        packages = Package.query.order_by(Package.created_at.desc()).all()
    return render_template("partials/admin_packages_table.html", packages=packages)

@app.route('/admin/package/<int:id>/suggest-reschedule', methods=['POST'])
@login_required
@admin_required
def admin_suggest_reschedule(id):
    package = Package.query.get_or_404(id)

    new_date_str = request.form.get("new_date")
    if not new_date_str:
        flash("Please provide a new date.")
        return redirect(url_for("admin_packages"))

    new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()

    # ✅ store admin suggested date (DO NOT overwrite pickup_date)
    package.admin_suggested_date = new_date
    package.status = "Admin Suggested Reschedule"

    # ✅ IMPORTANT: update timestamp for 24-hour acceptance window
    package.updated_at = datetime.utcnow()

    db.session.commit()

    # 🔔 REAL-TIME NOTIFICATION (customer side)
    socketio.emit(
        "reschedule_alert",
        {
            "message": f"New pickup date suggested for {package.tracking_number}"
        },
        namespace="/customer"
    )

    flash("Reschedule suggestion sent to user.")
    return redirect(url_for("admin_packages"))


# -------------------
# SOCKETIO
# -------------------
@socketio.on('connect', namespace='/admin')
def admin_connect():
    print("Admin connected")

# -------------------
# RUN
# -------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # -------------------
        # TEMP ADMIN (DEV ONLY)
        # -------------------
        if os.environ.get("DEV_MODE") == "true":
            admin_email = "admin@test.com"
            admin_password = "admin123"

            existing_admin = User.query.filter_by(email=admin_email).first()
            if not existing_admin:
                admin = User(
                    name="Admin",
                    email=admin_email,
                    phone="0000000000",
                    role="admin"
                )
                admin.password = admin_password
                db.session.add(admin)
                db.session.commit()
                print(f"Temporary admin created: {admin_email} / {admin_password}")

    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )