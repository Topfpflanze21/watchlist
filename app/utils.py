# /app/utils.py
from datetime import datetime
from collections import Counter, defaultdict
from flask import current_app
from . import data_manager
from . import tmdb_api
import random
import math
import requests
import calendar


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
    with app.app_context():
        print("Syncing metadata cache with watchlist...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
        fetched_count = 0

        all_item_ids = {'movie': {str(m['id']) for m in watchlist['watched']['movies'] + watchlist['planned']['movies']}, 'series': {str(s['id']) for s in watchlist['planned']['series']} | set(watchlist['watched']['series'].keys())}

        # --- FIX: Updated condition to also check for the 'collection' key ---
        for mid in all_item_ids['movie']:
            movie_entry = cache.get('movies', {}).get(mid)
            if not movie_entry or 'collection' not in movie_entry or 'watch_providers' not in movie_entry:
                if tmdb_api.get_movie_details(int(mid)):
                    fetched_count += 1

        for sid in all_item_ids['series']:
            series_entry = cache.get('series', {}).get(sid)
            if not series_entry or 'watch_providers' not in series_entry:
                if tmdb_api.get_series_details(int(sid)):
                    fetched_count += 1

        if fetched_count > 0:
            print(f"Sync complete. Fetched metadata for {fetched_count} new/updated item(s).")
        else:
            print("Cache is up to date.")

def generate_home_page_suggestions(watchlist, cache):
    """Generates all suggestion carousels for the home page."""
    # From your 'Plan to Watch'
    sorted_planned_movies = get_weighted_planned_suggestions('movie', watchlist, cache)
    sorted_planned_series = get_weighted_planned_suggestions('series', watchlist, cache)
    p_movie_suggs = [{**cache['movies'][str(i['id'])], 'type': 'movie'} for i in sorted_planned_movies[:26] if str(i['id']) in cache.get('movies', {})]
    p_series_suggs = [{**cache['series'][str(i['id'])], 'type': 'series'} for i in sorted_planned_series[:26] if str(i['id']) in cache.get('series', {})]

    # Continue Watching
    continue_collection_suggestions = get_continue_collection_suggestions(watchlist, cache)
    continue_series_suggestions = []
    watched_series = watchlist.get('watched', {}).get('series', {})
    for series_id, watch_throughs in watched_series.items():
        if series_id not in cache.get('series', {}): continue
        series_meta = cache['series'][series_id]
        total_episodes = series_meta.get('total_episode_count', 0)
        if watch_throughs:
            latest_watch = max(watch_throughs, key=lambda w: max((e.get('watched_on') or '0001-01-01' for e in w.get('watched_episodes', {}).values()), default='0001-01-01'))
            watched_count = len(latest_watch.get('watched_episodes', {}))
            if 0 < watched_count < total_episodes:
                last_watched_date = max((e.get('watched_on') or '0001-01-01' for e in latest_watch.get('watched_episodes', {}).values()), default='0001-01-01')
                continue_series_suggestions.append({'type': 'series', **series_meta, 'last_watched_on': last_watched_date})
    continue_series_suggestions.sort(key=lambda x: x['last_watched_on'], reverse=True)

    # Smart Suggestions
    smart_movie_suggestions = get_smart_suggestions('movies')[:26]
    smart_series_suggestions = get_smart_suggestions('series')[:26]

    # Trending
    trending_movies, trending_series = [], []
    api_key = current_app.config['TMDB_API_KEY']
    if api_key and api_key != "YOUR_API_KEY_HERE":
        try:
            image_url = current_app.config['TMDB_IMAGE_URL']
            res_movies = requests.get(f"{current_app.config['TMDB_BASE_URL']}/trending/movie/week?api_key={api_key}")
            res_movies.raise_for_status()
            for item in res_movies.json().get('results', []):
                if item.get('poster_path'):
                    trending_movies.append({"id": item.get('id'), "title": item.get('title'), "year": item.get('release_date', '')[:4], "poster_url": f"{image_url}{item.get('poster_path')}", "type": "movie"})
            res_series = requests.get(f"{current_app.config['TMDB_BASE_URL']}/trending/tv/week?api_key={api_key}")
            res_series.raise_for_status()
            for item in res_series.json().get('results', []):
                if item.get('poster_path'):
                    trending_series.append({"id": item.get('id'), "title": item.get('name'), "year": item.get('first_air_date', '')[:4], "poster_url": f"{image_url}{item.get('poster_path')}", "type": "series"})
        except requests.RequestException as e:
            print(f"API Error fetching trending items: {e}")

    return {
        'planned_movie_suggestions': p_movie_suggs,
        'planned_series_suggestions': p_series_suggs,
        'continue_collection_suggestions': continue_collection_suggestions[:26],
        'continue_series_suggestions': continue_series_suggestions[:26],
        'smart_movie_suggestions': smart_movie_suggestions,
        'smart_series_suggestions': smart_series_suggestions,
        'trending_movies': trending_movies[:26],
        'trending_series': trending_series[:26]
    }

def generate_stats_page_data(watchlist, cache):
    """Generates all data required for the statistics page."""
    stats = defaultdict(lambda: 0)
    stats['time_breakdown'] = {'movies': 0, 'series': 0}
    stats['ratings_dist'] = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}

    # --- Watched Movies ---
    movie_watches = watchlist['watched']['movies']
    stats['total_movie_watches'] = len(movie_watches)
    movie_watch_time = 0
    all_watch_dates = []

    genre_counter = Counter()
    actor_counter = Counter()
    director_counter = Counter()
    decade_counter = Counter()
    watched_providers_counter = Counter()

    today = datetime.now()

    for watch in movie_watches:
        movie_id = str(watch.get('id'))
        if movie_id in cache.get('movies', {}):
            movie_data = cache['movies'][movie_id]
            movie_watch_time += movie_data.get('runtime') or 0
            if watch.get('watched_on'):
                try:
                    all_watch_dates.append(datetime.strptime(watch['watched_on'], '%Y-%m-%d'))
                except (ValueError, TypeError):
                    pass


            rating = watch.get('rating')
            if rating:
                stats['ratings_dist'][rating] += 1
                influence = rating - 3.0

                if movie_data.get('genre'):
                    for genre in movie_data.get('genre').split(','):
                        genre_counter[genre.strip()] += influence
                if movie_data.get('actors'):
                     for actor in movie_data.get('actors').split(',')[:5]: # Top 5 actors
                        actor_counter[actor.strip()] += influence
                if movie_data.get('director'):
                    director_counter[movie_data.get('director')] += influence
                if movie_data.get('year'):
                    try:
                        decade = f"{(int(movie_data['year']) // 10) * 10}s"
                        decade_counter[decade] += influence
                    except (ValueError, TypeError):
                        pass

                if movie_data.get('watch_providers', {}).get('flatrate'):
                    for provider in movie_data['watch_providers']['flatrate']:
                        time_decay = 1.0
                        if watch.get('watched_on'):
                            try:
                                days_since_watched = max(0, (today - datetime.strptime(watch['watched_on'], '%Y-%m-%d')).days)
                                time_decay = 0.997 ** days_since_watched
                            except (ValueError, TypeError): pass
                        watched_providers_counter[provider['name']] += influence * time_decay


    stats['movie_watch_time_minutes'] = movie_watch_time

    # --- Watched Series ---
    total_episodes = 0
    series_watch_time = 0
    for series_id, watch_throughs in watchlist['watched']['series'].items():
        if series_id in cache.get('series', {}):
            series_data = cache['series'][series_id]
            for watch in watch_throughs:
                total_episodes += len(watch.get('watched_episodes', {}))

                # Calculate series runtime
                for ep_id, ep_data in watch.get('watched_episodes', {}).items():
                    if ep_data.get('watched_on'):
                        try:
                            all_watch_dates.append(datetime.strptime(ep_data['watched_on'], '%Y-%m-%d'))
                        except (ValueError, TypeError):
                            pass

                    # Find episode runtime
                    try:
                        season_num_str = ep_id[1:3]
                        ep_num_str = ep_id[4:6]
                        season_num = int(season_num_str)

                        for season in series_data.get('seasons', []):
                            if season.get('season_number') == season_num:
                                for episode in season.get('episodes', []):
                                    if episode.get('id') == ep_id:
                                        series_watch_time += episode.get('runtime') or 0
                                        break
                                break
                    except (ValueError, TypeError, IndexError):
                        continue


                rating = watch.get('rating')
                if rating:
                    stats['ratings_dist'][rating] += 1
                    influence = rating - 3.0

                    if series_data.get('genre'):
                        for genre in series_data.get('genre').split(','):
                            genre_counter[genre.strip()] += influence
                    if series_data.get('actors'):
                        for actor in series_data.get('actors').split(',')[:5]:
                            actor_counter[actor.strip()] += influence
                    if series_data.get('creator'):
                         for creator in series_data.get('creator').split(','):
                            director_counter[creator.strip()] += influence
                    if series_data.get('year'):
                        try:
                            decade = f"{(int(series_data['year']) // 10) * 10}s"
                            decade_counter[decade] += influence
                        except (ValueError, TypeError):
                            pass

                    if series_data.get('watch_providers', {}).get('flatrate'):
                        for provider in series_data['watch_providers']['flatrate']:
                            time_decay = 1.0
                            last_watched_date = max((e.get('watched_on') for e in watch.get('watched_episodes', {}).values() if e.get('watched_on')), default=None)
                            if last_watched_date:
                                try:
                                    days_since_watched = max(0, (today - datetime.strptime(last_watched_date, '%Y-%m-%d')).days)
                                    time_decay = 0.997 ** days_since_watched
                                except (ValueError, TypeError): pass
                            watched_providers_counter[provider['name']] += influence * time_decay

    stats['total_episodes'] = total_episodes
    stats['series_watch_time_minutes'] = series_watch_time
    stats['total_watch_time_minutes'] = movie_watch_time + series_watch_time

    # --- Time Breakdown ---
    if stats['total_watch_time_minutes'] > 0:
        stats['time_breakdown']['movies'] = round((movie_watch_time / stats['total_watch_time_minutes']) * 100)
        stats['time_breakdown']['series'] = round((series_watch_time / stats['total_watch_time_minutes']) * 100)

    # --- Viewing Habits ---
    daily_activity_counter = Counter(date.strftime('%A') for date in all_watch_dates)
    days_of_week = list(calendar.day_name)
    stats['daily_activity'] = [(day, {'count': daily_activity_counter.get(day, 0)}) for day in days_of_week]
    stats['max_daily_count'] = max(daily_activity_counter.values()) if daily_activity_counter else 0

    monthly_activity_counter = Counter(date.strftime('%Y-%B') for date in all_watch_dates)
    if monthly_activity_counter:
        most_active_month_str = monthly_activity_counter.most_common(1)[0][0]
        year, month_name = most_active_month_str.split('-')
        stats['most_active_month'] = {'month': month_name, 'count': monthly_activity_counter[most_active_month_str]}
    else:
        stats['most_active_month'] = {'month': 'N/A', 'count': 0}

    # --- Content Analysis ---
    stats['favorite_genres'] = [item for item in genre_counter.most_common(10) if item[1] > 0]
    stats['favorite_actors'] = [item for item in actor_counter.most_common(10) if item[1] > 0]
    stats['favorite_directors'] = [item for item in director_counter.most_common(10) if item[1] > 0]
    stats['favorite_decades'] = [item for item in decade_counter.most_common(10) if item[1] > 0]
    stats['max_rating_count'] = max(stats['ratings_dist'].values()) if any(stats['ratings_dist'].values()) else 0

    # --- Provider Insights ---
    # Planned providers
    planned_providers_counter = Counter()
    all_providers_data = tmdb_api.get_available_providers()
    provider_map = {p['name']: p for p in all_providers_data}

    planned_items = watchlist['planned']['movies'] + watchlist['planned']['series']
    for item in planned_items:
        item_type = 'movies' if 'runtime' in cache.get('movies', {}).get(str(item['id']), {}) else 'series'
        item_id = str(item['id'])
        if item_id in cache.get(item_type, {}):
            item_data = cache[item_type][item_id]
            if item_data.get('watch_providers', {}).get('flatrate'):
                for provider in item_data['watch_providers']['flatrate']:
                    planned_providers_counter[provider['name']] += 1

    stats['planned_providers'] = [{'name': name, 'count': count, 'logo_url': provider_map.get(name, {}).get('logo_url')} for name, count in planned_providers_counter.most_common(5)]

    # Watched providers
    stats['watched_providers'] = [{'name': name, 'score': score, 'logo_url': provider_map.get(name, {}).get('logo_url')} for name, score in watched_providers_counter.most_common(5) if score > 0]


    return stats

