from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, login_user, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text, or_
from bs4 import BeautifulSoup

from datetime import datetime, timedelta
import json

from .models import User, Package, Announcement, PushSubscription, AuditLog
from .extensions import db, socketio
from .decorators import admin_required
from .utils import generate_tracking, send_push_notification

main = Blueprint("main", __name__)
csrf = CSRFProtect()


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

        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")

        email = email.strip().lower() if email else None

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "warning")
            return redirect(url_for("main.register"))

        user = User(
            name=name,
            email=email,
            phone=phone,
            role="customer"
        )
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

        email = email.strip().lower() if email else None

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):

            if not user.active:
                flash("Your account is deactivated. Contact admin.", "danger")
                return redirect(url_for("main.login"))

            login_user(user)

            flash(f"Welcome back, {user.name}!", "success")

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


######                        #######
###### CUSTOMER SYSTEM ROUTES #######
######                        #######

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

    packages = Package.query.filter_by(
        user_id=current_user.id
    ).order_by(Package.created_at.desc()).all()

    # -------------------
    # FIXED ANALYTICS (CASE-SAFE)
    # -------------------
    total_packages = len(packages)

    pending_deliveries = sum(
        1 for p in packages
        if p.status and "pending" in p.status.lower()
    )

    delivered_packages = sum(
        1 for p in packages
        if p.status and "delivered" in p.status.lower()
    )

    in_transit_packages = sum(
        1 for p in packages
        if p.status and "transit" in p.status.lower()
    )

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
            pickup_datetime = datetime.strptime(pickup_date_str, "%Y-%m-%d")
        except ValueError:
            flash("Invalid pickup date!", "danger")
            return redirect(url_for("main.schedule"))

        if pickup_datetime < datetime.now() + timedelta(hours=72):
            flash("Pickup must be at least 72 hours from now.", "warning")
            return redirect(url_for("main.schedule"))

        # -------------------
        # IMPORTANT FIX:
        # tracking_number = NONE until admin approval
        # -------------------
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
        db.session.commit()

        flash(
            "Pickup scheduled successfully. Await admin approval.",
            "success"
        )

        return redirect(url_for("main.schedule"))

    return render_template("customer/schedule.html")



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
    # FIXED ANALYTICS LOGIC
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
        active=True
    ).count()

    if request.headers.get("X-Live-Sync") == "true":
        return render_template(
            "admin/admin_dashboard.html",
            packages=packages,
            announcements=announcements,
            total_packages=total_packages,
            pending_deliveries=pending_deliveries,
            delivered_today=delivered_today,
            active_users=active_users
        )

    return render_template(
        "admin/admin_dashboard.html",
        packages=packages,
        announcements=announcements,
        total_packages=total_packages,
        pending_deliveries=pending_deliveries,
        delivered_today=delivered_today,
        active_users=active_users
    )



@main.route("/admin/packages")
@login_required
@admin_required
def admin_packages():

    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("search", "").strip()

    query = Package.query.join(Package.user, isouter=True)

    if search_query:
        query = query.filter(or_(
            Package.tracking_number.ilike(f"%{search_query}%"),
            Package.description.ilike(f"%{search_query}%"),
            Package.status.ilike(f"%{search_query}%"),
            User.name.ilike(f"%{search_query}%"),
            User.phone.ilike(f"%{search_query}%")
        ))

    packages = query.order_by(
        Package.created_at.desc()
    ).paginate(page=page, per_page=20)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "partials/admin_packages_table.html",
            packages=packages
        )

    return render_template(
        "admin/admin_packages.html",
        packages=packages
    )


@main.route("/admin/package/<int:package_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_package(package_id):

    package = Package.query.get_or_404(package_id)

    # prevent double approval
    if package.tracking_number:
        flash("Package already approved.", "warning")
        return redirect(url_for("main.admin_packages"))

    # ONLY HERE tracking number is generated
    package.tracking_number = generate_tracking()

    package.status = "Scheduled"
    package.updated_at = datetime.utcnow()

    db.session.commit()

    flash(
        f"Pickup approved. Tracking #: {package.tracking_number}",
        "success"
    )

    return redirect(url_for("main.admin_packages"))


@main.route("/admin/package/<int:package_id>/update", methods=["POST"])
@login_required
@admin_required
def admin_update_package(package_id):

    package = Package.query.get_or_404(package_id)
    new_status = request.form.get("status")

    if new_status:
        package.status = new_status
        package.updated_at = datetime.utcnow()
        db.session.commit()

        flash(f"Package {package.tracking_number} updated.", "success")

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


@main.route("/admin/users")
@login_required
@admin_required
def admin_users():

    users = User.query.order_by(User.id.desc()).all()

    return render_template("admin/users.html", users=users)


@main.route("/admin/user/<int:user_id>/activate", methods=["POST"])
@login_required
@admin_required
def activate_user(user_id):

    user = User.query.get_or_404(user_id)
    user.active = True

    db.session.commit()

    flash(f"{user.name} activated.", "success")
    return redirect(url_for("main.admin_users"))


@main.route("/admin/user/<int:user_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_id):

    user = User.query.get_or_404(user_id)
    user.active = False

    db.session.commit()

    flash(f"{user.name} deactivated.", "warning")
    return redirect(url_for("main.admin_users"))


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
            User.name.ilike(f"%{search_query}%"),
            User.phone.ilike(f"%{search_query}%")
        ))

    packages = query.order_by(
        Package.created_at.desc()
    ).paginate(page=1, per_page=100)

    return render_template(
        "partials/admin_packages_table.html",
        packages=packages
    )

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



