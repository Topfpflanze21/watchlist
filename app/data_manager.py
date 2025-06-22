# /app/data_manager.py
import os
import json
import uuid
from flask import current_app
from flask_login import current_user
from werkzeug.security import generate_password_hash

# --- Path Helpers ---
def get_user_data_path(filename):
    """Returns the full path to a data file for the current logged-in user."""
    if not current_user or not current_user.is_authenticated:
        return None
    user_dir = os.path.join('data', 'user_data', str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, filename)

def get_base_data_path(filename):
    """Returns the path to a file in the root data directory."""
    return os.path.join('data', filename)

# --- Generic JSON Load/Save ---
def load_json_file(filename, default_data):
    """Loads a JSON file, returning default data if it doesn't exist or is empty/invalid."""
    if not filename or not os.path.exists(filename):
        return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else default_data
    except (IOError, json.JSONDecodeError):
        return default_data

def save_json_file(filename, data):
    """Saves data to a JSON file with pretty printing."""
    if not filename: return
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- User Management ---
def get_users_db():
    """Loads the user database."""
    return load_json_file(get_base_data_path('users.json'), {"users": [], "next_id": 1})

def save_users_db(db):
    """Saves the user database."""
    save_json_file(get_base_data_path('users.json'), db)

def find_user_by_username(username):
    """Finds a user by their username."""
    db = get_users_db()
    return next((user for user in db['users'] if user['username'].lower() == username.lower()), None)

def find_user_by_id(user_id):
    """Finds a user by their ID."""
    db = get_users_db()
    return next((user for user in db['users'] if str(user['id']) == str(user_id)), None)

def update_user(user_id, new_username=None, new_password=None):
    """Updates a user's username and/or password."""
    db = get_users_db()
    user_found = False
    for user in db['users']:
        if str(user['id']) == str(user_id):
            if new_username:
                user['username'] = new_username
            if new_password:
                user['password_hash'] = generate_password_hash(new_password)
            user_found = True
            break
    if user_found:
        save_users_db(db)
    return user_found

# --- Watchlist, Cache, and Suggestions (Now User-Specific) ---
def load_watchlist():
    """Loads the current user's watchlist."""
    watchlist_file = get_user_data_path(current_app.config['WATCHLIST_FILE'])
    # Default structure for a new user's watchlist
    default = {"watched": {"movies": [], "series": {}}, "planned": {"movies": [], "series": []}, "user_preferences": {"providers": []}}
    return load_json_file(watchlist_file, default)

def save_watchlist(data):
    """Saves the current user's watchlist."""
    save_json_file(get_user_data_path(current_app.config['WATCHLIST_FILE']), data)

def load_cache():
    """Loads the current user's metadata cache."""
    return load_json_file(get_user_data_path(current_app.config['CACHE_FILE']), {"movies": {}, "series": {}, "providers_cache": {}, "collections": {}})

def save_cache(data):
    """Saves the current user's metadata cache."""
    save_json_file(get_user_data_path(current_app.config['CACHE_FILE']), data)

def load_suggestions_cache():
    """Loads the current user's suggestions cache."""
    return load_json_file(get_user_data_path(current_app.config['SUGGESTIONS_CACHE_FILE']), {})

def save_suggestions_cache(data):
    """Saves the current user's suggestions cache."""
    save_json_file(get_user_data_path(current_app.config['SUGGESTIONS_CACHE_FILE']), data)

def clear_suggestions_cache():
    """Deletes the current user's suggestions cache file."""
    cache_file = get_user_data_path(current_app.config.get('SUGGESTIONS_CACHE_FILE'))
    if cache_file and os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print(f"Suggestions cache cleared for user {current_user.id}.")
        except OSError as e:
            print(f"Error clearing suggestions cache: {e}")