def generate_collections_page_suggestions(watchlist, cache):
    """Generates lists of in-progress and completed collections."""
    collections_dict = {}
    watched_movies = watchlist.get('watched', {}).get('movies', [])
    w_m_ids = {m['id'] for m in watched_movies}

    for movie_watch in watched_movies:
        movie_id_str = str(movie_watch.get('id'))
        if movie_id_str in cache.get('movies', {}):
            collection_info = cache['movies'][movie_id_str].get('collection')
            if collection_info and collection_info.get('id'):
                collection_id = collection_info['id']
                if collection_id not in collections_dict:
                    full_details = tmdb_api.get_collection_details(collection_id)
                    if full_details and len(full_details.get('parts', [])) > 1:
                        parts = full_details.get('parts', [])
                        watched_count = sum(1 for p in parts if p.get('id') in w_m_ids)
                        # --- FIX: Use data from the full details, not the stub ---
                        collections_dict[collection_id] = {
                            'id': collection_id,
                            'name': full_details.get('name'),
                            'poster_url': full_details.get('poster_url'),
                            'watched_count': watched_count,
                            'total_count': len(parts)
                        }

    all_collections = sorted(collections_dict.values(), key=lambda x: x.get('name', ''))
    completed_collections = [c for c in all_collections if c['watched_count'] == c['total_count']]
    in_progress_collections = [c for c in all_collections if c['watched_count'] != c['total_count']]
    return {'completed': completed_collections, 'in_progress': in_progress_collections}

