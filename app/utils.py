# /app/utils.py
from datetime import datetime
from collections import Counter, defaultdict
from flask import current_app
from . import data_manager
from . import tmdb_api
import random
import math

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
    print("Initial setup complete.")

def sync_cache_with_watchlist(app):
    """Ensures all items in the watchlist have up-to-date metadata in the cache."""
    with app.app_context():  # <--- This line is the fix
        print("Syncing metadata cache with watchlist...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
        fetched_count = 0

        all_item_ids = {'movie': {str(m['id']) for m in watchlist['watched']['movies'] + watchlist['planned']['movies']}, 'series': {str(s['id']) for s in watchlist['planned']['series']} | set(watchlist['watched']['series'].keys())}

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

    # Get all items the user has already seen or planned to see to avoid re-recommending them
    user_item_ids = {item['id'] for item in watchlist['planned'][item_type]}
    if item_type == 'movies':
        user_item_ids.update(item['id'] for item in watchlist['watched']['movies'])
        source_items = [item for item in watchlist['watched']['movies'] if item.get('rating') is not None]
    else:  # 'series'
        user_item_ids.update(int(id) for id in watchlist['watched']['series'])
        source_items = []
        for sid, watch_throughs in watchlist['watched']['series'].items():
            for watch in watch_throughs:
                if watch.get('rating') is not None:
                    source_items.append({'id': int(sid), 'rating': watch.get('rating'), 'watched_episodes': watch.get('watched_episodes', {})})

    scores = {}
    recommendation_data = {}

    # Calculate influence scores for all recommendations
    for item in source_items:
        id_str = str(item['id'])
        if id_str not in cache[item_type] or 'recommendations' not in cache[item_type][id_str]:
            continue

        rating = item.get('rating')
        base_influence = rating - 3.0

        if item_type == 'movies':
            date_str = item.get('watched_on')
        else:
            date_str = max((e['watched_on'] for e in item['watched_episodes'].values() if e.get('watched_on')), default=None) if item.get('watched_episodes') else None

        time_decay = 1.0
        if date_str:
            try:
                days_since_watched = max(0, (today - datetime.strptime(date_str, '%Y-%m-%d')).days)
                time_decay = 0.997 ** days_since_watched
            except (ValueError, TypeError):
                pass

        influence_score = base_influence * time_decay

        for rec in cache[item_type][id_str].get('recommendations', []):
            rec_id = rec.get('id')
            if rec_id and rec_id not in user_item_ids:
                scores[rec_id] = scores.get(rec_id, 0) + influence_score
                if rec_id not in recommendation_data:
                    recommendation_data[rec_id] = {**rec, 'type': singular_type}

    # Perform a weighted random sort
    weighted_suggestions = []
    temperature = 5.0  # Higher temp = more randomness; lower = more score-based

    for rec_id, score in scores.items():
        try:
            # Use math.exp to handle positive/negative scores and create a weighted key
            weight = math.exp(score / temperature)
        except OverflowError:
            weight = float('inf')  # Handle potential for very large scores

        random_sort_key = random.random() * weight
        weighted_suggestions.append((rec_id, random_sort_key))

    # Sort by the new weighted random key
    weighted_suggestions.sort(key=lambda x: x[1], reverse=True)

    # Reconstruct the final list in the new order
    final_list = [recommendation_data[id] for id, key in weighted_suggestions if id in recommendation_data]

    return final_list

def get_weighted_planned_suggestions(item_type, watchlist, cache):
    """
    Generates a probabilistically sorted list of suggestions from the 'Plan to Watch' list.
    The probability is weighted by similarity to the user's rated watch history.
    """
    internal_type = 'movies' if item_type == 'movie' else 'series'
    planned_items = watchlist['planned'][internal_type]

    # 1. Prepare watched items list with relevant data for scoring
    watched_items_for_scoring = []
    if internal_type == 'movies':
        watches_by_id = defaultdict(list)
        for watch in watchlist['watched']['movies']:
            watches_by_id[watch['id']].append(watch)
        for item_id, watches in watches_by_id.items():
            if watches:
                latest_watch = max(watches, key=lambda x: x.get('watched_on') or '0001-01-01')
                watched_items_for_scoring.append(latest_watch)
    else:  # series
        for sid, watch_throughs in watchlist['watched']['series'].items():
            if sid in cache['series'] and watch_throughs:
                latest_watch = max(watch_throughs, key=lambda w: max((e.get('watched_on') or '0001-01-01' for e in w.get('watched_episodes', {}).values()), default='0001-01-01'))
                last_watched_date = max((e.get('watched_on') for e in latest_watch.get('watched_episodes', {}).values() if e.get('watched_on')), default=None)
                latest_watch_with_id = {**latest_watch, 'id': int(sid), 'watched_on': last_watched_date}
                watched_items_for_scoring.append(latest_watch_with_id)

    if not any(w.get('rating') for w in watched_items_for_scoring):
        random.shuffle(planned_items)
        return planned_items

    today = datetime.now()
    item_scores = {}

    # 2. Pre-calculate influence of each watched item
    watched_item_influences = []
    for w_item in watched_items_for_scoring:
        rating = w_item.get('rating')
        if rating is None: continue
        rating_influence = rating - 3.0
        time_decay, date_str = 1.0, w_item.get('watched_on')
        if date_str:
            try:
                days_since = (today - datetime.strptime(date_str, '%Y-%m-%d')).days
                time_decay = 0.997 ** max(0, days_since)
            except (ValueError, TypeError):
                pass
        base_influence = rating_influence * time_decay
        w_item_id = str(w_item['id'])
        w_item_details = cache.get(internal_type, {}).get(w_item_id)
        if w_item_details:
            watched_item_influences.append({'influence': base_influence, 'details': w_item_details})

    # 3. Score each planned item based on similarity to watched items
    for p_item in planned_items:
        p_item_id = str(p_item['id'])
        p_item_details = cache.get(internal_type, {}).get(p_item_id)
        if not p_item_details: continue
        current_score = 0.0
        p_genres = set(g.strip() for g in p_item_details.get('genre', '').split(',') if g.strip())
        p_actors = set(a.strip() for a in p_item_details.get('actors', '').split(',')[:3] if a.strip())
        p_director = p_item_details.get('director') or p_item_details.get('creator', '')
        for w_influence in watched_item_influences:
            w_details = w_influence['details']
            w_genres = set(g.strip() for g in w_details.get('genre', '').split(',') if g.strip())
            w_actors = set(a.strip() for a in w_details.get('actors', '').split(',')[:3] if a.strip())
            w_director = w_details.get('director') or w_details.get('creator', '')
            genre_overlap = len(p_genres.intersection(w_genres))
            actor_overlap = len(p_actors.intersection(w_actors))
            director_match = 3.0 if p_director and p_director == w_director else 0
            similarity = (genre_overlap * 1.0) + (actor_overlap * 0.5) + director_match
            if similarity > 0:
                current_score += w_influence['influence'] * similarity
        item_scores[p_item_id] = current_score

    # 4. Perform a weighted random sort
    weighted_planned_list = []
    for p_item in planned_items:
        p_item_id = str(p_item['id'])
        score = item_scores.get(p_item_id, 0.0)
        # Use math.exp to handle negative scores and create a weighted, randomized key
        weight = math.exp(score / 3.0)  # Temperature of 3.0 balances score vs randomness
        random_sort_key = random.random() * weight
        weighted_planned_list.append((p_item, random_sort_key))

    weighted_planned_list.sort(key=lambda x: x[1], reverse=True)
    return [item for item, key in weighted_planned_list]

def get_continue_collection_suggestions(watchlist, cache):
    """
    Generates suggestions for the next movie to watch in an in-progress collection.
    The suggestions are scored and sorted based on:
    1. (Primary) The ratings and recency of other movies watched in the same collection.
    2. (Secondary) The similarity of the suggested movie to the user's overall watch history.
    """
    today = datetime.now()
    w_m_ids = {m['id'] for m in watchlist['watched']['movies']}

    # --- 1. Pre-calculate influence of ALL watched items (for the secondary score) ---
    watched_item_influences = []
    # Process all rated movies
    for watch in watchlist['watched']['movies']:
        rating = watch.get('rating')
        if rating is None: continue
        rating_influence = rating - 3.0
        time_decay = 1.0
        date_str = watch.get('watched_on')
        if date_str:
            try:
                days_since = (today - datetime.strptime(date_str, '%Y-%m-%d')).days
                time_decay = 0.997 ** max(0, days_since)
            except (ValueError, TypeError):
                pass
        base_influence = rating_influence * time_decay
        w_item_id = str(watch['id'])
        w_item_details = cache.get('movies', {}).get(w_item_id)
        if w_item_details:
            watched_item_influences.append({'influence': base_influence, 'details': w_item_details})
    # Process all rated series
    for sid, watch_throughs in watchlist['watched']['series'].items():
        for watch in watch_throughs:
            rating = watch.get('rating')
            if rating is None: continue
            rating_influence = rating - 3.0
            time_decay = 1.0
            last_watched_date = max((e.get('watched_on') for e in watch.get('watched_episodes', {}).values() if e.get('watched_on')), default=None)
            if last_watched_date:
                try:
                    days_since = (today - datetime.strptime(last_watched_date, '%Y-%m-%d')).days
                    time_decay = 0.997 ** max(0, days_since)
                except (ValueError, TypeError):
                    pass
            base_influence = rating_influence * time_decay
            w_item_details = cache.get('series', {}).get(sid)
            if w_item_details:
                watched_item_influences.append({'influence': base_influence, 'details': w_item_details})

    # --- 2. Find collections in progress ---
    collections_in_progress = defaultdict(list)
    for movie_watch in watchlist['watched']['movies']:
        movie_id_str = str(movie_watch.get('id'))
        movie_cache_entry = cache.get('movies', {}).get(movie_id_str)
        if movie_cache_entry and movie_cache_entry.get('collection'):
            collection_id = movie_cache_entry['collection'].get('id')
            if collection_id:
                collections_in_progress[collection_id].append(movie_watch)
    if not collections_in_progress:
        return []
    suggestions_with_scores = []

    # --- 3. For each collection, find the next movie and calculate its score ---
    for collection_id, watched_movies_in_collection in collections_in_progress.items():
        collection_details = tmdb_api.get_collection_details(collection_id)
        if not collection_details or not collection_details.get('parts'): continue
        all_parts = collection_details.get('parts', [])
        next_movie_to_watch = next((part for part in all_parts if part.get('id') not in w_m_ids), None)

        if next_movie_to_watch:
            # --- Calculate Primary Score (from within the collection) ---
            primary_score = 0.0
            for watched_movie in watched_movies_in_collection:
                rating = watched_movie.get('rating')
                watched_on = watched_movie.get('watched_on')
                rating_score = (rating - 3.0) if rating is not None else 0.2
                time_decay = 1.0
                if watched_on:
                    try:
                        days_since = (today - datetime.strptime(watched_on, '%Y-%m-%d')).days
                        time_decay = 0.997 ** max(0, days_since)
                    except (ValueError, TypeError):
                        pass
                primary_score += rating_score * time_decay

            # --- Calculate Secondary Score (similarity to all watched items) ---
            secondary_score = 0.0
            suggestion_details = cache.get('movies', {}).get(str(next_movie_to_watch['id']))
            if suggestion_details:
                p_genres = set(g.strip() for g in suggestion_details.get('genre', '').split(',') if g.strip())
                p_actors = set(a.strip() for a in suggestion_details.get('actors', '').split(',')[:3] if a.strip())
                p_director = suggestion_details.get('director') or suggestion_details.get('creator', '')
                for w_influence in watched_item_influences:
                    w_details = w_influence['details']
                    w_genres = set(g.strip() for g in w_details.get('genre', '').split(',') if g.strip())
                    w_actors = set(a.strip() for a in w_details.get('actors', '').split(',')[:3] if a.strip())
                    w_director = w_details.get('director') or w_details.get('creator', '')
                    genre_overlap = len(p_genres.intersection(w_genres))
                    actor_overlap = len(p_actors.intersection(w_actors))
                    director_match = 3.0 if p_director and p_director == w_director else 0
                    similarity = (genre_overlap * 1.0) + (actor_overlap * 0.5) + director_match
                    if similarity > 0:
                        secondary_score += w_influence['influence'] * similarity

            # --- Combine Scores ---
            primary_weight = 5.0
            final_score = (primary_score * primary_weight) + secondary_score
            suggestions_with_scores.append({'suggestion': next_movie_to_watch, 'score': final_score})

    # --- 4. Sort and finalize ---
    sorted_suggestions = sorted(suggestions_with_scores, key=lambda x: x['score'], reverse=True)
    return [item['suggestion'] for item in sorted_suggestions]