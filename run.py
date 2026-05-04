import os
from app import create_app
from app.extensions import socketio

print("🚀 RUN.PY ENTRY POINT EXECUTING")

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    print(f"🌍 Starting server on port {port}")
    print(f"🔐 Debug mode: {debug_mode}")
    print("🧠 Database configured")

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug_mode,
    )