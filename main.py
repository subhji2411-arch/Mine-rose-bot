import threading
from bot import main as bot_main

def run_bot():
    bot_main()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()

    # dummy loop so Render thinks service is alive
    import time
    while True:
        time.sleep(60)