def get_smart_suggestions(item_type):
    """Generates personalized suggestions based on watched items."""
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    today = datetime.now()
    singular_type = 'movie' if item_type == 'movies' else 'series'

    user_item_ids = {item['id'] for item in watchlist['planned'][item_type]}
    if item_type == 'movies':
        user_item_ids.update(item['id'] for item in watchlist['watched']['movies'])
        source_items = [item for item in watchlist['watched']['movies'] if item.get('rating') is not None]
    else:
        user_item_ids.update(int(id) for id in watchlist['watched']['series'])
        source_items = []
        for sid, watch_throughs in watchlist['watched']['series'].items():
            for watch in watch_throughs:
                if watch.get('rating') is not None:
                    source_items.append({'id': int(sid), 'rating': watch.get('rating'), 'watched_episodes': watch.get('watched_episodes', {})})

    scores, recommendation_data = {}, {}
    for item in source_items:
        id_str = str(item['id'])
        if id_str not in cache[item_type] or 'recommendations' not in cache[item_type][id_str]:
            continue
        rating = item.get('rating')
        base_influence = rating - 3.0
        date_str = item.get('watched_on') if item_type == 'movies' else (max((e['watched_on'] for e in item['watched_episodes'].values() if e.get('watched_on')), default=None) if item.get('watched_episodes') else None)
        time_decay = 1.0
        if date_str:
            try:
                days_since_watched = max(0, (today - datetime.strptime(date_str, '%Y-%m-%d')).days)
                time_decay = 0.997 ** days_since_watched
            except (ValueError, TypeError): pass
        influence_score = base_influence * time_decay
        for rec in cache[item_type][id_str].get('recommendations', []):
            rec_id = rec.get('id')
            if rec_id and rec_id not in user_item_ids:
                scores[rec_id] = scores.get(rec_id, 0) + influence_score
                if rec_id not in recommendation_data:
                    recommendation_data[rec_id] = {**rec, 'type': singular_type}

    weighted_suggestions = []
    temperature = 5.0
    for rec_id, score in scores.items():
        try:
            weight = math.exp(score / temperature)
        except OverflowError:
            weight = float('inf')
        weighted_suggestions.append((rec_id, random.random() * weight))

    weighted_suggestions.sort(key=lambda x: x[1], reverse=True)
    return [recommendation_data[id] for id, key in weighted_suggestions if id in recommendation_data]

