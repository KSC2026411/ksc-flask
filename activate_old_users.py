# activate_old_users.py
from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():
    old_users = User.query.filter_by(is_active=False).all()
    for u in old_users:
        u.is_active = True
    db.session.commit()
    print(f"{len(old_users)} old users activated")