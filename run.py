# run.py
import os
from app import create_app
from app.extensions import socketio

# Create Flask app
app = create_app()

if __name__ == "__main__":
    # Use Railway PORT environment variable
    port = int(os.environ.get("PORT", 5000))

    # Run Socket.IO with threading mode
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,  # Turn off debug in production
    )