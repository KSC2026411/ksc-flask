# app/events.py

import traceback
from datetime import datetime

from flask import request
from flask_login import current_user

from .extensions import socketio


# =====================================================
# ONLINE USERS TRACKER
# =====================================================

# user_id -> user info
online_users = {}

# socket_id -> user_id
active_sids = {}


def emit_online_users():
    """
    Send current online users list to admin dashboard.
    """

    socketio.emit(
        "online_users_update",
        {
            "count": len(online_users),
            "users": list(online_users.values())
        },
        namespace="/admin"
    )


# =====================================================
# PACKAGE UPDATE HELPER
# =====================================================

def emit_package_update(package):
    """
    Broadcast package updates to customer namespace.
    """

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

        print("Package update emit error:", e)
        traceback.print_exc()


# =====================================================
# SOCKET.IO EVENTS
# =====================================================

def register_socketio_events(app):

    # =================================================
    # CUSTOMER NAMESPACE
    # =================================================

    @socketio.on("connect", namespace="/customer")
    def customer_connect():

        print(f"Customer connected: {request.sid}")

        if not current_user.is_authenticated:
            return

        # track socket -> user
        active_sids[request.sid] = current_user.id

        # track online user
        online_users[current_user.id] = {
            "id": current_user.id,
            "name": current_user.full_name,
            "email": current_user.email,
            "role": current_user.role
        }

        print(
            f"Online Users: {len(online_users)} "
            f"({current_user.full_name})"
        )

        emit_online_users()

    @socketio.on("disconnect", namespace="/customer")
    def customer_disconnect():

        print(f"Customer disconnected: {request.sid}")

        user_id = active_sids.pop(request.sid, None)

        if not user_id:
            return

        # Check if user still has another tab/window open
        still_connected = user_id in active_sids.values()

        if not still_connected:
            online_users.pop(user_id, None)

        print(f"Online Users: {len(online_users)}")

        emit_online_users()

    @socketio.on("cargo_update", namespace="/customer")
    def handle_cargo_update(data):

        print(f"Received cargo update: {data}")

        try:

            socketio.emit(
                "cargo_update",
                data,
                namespace="/customer"
            )

        except Exception as e:

            print("Cargo update error:", e)
            traceback.print_exc()

    # =================================================
    # ADMIN NAMESPACE
    # =================================================

    @socketio.on("connect", namespace="/admin")
    def admin_connect():

        print(f"Admin connected: {request.sid}")

        emit_online_users()

    @socketio.on("disconnect", namespace="/admin")
    def admin_disconnect():

        print(f"Admin disconnected: {request.sid}")