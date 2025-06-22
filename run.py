# /run.py
import threading
import webbrowser
from app import create_app, utils

app = create_app()

if __name__ == '__main__':
    url = "http://127.0.0.1:5000"
    print(f"Starting server, opening browser at {url}")

    with app.app_context():
        utils.run_initial_setup()

    # Pass the app instance to the background thread's arguments
    # threading.Thread(target=utils.sync_cache_with_watchlist, args=(app,), daemon=True).start()

    threading.Timer(1.25, lambda: webbrowser.open(url)).start()
    app.run(port=5000, debug=False)