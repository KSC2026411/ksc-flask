from app import create_app
from app.extensions import socketio
import os

print("🚀 RUN.PY ENTRY POINT EXECUTING")

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print(f"🌍 Starting server on port {port}")
    print(f"🔐 Debug mode: {app.config.get('DEV_MODE')}")
    print("🧠 Database configured")

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        allow_unsafe_werkzeug=True  # ✅ THIS FIXES YOUR ERROR
    )