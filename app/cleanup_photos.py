from datetime import datetime
from app import create_app
from app.extensions import db
from app.models import PackagePhoto
import os

app = create_app()

with app.app_context():
    now = datetime.utcnow()
    photos = PackagePhoto.query.filter(
        PackagePhoto.delete_at.isnot(None),
        PackagePhoto.delete_at <= now
    ).all()

    deleted = 0

    for photo in photos:
        filepath = os.path.join(
            app.root_path,
            "static",
            "uploads",
            "packages",
            photo.filename
        )

        try:
            if os.path.exists(filepath):
                os.remove(filepath)

            db.session.delete(photo)
            deleted += 1

        except Exception as e:
            print(f"PHOTO DELETE FAILED {photo.id}: {e}")

    db.session.commit()

    print(f"PHOTO CLEANUP COMPLETE: {deleted} photo(s) deleted.")