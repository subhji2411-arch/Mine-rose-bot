import os
import signal
import asyncio
from flask import Flask, request, jsonify
from bot import process_update_from_json  # helper from bot.py

PORT = int(os.getenv("PORT", "8443"))
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram webhook path

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "OK - Web service running", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook_receiver():
    json_update = request.get_json(force=True)
    if json_update:
        asyncio.run(process_update_from_json(json_update))
    return jsonify({"status": "ok"}), 200

def _graceful_shutdown(signum, frame):
    print("Shutting down gracefully...")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    app.run(host="0.0.0.0", port=PORT)
