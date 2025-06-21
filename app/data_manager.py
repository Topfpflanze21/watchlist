# /app/data_manager.py
import os
import json
import uuid
from flask import current_app


def load_json_file(filename, default_data):
    """Loads a JSON file, returning default data if it doesn't exist or is empty/invalid."""
    if not os.path.exists(filename):
        return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else default_data
    except (IOError, json.JSONDecodeError):
        return default_data


def save_json_file(filename, data):
    """Saves data to a JSON file with pretty printing."""
    # Ensure the directory exists before writing the file
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4)


def migrate_watchlist_add_uuids_to_movies(watchlist):
    """Adds unique IDs to legacy movie watch records for easier identification."""
    made_changes = False
    if 'movies' in watchlist.get('watched', {}) and isinstance(watchlist['watched']['movies'], list):
        for record in watchlist['watched']['movies']:
            if 'watch_id' not in record:
                record['watch_id'] = str(uuid.uuid4())
                made_changes = True
    return made_changes


def migrate_series_to_multi_watch(watchlist):
    """Migrates series data to support multiple watch-throughs."""
    made_changes = False
    watched_series = watchlist.get('watched', {}).get('series', {})
    for series_id, data in watched_series.items():
        if isinstance(data, dict):  # Old format: series_id -> {details}
            print(f"Migrating series {series_id} to multi-watch format.")
            new_watch_record = {"series_watch_id": str(uuid.uuid4()), "watched_episodes": data.get("watched_episodes", {})}
            if 'rating' in data:
                new_watch_record['rating'] = data['rating']
            watched_series[series_id] = [new_watch_record]  # New format: series_id -> [list of watches]
            made_changes = True
    return made_changes


def load_watchlist():
    """Loads the main watchlist data, performing data migrations if necessary."""
    watchlist_file = current_app.config['WATCHLIST_FILE']
    default = {"watched": {"movies": [], "series": {}}, "planned": {"movies": [], "series": []}, "user_preferences": {"providers": []}}
    watchlist = load_json_file(watchlist_file, default)

    # Run migrations for older data formats
    if migrate_watchlist_add_uuids_to_movies(watchlist):
        print("Migrating movie watchlist: Added unique IDs.")
        save_json_file(watchlist_file, watchlist)

    if migrate_series_to_multi_watch(watchlist):
        print("Migrating series data to new multi-watch format.")
        save_json_file(watchlist_file, watchlist)

    if 'series' not in watchlist.get('watched', {}) or isinstance(watchlist['watched']['series'], list):
        print("Migrating series data to new episode-tracking format.")
        watchlist['watched']['series'] = {}  # Replace old list with new dict format
        save_json_file(watchlist_file, watchlist)
        print("Series data migration complete.")

    if 'user_preferences' not in watchlist:
        watchlist['user_preferences'] = {"providers": []}
        save_json_file(watchlist_file, watchlist)

    return watchlist


def save_watchlist(data):
    """Saves the main watchlist data."""
    save_json_file(current_app.config['WATCHLIST_FILE'], data)


def load_cache():
    """Loads the metadata cache."""
    return load_json_file(current_app.config['CACHE_FILE'], {"movies": {}, "series": {}, "providers_cache": {}})


def save_cache(data):
    """Saves the metadata cache."""
    save_json_file(current_app.config['CACHE_FILE'], data)