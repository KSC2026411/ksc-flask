from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, login_user, logout_user, current_user
from .models import User, Package, Announcement
from .extensions import db, socketio
from datetime import datetime, timedelta
from flask_wtf.csrf import CSRFProtect
from .decorators import admin_required
from .utils import generate_tracking
from sqlalchemy import text
from bs4 import BeautifulSoup
from flask import render_template

main = Blueprint("main", __name__)
csrf = CSRFProtect()  # Enable in create_app()

@main.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception as e:
        return {"status": "error", "details": str(e)}, 500

# -------------------
# PUBLIC ROUTES
# -------------------
@main.route("/test")
def test():
    return "TEST OK"

@main.route("/offline")
def offline():
    return render_template("offline.html")

@main.route("/")
def home():
    now = datetime.utcnow()
    try:
        expired = Announcement.query.filter(
            Announcement.expires_at.isnot(None),
            Announcement.expires_at <= now
        ).all()
        for a in expired:
            db.session.delete(a)
        db.session.commit()

        announcements = Announcement.query.filter(
            Announcement.expires_at.isnot(None),
            Announcement.expires_at > now
        ).order_by(Announcement.created_at.desc()).all()

    except Exception as e:
        db.session.rollback()
        print("DB ERROR:", e)
        announcements = []

    return render_template("home.html", announcements=announcements, now=now)


# -------------------
# AUTHENTICATION
# -------------------
@main.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "warning")
            return redirect(url_for("main.register"))

        user = User(name=name, email=email, phone=phone, role="customer")
        user.password = password
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please login.", "success")
        return redirect(url_for("main.login"))

    return render_template("register.html")


@main.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Normalize email (avoids login issues)
        email = email.strip().lower() if email else None

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):

            # 🚫 BLOCK ONLY if explicitly deactivated
            if user.active is False:
                flash("Your account is deactivated. Contact admin to reactivate.", "danger")
                return redirect(url_for("main.login"))

            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")

            return redirect(
                url_for("main.admin_dashboard")
                if user.role == "admin"
                else url_for("main.dashboard")
            )

        flash("Invalid email or password", "danger")

    return render_template("login.html")

@main.route("/login", methods=["POST"])
def login_route():
    email = request.form["email"]
    password = request.form["password"]

    user = get_user_from_db(email)

    success, message = login(user, password)

    if success:
        return redirect("/dashboard")
    else:
        return message, 401


@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("main.home"))


# -------------------
# ADMIN: USERS
# -------------------
@main.route("/admin/users")
@login_required
@admin_required
def admin_users():

    # newest users first
    users = User.query.order_by(User.id.desc()).all()

    return render_template(
        "users.html",
        users=users
    )

@main.route("/admin/clear-packages", methods=["POST"])
@login_required
def admin_clear_packages():
    if current_user.role != "admin":
        return "Unauthorized", 403

    confirm = request.form.get("confirm_text")

    if confirm != "DELETE":
        flash("You must type DELETE to confirm.", "danger")
        return redirect(url_for("main.admin_packages_table"))

    # (optional backup step could go here)

    Package.query.delete()
    db.session.commit()

    flash("All pickup schedules deleted successfully.", "success")
    return redirect(url_for("main.admin_packages_table"))

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


@main.route("/admin/user/<int:user_id>/promote", methods=["POST"])
@login_required
@admin_required
def promote_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != "admin":
        user.role = "admin"
        db.session.commit()
        flash(f"{user.name} is now an admin.", "success")
    else:
        flash(f"{user.name} is already an admin.", "info")
    return redirect(url_for("main.admin_users"))


@main.route("/admin/user/<int:user_id>/demote", methods=["POST"])
@login_required
@admin_required
def demote_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        user.role = "customer"
        db.session.commit()
        flash(f"{user.name} has been demoted.", "success")
    else:
        flash(f"{user.name} is already a customer.", "info")
    return redirect(url_for("main.admin_users"))

@main.route("/admin/user/<int:user_id>/activate", methods=["POST"])
@login_required
@admin_required
def activate_user(user_id):
    user = User.query.get_or_404(user_id)

    user.active = True
    db.session.commit()

    flash(f"{user.name} has been activated.", "success")
    return redirect(url_for("main.admin_users"))

