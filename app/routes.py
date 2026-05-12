from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, login_user, logout_user, current_user
from .models import User, Package, Announcement, PushSubscription, AuditLog
from .extensions import db, socketio
from datetime import datetime, timedelta
from flask_wtf.csrf import CSRFProtect
from .decorators import admin_required
from .utils import generate_tracking, send_push_notification
from sqlalchemy import text, or_
from bs4 import BeautifulSoup
from flask import render_template
import json

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
    return render_template("public/offline.html")

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

    return render_template(
        "public/home.html",
        announcements=announcements,
        now=now
    )

@main.route("/save-subscription", methods=["POST"])
@login_required
def save_subscription():

    try:

        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "error": "No data"
            }), 400

        subscription_json = json.dumps(data)

        # ======================================
        # 🔐 ONE SUBSCRIPTION PER USER (SECURE)
        # ======================================
        existing = PushSubscription.query.filter_by(
            user_id=current_user.id
        ).first()

        if existing:
            existing.subscription = subscription_json
        else:
            new_subscription = PushSubscription(
                user_id=current_user.id,
                subscription=subscription_json
            )
            db.session.add(new_subscription)

        db.session.commit()

        return jsonify({
            "success": True
        })

    except Exception as e:

        print("❌ SAVE SUBSCRIPTION ERROR:", e)

        return jsonify({
            "success": False
        }), 500

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

    return render_template("public/register.html")


@main.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        # Normalize email
        email = email.strip().lower() if email else None

        user = User.query.filter_by(email=email).first()

        # ======================================
        # AUTH CHECK
        # ======================================
        if user and user.check_password(password):

            # BLOCK deactivated users
            if not user.active:
                flash("Your account is deactivated. Contact admin.", "danger")
                return redirect(url_for("main.login"))

            login_user(user)

            flash(f"Welcome back, {user.name}!", "success")

            # Redirect by role
            if user.role == "admin":
                return redirect(url_for("main.admin_dashboard"))
            else:
                return redirect(url_for("main.dashboard"))

        flash("Invalid email or password", "danger")

    return render_template("public/login.html")


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
        "admin/users.html",
        users=users
    )

@main.route("/admin/packages/archived")
@login_required
def admin_archived_packages():
    if current_user.role != "admin":
        return "Unauthorized", 403

    archived = Package.query.filter_by(status="Archived").order_by(Package.id.desc()).all()

    return render_template("admin/admin_archived_packages.html", packages=archived)

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

@main.route("/admin/audit")
@login_required
def audit_dashboard():

    if current_user.role != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for("main.home"))

    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()

    return render_template("admin/audit_dashboard.html", logs=logs)




# -------------------
# CUSTOMER DASHBOARD
# -------------------
@main.route("/dashboard")
@login_required
def dashboard():
    if current_user.role != "customer":
        flash("Admins cannot access customer pages.", "warning")
        return redirect(url_for("main.admin_dashboard"))

    # --- Fetch announcements ---
    now = datetime.utcnow()
    announcements = Announcement.query.filter(
        Announcement.expires_at.isnot(None),
        Announcement.expires_at > now
    ).order_by(Announcement.created_at.desc()).all()

    # --- Fetch packages for current customer ---
    packages = Package.query.filter_by(user_id=current_user.id).order_by(Package.created_at.desc()).all()

    # --- Analytics numbers ---
    total_packages = len(packages)
    pending_deliveries = sum(1 for p in packages if p.status == 'pending')
    delivered_packages = sum(1 for p in packages if p.status == 'delivered')
    in_transit_packages = sum(1 for p in packages if p.status == 'in_transit')

    # --- Render template with all data ---
    return render_template(
        "customer/customer_dashboard.html",
        announcements=announcements,
        packages=packages,
        total_packages=total_packages,
        pending_deliveries=pending_deliveries,
        delivered_packages=delivered_packages,
        in_transit_packages=in_transit_packages
    )


