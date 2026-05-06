from datetime import datetime, timedelta
from app import db
from app.models import Package

def cleanup_delivered_packages():
    cutoff = datetime.utcnow() - timedelta(days=14)

    old_packages = Package.query.filter(
        Package.status == "delivered",
        Package.delivered_at < cutoff
    ).all()

    for pkg in old_packages:
        db.session.delete(pkg)

    db.session.commit()