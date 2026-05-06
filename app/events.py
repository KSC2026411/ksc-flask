# app/events.py
import threading
import time
import traceback
from flask import request
from datetime import datetime

from .extensions import socketio, db
from .models import Package


def register_socketio_events(app):

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
        print(f"Received cargo update from client: {data}")
        try:
            socketio.emit(
                "cargo_update",
                data,
                namespace="/customer",
                broadcast=True
            )
        except Exception as e:
            print(f"Error emitting cargo_update: {e}")
            traceback.print_exc()

    # -------------------
    # BACKGROUND UPDATER
    # -------------------
    def cargo_status_updater():
        with app.app_context():
            while True:
                try:
                    packages = Package.query.all()

                    for package in packages:
                        try:
                            data = {
                                "cargo_id": package.id,
                                "status": package.status,
                                "last_updated": (
                                    package.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                                    if hasattr(package, "updated_at") and package.updated_at
                                    else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                )
                            }

                            socketio.emit(
                                "cargo_update",
                                data,
                                namespace="/customer"
                            )

                        except Exception as inner_error:
                            # prevents one bad package from breaking loop
                            print("Package processing error:", inner_error)
                            traceback.print_exc()
                            db.session.rollback()

                except Exception as e:
                    print("Background updater error:", e)
                    traceback.print_exc()
                    db.session.rollback()   # 🔥 CRITICAL FIX

                time.sleep(5)

    # Start thread
    threading.Thread(target=cargo_status_updater, daemon=True).start()
    print("Background cargo updater started.")