# -------------------
# SCHEDULE PICKUP
# -------------------
@main.route("/schedule", methods=["GET", "POST"])
@login_required
def schedule():

    # ======================================
    # 🔐 BLOCK ADMINS FROM CUSTOMER FLOW
    # ======================================
    if current_user.role == "admin":
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

        # ======================================
        # 🔐 INPUT VALIDATION
        # ======================================
        if not all([description, street, city, state, zip_code, phone, pickup_date_str]):
            flash("All fields are required!", "warning")
            return redirect(url_for("main.schedule"))

        try:
            pickup_datetime = datetime.strptime(pickup_date_str, "%Y-%m-%d")
        except ValueError:
            flash("Invalid pickup date!", "danger")
            return redirect(url_for("main.schedule"))

        # ======================================
        # 🔐 BUSINESS RULE (72 HOURS RULE)
        # ======================================
        if pickup_datetime < datetime.now() + timedelta(hours=72):
            flash("Pickup must be at least 72 hours from now.", "warning")
            return redirect(url_for("main.schedule"))

        # ======================================
        # 🔐 CREATE PACKAGE
        # ======================================
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

        db.session.add(package)

        # ======================================
        # 📊 AUDIT LOG (PHASE 2)
        # ======================================
        try:
            log = AuditLog(
                user_id=current_user.id,
                action="schedule_pickup",
                details=f"Pickup scheduled: {package.tracking_number}",
                ip_address=request.remote_addr,
                status="success"
            )
            db.session.add(log)

        except Exception as e:
            print("Audit log error:", e)

        db.session.commit()

        # ======================================
        # 🔔 NOTIFY ADMINS
        # ======================================
        admins = User.query.filter_by(role="admin").all()

        for admin in admins:
            try:
                send_push_notification(
                    user_id=admin.id,
                    title="New Pickup Request",
                    body=f"{current_user.name} submitted a pickup request",
                    url="/admin/pickups",
                    badge=1
                )
            except Exception as e:
                print(f"Push failed for admin {admin.id}: {e}")

        # ======================================
        # ✅ SUCCESS
        # ======================================
        flash(
            "Pickup scheduled! Please send $75 Zelle deposit 48H before pickup date.",
            "success"
        )

        return redirect(url_for("main.schedule"))

    return render_template("customer/schedule.html")


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
    return render_template("customer/packages.html", packages=packages)


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
                flash("No package found with that tracking number.", "warning")

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

    if not package:
        return render_template("track.html", package=None, tracking_number=tracking_number)

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

    # Fetch all packages for the current customer
    packages = Package.query.filter_by(user_id=current_user.id).order_by(Package.created_at.desc()).all()

    # Compute analytics
    total_packages = len(packages)
    pending_deliveries = sum(1 for p in packages if p.status == "Pending")
    delivered_packages = sum(1 for p in packages if p.status == "Delivered")
    in_transit_packages = sum(1 for p in packages if p.status == "In Transit")

    return render_template(
        "customer/analytics.html",
        total_packages=total_packages,
        pending_deliveries=pending_deliveries,
        delivered_packages=delivered_packages,
        in_transit_packages=in_transit_packages
    )

# -------------------
# ADMIN DASHBOARD
# -------------------
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

    # ======================================
    # ⚡ LIVE SYNC MODE (AJAX REFRESH SUPPORT)
    # ======================================
    if request.headers.get("X-Live-Sync") == "true":

        return render_template(
            "admin/admin_dashboard.html",
            packages=packages,
            announcements=announcements,

            # REAL-TIME STATS
            total_packages=Package.query.count(),

            pending_deliveries=Package.query.filter(
                Package.status.ilike("%pending%")
            ).count(),

            delivered_today=Package.query.filter(
                Package.status.ilike("%delivered%")
            ).count(),

            active_users=User.query.filter_by(
                role="customer",
                active=True
            ).count()
        )

    # ======================================
    # NORMAL PAGE LOAD
    # ======================================
    return render_template(
        "admin/admin_dashboard.html",
        packages=packages,
        announcements=announcements
    )


