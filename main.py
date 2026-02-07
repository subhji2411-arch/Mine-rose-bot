# main.py
from threading import Thread
import asyncio
from bot import main as bot_main  # async main

def run_bot():
    asyncio.run(bot_main())  # directly run in main thread of asyncio

Thread(target=run_bot, daemon=True).start()  # Flask ke start se pehle

from flask import Flask
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
