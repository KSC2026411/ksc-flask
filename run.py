import os
from app import create_app
from app.extensions import socketio

print("🚀 RUN.PY ENTRY POINT EXECUTING")

# Create Flask app
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print(f"🌍 Starting server on port {port}")
    print(f"🧠 ENV: DATABASE_URL = {os.getenv('DATABASE_URL')[:50] if os.getenv('DATABASE_URL') else 'None'}")

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
    )