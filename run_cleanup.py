from app import create_app
from app.tasks import cleanup_delivered_packages

app = create_app()

with app.app_context():
    cleanup_delivered_packages()