def get_weighted_planned_suggestions(item_type, watchlist, cache):
    internal_type = 'movies' if item_type == 'movie' else 'series'
    planned_items = watchlist['planned'][internal_type]
    watched_items_for_scoring = []
    if internal_type == 'movies':
        watches_by_id = defaultdict(list)
        for watch in watchlist['watched']['movies']: watches_by_id[watch['id']].append(watch)
        for item_id, watches in watches_by_id.items():
            if watches: watched_items_for_scoring.append(max(watches, key=lambda x: x.get('watched_on') or '0001-01-01'))
    else:
        for sid, watch_throughs in watchlist['watched']['series'].items():
            if sid in cache['series'] and watch_throughs:
                latest_watch = max(watch_throughs, key=lambda w: max((e.get('watched_on') or '0001-01-01' for e in w.get('watched_episodes', {}).values()), default='0001-01-01'))
                last_watched_date = max((e.get('watched_on') for e in latest_watch.get('watched_episodes', {}).values() if e.get('watched_on')), default=None)
                watched_items_for_scoring.append({**latest_watch, 'id': int(sid), 'watched_on': last_watched_date})
    if not any(w.get('rating') for w in watched_items_for_scoring):
        random.shuffle(planned_items)
        return planned_items
    today, item_scores, watched_item_influences = datetime.now(), {}, []
    for w_item in watched_items_for_scoring:
        rating = w_item.get('rating')
        if rating is None: continue
        rating_influence, time_decay = rating - 3.0, 1.0
        if date_str := w_item.get('watched_on'):
            try: time_decay = 0.997 ** max(0, (today - datetime.strptime(date_str, '%Y-%m-%d')).days)
            except (ValueError, TypeError): pass
        base_influence = rating_influence * time_decay
        w_item_id, w_item_details = str(w_item['id']), cache.get(internal_type, {}).get(str(w_item['id']))
        if w_item_details: watched_item_influences.append({'influence': base_influence, 'details': w_item_details})
    for p_item in planned_items:
        p_item_id, p_item_details = str(p_item['id']), cache.get(internal_type, {}).get(str(p_item['id']))
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
            similarity = (len(p_genres.intersection(w_genres)) * 1.0) + (len(p_actors.intersection(w_actors)) * 0.5) + (3.0 if p_director and p_director == w_director else 0)
            if similarity > 0: current_score += w_influence['influence'] * similarity
        item_scores[p_item_id] = current_score
    weighted_planned_list = []
    for p_item in planned_items:
        p_item_id = str(p_item['id'])
        score = item_scores.get(p_item_id, 0.0)
        weight = math.exp(score / 3.0)
        weighted_planned_list.append((p_item, random.random() * weight))
    weighted_planned_list.sort(key=lambda x: x[1], reverse=True)
    return [item for item, key in weighted_planned_list]

