from app import app
from models import db, User

with app.app_context():
    admin = User.query.filter_by(email="admin@test.com").first()

    if not admin:
        admin = User(
            name="Admin",
            email="admin@test.com",
            phone="0000000000",
            role="admin",
            is_admin=True
        )
        admin.password = "admin123"
        db.session.add(admin)

    admin.role = "admin"
    admin.is_admin = True

    db.session.commit()

    print("ADMIN READY")