# -------------------
# ADMIN PACKAGES
# -------------------

@main.route("/admin/packages")
@login_required
@admin_required
def admin_packages():
    # Get current page number
    page = request.args.get("page", 1, type=int)
    
    # Get search query
    search_query = request.args.get("search", "").strip()
    
    # Base query with optional join to User
    query = Package.query.join(Package.user, isouter=True)
    
    # Apply search filter if query exists
    if search_query:
        search_filter = or_(
            Package.tracking_number.ilike(f"%{search_query}%"),
            Package.description.ilike(f"%{search_query}%"),
            Package.status.ilike(f"%{search_query}%"),
            Package.notes.ilike(f"%{search_query}%"),
            User.name.ilike(f"%{search_query}%"),
            User.phone.ilike(f"%{search_query}%")
        )
        query = query.filter(search_filter)
    
    # Paginate results
    packages = query.order_by(Package.created_at.desc()).paginate(page=page, per_page=20)
    
    # If AJAX request, render only the table rows
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template("partials/admin_packages_table.html", packages=packages)
    
    # Full page render
    return render_template("admin/admin_packages.html", packages=packages)


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

@main.route("/admin/package/<int:package_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_package(package_id):

    package = Package.query.get_or_404(package_id)

    # Prevent duplicate approvals
    if package.tracking_number:
        flash("Package already approved.", "warning")
        return redirect(url_for("main.admin_packages"))

    # Generate tracking number only now
    package.tracking_number = generate_tracking()

    # Update status
    package.status = "Scheduled"

    db.session.commit()

    flash(
        f"Pickup approved. Tracking #: {package.tracking_number}",
        "success"
    )

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
@admin_required
def admin_announcements():

    if request.method == 'POST':

        title = request.form.get('title')
        message = request.form.get('message')

        if not title or not message:
            flash("All fields are required.", "danger")
            return redirect(url_for('main.admin_announcements'))

        # ======================================
        # 🧼 SANITIZE INPUT
        # ======================================
        clean_message = BeautifulSoup(
            message,
            "html.parser"
        ).get_text(separator="\n")

        new_announcement = Announcement(
            title=title,
            message=clean_message,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        db.session.add(new_announcement)
        db.session.commit()

        # ======================================
        # 📡 REAL-TIME UPDATE
        # ======================================
        socketio.emit(
            'new_announcement',
            {
                'title': new_announcement.title,
                'message': new_announcement.message,
                'expires_at': new_announcement.expires_at.strftime('%Y-%m-%d')
            },
            namespace='/customer'
        )

        flash("Announcement posted successfully.", "success")
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
def edit_announcement(id):
    announcement = Announcement.query.get_or_404(id)

    if request.method == 'POST':
        if current_user.role != 'admin':
            abort(403)
        announcement.title = request.form['title']
        announcement.message = request.form['message']
        db.session.commit()
        return redirect(url_for('main.admin_announcements'))

    return render_template("admin/edit_announcement.html", announcement=announcement)


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

    query = Package.query.join(Package.user, isouter=True)

    if search_query:

        search_filter = or_(
            Package.tracking_number.ilike(f"%{search_query}%"),
            Package.description.ilike(f"%{search_query}%"),
            Package.status.ilike(f"%{search_query}%"),
            Package.notes.ilike(f"%{search_query}%"),
            User.name.ilike(f"%{search_query}%"),
            User.phone.ilike(f"%{search_query}%")
        )

        query = query.filter(search_filter)

    packages = query.order_by(
        Package.created_at.desc()
    ).paginate(page=1, per_page=100)

    return render_template(
        "partials/admin_packages_table.html",
        packages=packages
    )