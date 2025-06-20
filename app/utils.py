# /app/utils.py
from datetime import datetime
from collections import Counter
from flask import current_app
from . import data_manager
from . import tmdb_api

def format_runtime(minutes):
    """Jinja filter to format minutes into hours and minutes (e.g., 135 -> 2h 15m)."""
    if not minutes: return ""
    try:
        minutes = int(minutes)
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0: return f"{hours}h {mins}m"
        return f"{mins}m"
    except (ValueError, TypeError):
        return ""

def run_initial_setup():
    """Performs initial application setup tasks."""
    print("Performing initial setup...")
    api_key = current_app.config['TMDB_API_KEY']
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("\n" + "=" * 50 + "\nWARNING: TMDB_API_KEY is not set in config.py!\n" + "=" * 50 + "\n")
    data_manager.load_watchlist()
    print("Initial setup complete.")

def sync_cache_with_watchlist(app):
    """Ensures all items in the watchlist have up-to-date metadata in the cache."""
    with app.app_context(): # <--- This line is the fix
        print("Syncing metadata cache with watchlist...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
        fetched_count = 0

        all_item_ids = {
            'movie': {str(m['id']) for m in watchlist['watched']['movies'] + watchlist['planned']['movies']},
            'series': {str(s['id']) for s in watchlist['planned']['series']} | set(watchlist['watched']['series'].keys())
        }

        for mid in all_item_ids['movie']:
            if mid not in cache['movies'] or 'watch_providers' not in cache['movies'][mid]:
                if tmdb_api.get_movie_details(int(mid)): fetched_count += 1
        for sid in all_item_ids['series']:
            if sid not in cache['series'] or 'watch_providers' not in cache['series'][sid]:
                if tmdb_api.get_series_details(int(sid)): fetched_count += 1

        if fetched_count > 0:
            print(f"Sync complete. Fetched metadata for {fetched_count} item(s).")
        else:
            print("Cache is up to date.")


def get_smart_suggestions(item_type):
    """Generates personalized suggestions based on watched items."""
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    today = datetime.now()
    singular_type = 'movie' if item_type == 'movies' else 'series'
    user_item_ids = {item['id'] for item in watchlist['planned'][item_type]}
    if item_type == 'movies':
        user_item_ids.update(item['id'] for item in watchlist['watched']['movies'])
        source_items = watchlist['watched']['movies']
    else:  # 'series'
        user_item_ids.update(int(id) for id in watchlist['watched']['series'])
        source_items = list(watchlist['watched']['series'].values())

    scores, recommendation_data = {}, {}
    for item in source_items:
        id_str = str(item['id'])
        if id_str not in cache[item_type] or 'recommendations' not in cache[item_type][id_str]:
            continue

        rating = item.get('rating')
        if rating is None: continue # Skip items that have not been rated

        if item_type == 'movies':
            date_str = item.get('watched_on')
        else:
            date_str = max((e['watched_on'] for e in item['watched_episodes'].values() if e.get('watched_on')), default=None) if item.get('watched_episodes') else None
        if not date_str: continue

        try:
            days_since_watched = max(0, (today - datetime.strptime(date_str, '%Y-%m-%d')).days)
            base_score = (rating ** 2) * (0.98 ** days_since_watched)

            for rec in cache[item_type][id_str].get('recommendations', []):
                if rec.get('id') and rec['id'] not in user_item_ids:
                    scores[rec['id']] = scores.get(rec['id'], 0) + base_score
                    if rec['id'] not in recommendation_data:
                        recommendation_data[rec['id']] = {**rec, 'type': singular_type}
        except (ValueError, TypeError):
            continue

    sorted_recs = sorted(scores.items(), key=lambda i: i[1], reverse=True)
    return [recommendation_data[id] for id, score in sorted_recs[:12]]