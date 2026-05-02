import threading
import time
from flask import request, current_app
from .extensions import socketio, db
from .models import Package  # Use your existing Package model
from datetime import datetime

def register_socketio_events(app):
    """
    Register all Socket.IO events and start the background updater.
    """
    # -------------------
    # SOCKET.IO EVENTS
    # -------------------
    @socketio.on("connect", namespace="/customer")
    def handle_connect():
        print(f"Customer connected: {request.sid}")

    @socketio.on("disconnect", namespace="/customer")
    def handle_disconnect():
        print(f"Customer disconnected: {request.sid}")

    @socketio.on("cargo_update", namespace="/customer")
    def handle_cargo_update(data):
        """
        Handles client-initiated cargo updates.
        Broadcasts the update to all connected customers.
        """
        print(f"Received cargo update from client: {data}")
        socketio.emit(
            "cargo_update",
            data,
            namespace="/customer",
            broadcast=True  # Ensures all connected customers get it
        )

    # -------------------
    # BACKGROUND PACKAGE UPDATER THREAD
    # -------------------
    def cargo_status_updater():
        """
        Continuously fetch package statuses from the database
        and broadcast them to all connected clients every 5 seconds.
        """
        with app.app_context():
            while True:
                try:
                    packages = Package.query.all()  # Use Package model
                    for package in packages:
                        data = {
                            "cargo_id": package.id,
                            "status": package.status,
                            "last_updated": package.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                            if hasattr(package, "updated_at") else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        socketio.emit("cargo_update", data, namespace="/customer")
                except Exception as e:
                    print(f"Error broadcasting package updates: {e}")
                time.sleep(5)  # Update interval in seconds

    # Start background updater thread
    threading.Thread(target=cargo_status_updater, daemon=True).start()
    print("Background cargo updater started.")