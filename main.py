from threading import Thread
import asyncio
from bot import main as bot_main  # bot.py ka async main

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_main())

# Background me bot start karo
Thread(target=run_bot, daemon=True).start()

# Flask app
from flask import Flask
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