def get_continue_collection_suggestions(watchlist, cache):
    today = datetime.now()
    w_m_ids, watched_item_influences = {m['id'] for m in watchlist['watched']['movies']}, []
    for watch in watchlist['watched']['movies']:
        rating = watch.get('rating')
        if rating is None: continue
        rating_influence, time_decay = rating - 3.0, 1.0
        if date_str := watch.get('watched_on'):
            try: time_decay = 0.997 ** max(0, (today - datetime.strptime(date_str, '%Y-%m-%d')).days)
            except (ValueError, TypeError): pass
        base_influence = rating_influence * time_decay
        if w_item_details := cache.get('movies', {}).get(str(watch['id'])): watched_item_influences.append({'influence': base_influence, 'details': w_item_details})
    for sid, watch_throughs in watchlist['watched']['series'].items():
        for watch in watch_throughs:
            rating = watch.get('rating')
            if rating is None: continue
            rating_influence, time_decay = rating - 3.0, 1.0
            if last_watched_date := max((e.get('watched_on') for e in watch.get('watched_episodes', {}).values() if e.get('watched_on')), default=None):
                try: time_decay = 0.997 ** max(0, (today - datetime.strptime(last_watched_date, '%Y-%m-%d')).days)
                except (ValueError, TypeError): pass
            base_influence = rating_influence * time_decay
            if w_item_details := cache.get('series', {}).get(sid): watched_item_influences.append({'influence': base_influence, 'details': w_item_details})
    collections_in_progress, suggestions_with_scores = defaultdict(list), []
    for movie_watch in watchlist['watched']['movies']:
        if movie_cache_entry := cache.get('movies', {}).get(str(movie_watch.get('id'))):
            if collection_info := movie_cache_entry.get('collection'):
                if collection_id := collection_info.get('id'):
                    collections_in_progress[collection_id].append(movie_watch)
    if not collections_in_progress: return []
    for collection_id, watched_movies_in_collection in collections_in_progress.items():
        collection_details = tmdb_api.get_collection_details(collection_id)
        if not (collection_details and collection_details.get('parts')): continue
        next_movie_to_watch = next((part for part in collection_details.get('parts', []) if part.get('id') not in w_m_ids), None)
        if next_movie_to_watch:
            primary_score = 0.0
            for watched_movie in watched_movies_in_collection:
                rating_score = (watched_movie.get('rating') - 3.0) if watched_movie.get('rating') is not None else 0.2
                time_decay = 1.0
                if watched_on := watched_movie.get('watched_on'):
                    try: time_decay = 0.997 ** max(0, (today - datetime.strptime(watched_on, '%Y-%m-%d')).days)
                    except (ValueError, TypeError): pass
                primary_score += rating_score * time_decay
            secondary_score = 0.0
            if suggestion_details := cache.get('movies', {}).get(str(next_movie_to_watch['id'])):
                p_genres = set(g.strip() for g in suggestion_details.get('genre', '').split(',') if g.strip())
                p_actors = set(a.strip() for a in suggestion_details.get('actors', '').split(',')[:3] if a.strip())
                p_director = suggestion_details.get('director') or suggestion_details.get('creator', '')
                for w_influence in watched_item_influences:
                    w_details = w_influence['details']
                    w_genres = set(g.strip() for g in w_details.get('genre', '').split(',') if g.strip())
                    w_actors = set(a.strip() for a in w_details.get('actors', '').split(',')[:3] if a.strip())
                    w_director = w_details.get('director') or w_details.get('creator', '')
                    similarity = (len(p_genres.intersection(w_genres)) * 1.0) + (len(p_actors.intersection(w_actors)) * 0.5) + (3.0 if p_director and p_director == w_director else 0)
                    if similarity > 0: secondary_score += w_influence['influence'] * similarity
            final_score = (primary_score * 5.0) + secondary_score
            suggestions_with_scores.append({'suggestion': next_movie_to_watch, 'score': final_score})
    sorted_suggestions = sorted(suggestions_with_scores, key=lambda x: x['score'], reverse=True)
    return [item['suggestion'] for item in sorted_suggestions]