@main.route("/admin/user/<int:user_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)

    user.active = False
    db.session.commit()

    flash(f"{user.name} has been deactivated.", "warning")
    return redirect(url_for("main.admin_users"))

@main.route("/admin/packages/archived")
@login_required
def admin_archived_packages():
    if current_user.role != "admin":
        return "Unauthorized", 403

    archived = Package.query.filter_by(status="Archived").order_by(Package.id.desc()).all()

    return render_template("admin_archived_packages.html", packages=archived)

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




# -------------------
# CUSTOMER DASHBOARD
# -------------------
@main.route("/dashboard")
@login_required
def dashboard():
    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    now = datetime.utcnow()
    announcements = Announcement.query.filter(
        Announcement.expires_at.isnot(None),
        Announcement.expires_at > now
    ).order_by(Announcement.created_at.desc()).all()
    return render_template("customer_dashboard.html", announcements=announcements)


# -------------------
# SCHEDULE PICKUP
# -------------------
@main.route("/schedule", methods=["GET","POST"])
@login_required
def schedule():
    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    if request.method == "POST":
        description = request.form.get("description")
        street = request.form.get("street")
        city = request.form.get("city")
        state = request.form.get("state")
        zip_code = request.form.get("zip")
        phone = request.form.get("phone")
        pickup_date_str = request.form.get("date")

        if not all([description, street, city, state, zip_code, phone, pickup_date_str]):
            flash("All fields are required!", "warning")
            return redirect(url_for("main.schedule"))

        try:
            pickup_datetime = datetime.strptime(pickup_date_str,"%Y-%m-%d")
        except ValueError:
            flash("Invalid pickup date!", "danger")
            return redirect(url_for("main.schedule"))

        if pickup_datetime < datetime.now() + timedelta(hours=72):
            flash("Pickup must be at least 72 hours from now.", "warning")
            return redirect(url_for("main.schedule"))

        package = Package(
            tracking_number=generate_tracking(),
            description=description,
            street=street,
            city=city,
            state=state,
            zip_code=zip_code,
            user_id=current_user.id,
            pickup_date=pickup_datetime.date()
        )
        db.session.add(package)
        db.session.commit()
        flash("Pickup scheduled! Please send $75 Zelle deposit 48H before pickup date.", "success")
        return redirect(url_for("main.schedule"))

    return render_template("schedule.html")


# -------------------
# MY PACKAGES
# -------------------
@main.route("/my-packages")
@login_required
def my_packages():
    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    packages = Package.query.filter_by(user_id=current_user.id).all()
    return render_template("packages.html", packages=packages)


# -------------------
# PACKAGE ACTIONS (Customer)
# -------------------
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

@main.route("/customer/package/<int:package_id>/cancel", methods=["POST"])
@login_required
def cancel_package(package_id):
    package = Package.query.get_or_404(package_id)
    if package.user_id != current_user.id:
        flash("Unauthorized.")
        return redirect(url_for("main.my_packages"))

    if package.status in ["Picked Up","Delivered"]:
        flash("Cannot cancel picked up or delivered packages.")
        return redirect(url_for("main.my_packages"))

    if (package.pickup_date - datetime.utcnow().date()).days < 3:
        flash("Cancellations allowed only 72 hours before pickup date.")
        return redirect(url_for("main.my_packages"))

    package.status = "Cancelled"
    db.session.commit()
    socketio.emit("update_packages", {"message": f"Package {package.tracking_number} cancelled"}, namespace="/admin")
    flash("Package cancelled.")
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


# -------------------
# TRACK PACKAGE
# -------------------
@main.route("/track", methods=["GET","POST"])
@login_required
def track():
    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    package = None
    if request.method == "POST":
        tracking_number = request.form.get("tracking_number")
        if tracking_number:
            package = Package.query.filter_by(tracking_number=tracking_number).first()
            if not package:
                flash(f"No package found with tracking number {tracking_number}", "warning")
    return render_template("track.html", package=package)

# -------------------
# ADMIN DASHBOARD
# -------------------
@main.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    packages = Package.query.order_by(Package.pickup_date.desc()).all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin_dashboard.html", packages=packages, announcements=announcements)


# -------------------
# ADMIN PACKAGES
# -------------------
@main.route("/admin/packages")
@login_required
@admin_required
def admin_packages():
    packages = Package.query.order_by(Package.created_at.desc()).all()
    return render_template("admin_packages.html", packages=packages)


@main.route("/admin/package/<int:package_id>/update", methods=["POST"])
@login_required
@admin_required
def admin_update_package(package_id):
    package = Package.query.get_or_404(package_id)
    new_status = request.form.get("status")
    if new_status:
        package.status = new_status
        db.session.commit()
        flash(f"Package {package.tracking_number} updated.", "success")
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

    flash("Reschedule suggestion sent to customer.", "success")
    return redirect(url_for("main.admin_packages"))


# -------------------
# ADMIN ANNOUNCEMENTS
# -------------------
@main.route('/admin/announcements', methods=['GET', 'POST'])
@login_required
def admin_announcements():
    if current_user.role != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')

        if not title or not message:
            flash("All fields are required.", "danger")
            return redirect(url_for('main.admin_announcements'))

        # ✅ STRIP HTML TAGS HERE
        clean_message = BeautifulSoup(message, "html.parser").get_text(separator="\n")

        new_announcement = Announcement(
            title=title,
            message=clean_message,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        db.session.add(new_announcement)
        db.session.commit()

        # realtime push
        socketio.emit('new_announcement', {
            'title': new_announcement.title,
            'message': new_announcement.message,
            'expires_at': new_announcement.expires_at.strftime('%Y-%m-%d')
        }, namespace='/customer')

        flash("Announcement posted successfully.", "success")
        return redirect(url_for('main.admin_announcements'))

    announcements = Announcement.query.filter(
        Announcement.expires_at > datetime.utcnow()
    ).order_by(Announcement.created_at.desc()).all()

    return render_template(
        "admin_announcements.html",
        announcements=announcements,
        now=datetime.utcnow()
    )

@main.route('/admin/announcements/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_announcement(id):
    announcement = Announcement.query.get_or_404(id)

    if request.method == 'POST':
        if current_user.role != 'admin':
            abort(403)
        announcement.title = request.form['title']
        announcement.message = request.form['message']
        db.session.commit()
        return redirect(url_for('main.admin_announcements'))

    return render_template('edit_announcement.html', announcement=announcement)


@main.route("/admin/announcements/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_announcement(id):
    announcement = Announcement.query.get_or_404(id)
    db.session.delete(announcement)
    db.session.commit()
    flash("Announcement deleted.", "success")
    return redirect(url_for("main.admin_announcements"))


# -------------------
# ADMIN: PARTIAL TABLE (AJAX)
# -------------------
@main.route("/admin/packages_table")
@login_required
@admin_required
def admin_packages_table():
    search_query = request.args.get("search", "").strip()
    if search_query:
        packages = Package.query.filter(Package.tracking_number.ilike(f"%{search_query}%")).all()
    else:
        packages = Package.query.order_by(Package.created_at.desc()).all()
    return render_template("partials/admin_packages_table.html", packages=packages)