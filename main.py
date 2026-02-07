from flask import Flask
import threading
import os

from bot import main as bot_main

app = Flask(__name__)

@app.route("/")
def home():
    return "Telegram bot is running 🚀"

def run_bot():
    bot_main()

if __name__ == "__main__":
    # Bot ko background thread me chalao
    threading.Thread(target=run_bot).start()

    # Render ka port bind
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
