# app/events.py

import traceback
from flask import request
from flask_login import current_user
from datetime import datetime

from .extensions import socketio, db
from .models import Package

# -----------------------------
# ONLINE USERS TRACKER
# -----------------------------
online_users = set()


def emit_online_users():
    socketio.emit(
        "online_users_update",
        {"count": len(online_users)},
        namespace="/customer"
    )

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
# HELPER: broadcast online users
# -----------------------------
def emit_online_users():

    users = list(online_users.values())

    socketio.emit(
        "online_users_update",
        users,
        namespace="/admin"
    )


# -----------------------------
# SOCKET.IO EVENTS
# -----------------------------
def register_socketio_events(app):

    # =============================
    # CUSTOMER SOCKETS
    # =============================
    @socketio.on("connect", namespace="/customer")
    def handle_connect():

        print(f"Customer connected: {request.sid}")

        if current_user.is_authenticated:

            online_users[current_user.id] = {
                "id": current_user.id,
                "name": current_user.full_name,
                "email": current_user.email,
                "role": current_user.role
            }

            emit_online_users()

    @socketio.on("disconnect", namespace="/customer")
    def handle_disconnect():

        print(f"Customer disconnected: {request.sid}")

        if current_user.is_authenticated:

            online_users.pop(current_user.id, None)

            emit_online_users()

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

    # =============================
    # ADMIN SOCKETS
    # =============================
    @socketio.on("connect", namespace="/admin")
    def admin_connect():

        print(f"Admin connected: {request.sid}")

        emit_online_users()

    @socketio.on("disconnect", namespace="/admin")
    def admin_disconnect():

        print(f"Admin disconnected: {request.sid}")