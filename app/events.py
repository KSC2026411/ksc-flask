# app/events.py

import traceback
from flask import request
from datetime import datetime

from .extensions import socketio, db
from .models import Package


# -----------------------------
# HELPER: emit package update
# -----------------------------
def emit_package_update(package):
    try:
        data = {
            "cargo_id": package.id,
            "status": package.status,
            "last_updated": (
                package.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if package.updated_at
                else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )
        }

        socketio.emit(
            "cargo_update",
            data,
            namespace="/customer"
        )

    except Exception as e:
        print("Emit error:", e)
        traceback.print_exc()


# -----------------------------
# SOCKET.IO EVENTS
# -----------------------------
def register_socketio_events(app):

    @socketio.on("connect", namespace="/customer")
    def handle_connect():
        print(f"Customer connected: {request.sid}")

    @socketio.on("disconnect", namespace="/customer")
    def handle_disconnect():
        print(f"Customer disconnected: {request.sid}")

    @socketio.on("cargo_update", namespace="/customer")
    def handle_cargo_update(data):
        """
        Optional: client-triggered updates (admin panel etc.)
        """
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