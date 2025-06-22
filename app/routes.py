# /app/routes.py
import uuid
import random
import requests
import calendar
from datetime import datetime
from collections import Counter, defaultdict
from flask import (Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, Response)
from . import data_manager, tmdb_api, utils
from flask_login import login_user, logout_user, current_user, login_required
from .models import User
import json

bp = Blueprint('main', __name__)

# --- Authentication Routes ---
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') is not None
        user_data = data_manager.find_user_by_username(username)
        user_obj = User(user_data['id'], user_data['username'], user_data['password_hash']) if user_data else None

        if user_obj is None or not user_obj.check_password(password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('main.login'))

        login_user(user_obj, remember=remember)
        return redirect(url_for('main.index'))
    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if data_manager.find_user_by_username(username):
            flash('Username already exists. Please choose another.', 'error')
            return redirect(url_for('main.register'))

        users_db = data_manager.get_users_db()
        new_user = User(id=users_db['next_id'], username=username, password_hash='')
        new_user.set_password(password)

        users_db['users'].append({'id': new_user.id, 'username': new_user.username, 'password_hash': new_user.password_hash})
        users_db['next_id'] += 1
        data_manager.save_users_db(users_db)

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html')


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/refresh_suggestions')
@login_required
def refresh_suggestions():
    """Clears the suggestions cache and redirects to the homepage."""
    data_manager.clear_suggestions_cache()
    return redirect(url_for('main.index'))


@bp.route('/')
def index():
    suggestions_cache = data_manager.load_suggestions_cache()

    if 'home_page' in suggestions_cache:
        cached_data = suggestions_cache['home_page']
        p_movie_suggs = cached_data.get('planned_movie_suggestions', [])
        p_series_suggs = cached_data.get('planned_series_suggestions', [])
        continue_collection_suggestions = cached_data.get('continue_collection_suggestions', [])
        continue_series_suggestions = cached_data.get('continue_series_suggestions', [])
        smart_movie_suggestions = cached_data.get('smart_movie_suggestions', [])
        smart_series_suggestions = cached_data.get('smart_series_suggestions', [])
        trending_movies = cached_data.get('trending_movies', [])
        trending_series = cached_data.get('trending_series', [])
    else:
        print("Generating and caching new homepage suggestions...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
        sorted_planned_movies = utils.get_weighted_planned_suggestions('movie', watchlist, cache)
        sorted_planned_series = utils.get_weighted_planned_suggestions('series', watchlist, cache)
        p_movie_suggs = [{**cache['movies'][str(i['id'])], 'type': 'movie'} for i in sorted_planned_movies[:26] if str(i['id']) in cache['movies']]
        p_series_suggs = [{**cache['series'][str(i['id'])], 'type': 'series'} for i in sorted_planned_series[:26] if str(i['id']) in cache['series']]

        continue_collection_suggestions = utils.get_continue_collection_suggestions(watchlist, cache)
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

        smart_movie_suggestions = utils.get_smart_suggestions('movies')[:26]
        smart_series_suggestions = utils.get_smart_suggestions('series')[:26]

        trending_movies, trending_series = [], []
        api_key = current_app.config['TMDB_API_KEY']
        if api_key and api_key != "YOUR_API_KEY_HERE":
            try:
                image_url = current_app.config['TMDB_IMAGE_URL']
                # Fetch Trending Movies
                res_movies = requests.get(f"{current_app.config['TMDB_BASE_URL']}/trending/movie/week?api_key={api_key}")
                res_movies.raise_for_status()
                for item in res_movies.json().get('results', []):
                    if item.get('poster_path'):
                        trending_movies.append({"id": item.get('id'), "title": item.get('title'), "year": item.get('release_date', '')[:4], "poster_url": f"{image_url}{item.get('poster_path')}", "type": "movie"})
                # Fetch Trending Series
                res_series = requests.get(f"{current_app.config['TMDB_BASE_URL']}/trending/tv/week?api_key={api_key}")
                res_series.raise_for_status()
                for item in res_series.json().get('results', []):
                    if item.get('poster_path'):
                        trending_series.append({"id": item.get('id'), "title": item.get('name'), "year": item.get('first_air_date', '')[:4], "poster_url": f"{image_url}{item.get('poster_path')}", "type": "series"})
            except requests.RequestException as e:
                print(f"API Error fetching trending items: {e}")

        suggestions_cache['home_page'] = {'planned_movie_suggestions': p_movie_suggs, 'planned_series_suggestions': p_series_suggs, 'continue_collection_suggestions': continue_collection_suggestions[:26],
            'continue_series_suggestions': continue_series_suggestions[:26], 'smart_movie_suggestions': smart_movie_suggestions, 'smart_series_suggestions': smart_series_suggestions, 'trending_movies': trending_movies[:26], 'trending_series': trending_series[:26]}
        data_manager.save_suggestions_cache(suggestions_cache)

    return render_template('index.html', planned_movie_suggestions=p_movie_suggs, planned_series_suggestions=p_series_suggs, continue_collection_suggestions=continue_collection_suggestions, continue_series_suggestions=continue_series_suggestions,
                           smart_movie_suggestions=smart_movie_suggestions, smart_series_suggestions=smart_series_suggestions, trending_movies=trending_movies, trending_series=trending_series)


@bp.route('/movies')
def movies():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    watches = {}
    for watch in watchlist['watched']['movies']:
        watches.setdefault(watch['id'], []).append(watch)

    watched_items = sorted([({**cache['movies'][str(id)], **max(w, key=lambda x: x.get('watched_on') or '0001-01-01'), 'watch_count': len(w), 'type': 'movie'}) for id, w in watches.items() if str(id) in cache['movies']],
                           key=lambda x: x.get('watched_on') or '0001-01-01', reverse=True)

    planned_items = [{**cache['movies'][str(m['id'])], **m, 'type': 'movie'} for m in watchlist['planned']['movies'] if str(m['id']) in cache['movies']]
    return render_template('items_list.html', item_type='movies', watched_items=watched_items, planned_items=planned_items)


@bp.route('/series')
def series():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    watched_items = []
    for sid, watch_throughs in watchlist['watched']['series'].items():
        if sid in cache['series'] and watch_throughs:
            details = cache['series'][sid]
            # Get the most recently active watch-through for summary display
            latest_watch = max(watch_throughs, key=lambda w: max((e.get('watched_on') or '0001-01-01' for e in w.get('watched_episodes', {}).values()), default='0001-01-01'))

            w_ep_c = len(latest_watch.get('watched_episodes', {}))
            t_ep_c = details.get('total_episode_count', 0)
            last_on = max((e['watched_on'] for e in latest_watch.get('watched_episodes', {}).values() if e.get('watched_on')), default='N/A')
            status = 'Completed' if t_ep_c > 0 and w_ep_c == t_ep_c else 'In Progress'

            watched_items.append({**details, **latest_watch, 'type': 'series', 'watch_count': len(watch_throughs), 'watched_episode_count': w_ep_c, 'total_episode_count': t_ep_c, 'status': status, 'last_watched_on': last_on})

    watched_items.sort(key=lambda x: x.get('last_watched_on') or '0001-01-01', reverse=True)
    planned_items = [{**cache['series'][str(s['id'])], **s, 'type': 'series'} for s in watchlist['planned']['series'] if str(s['id']) in cache['series']]
    return render_template('items_list.html', item_type='series', watched_items=watched_items, planned_items=planned_items)


@bp.route('/item/<item_type>/<int:item_id>')
def item_detail(item_type, item_id):
    internal_type = 'movies' if item_type == 'movie' else 'series'
    details_func = tmdb_api.get_movie_details if item_type == 'movie' else tmdb_api.get_series_details
    details = details_func(item_id)
    if not details:
        flash(f"Could not retrieve details for this {item_type}.", "error")
        return redirect(url_for(f'main.{internal_type}'))

    if item_type == 'movie' and details.get('collection'):
        collection_details = tmdb_api.get_collection_details(details['collection']['id'])
        if not collection_details or len(collection_details.get('parts', [])) <= 1:
            details['collection'] = None

    watchlist = data_manager.load_watchlist()
    today = datetime.now().strftime('%Y-%m-%d')
    item_to_show = {**details, 'type': item_type}
    origin = request.referrer or url_for(f'main.{internal_type}')

    if item_type == 'movie':
        watch_history = sorted([i for i in watchlist['watched']['movies'] if i.get('id') == item_id], key=lambda x: x.get('watched_on') or '0001-01-01', reverse=True)
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['movies'])
        is_watched = bool(watch_history)
        return render_template('details.html', item=item_to_show, is_planned=is_planned, is_watched=is_watched, today=today, origin=origin, watch_history=watch_history, internal_type=internal_type)
    else:  # series
        watch_histories = watchlist['watched']['series'].get(str(item_id), [])
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['series'])
        is_watched = bool(watch_histories)

        return render_template('details.html', item=item_to_show, is_planned=is_planned, is_watched=is_watched, today=today, origin=origin, watch_histories=watch_histories, internal_type=internal_type)


@bp.route('/item/<item_type>/<int:item_id>/action', methods=['POST'])
@login_required
def item_detail_action(item_type, item_id):
    internal, watchlist = ('movies' if item_type == 'movie' else 'series'), data_manager.load_watchlist()
    should_clear_cache = False

    details_func = tmdb_api.get_movie_details if item_type == 'movie' else tmdb_api.get_series_details
    details = details_func(item_id)
    if not details:
        flash(f"Could not retrieve details for this {item_type}.", "error")
        return redirect(url_for(f'main.{internal}'))

    item_title_for_debug, item_year_for_debug = details.get('title', 'Unknown'), details.get('year', 'N/A')
    origin = request.args.get('origin', url_for(f'main.{internal}'))
    action = request.form.get('action')
    sid = str(item_id)

    if action == 'plan':
        if not any(i.get('id') == item_id for i in watchlist['planned'][internal]):
            watchlist['planned'][internal].append({"id": item_id, "title": item_title_for_debug, "year": item_year_for_debug})
            should_clear_cache = True
    elif action == 'remove_plan':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        should_clear_cache = True
    elif action == 'watch' and item_type == 'movie':
        new_watch = {"id": item_id, "title": item_title_for_debug, "year": item_year_for_debug, "watch_id": str(uuid.uuid4()), "watched_on": request.form.get('watched_on') or None, "rating": int(r) if (r := request.form.get('rating')) else None}
        watchlist['watched']['movies'].append(new_watch)
        watchlist['planned']['movies'] = [i for i in watchlist['planned']['movies'] if i.get('id') != item_id]
        should_clear_cache = True
    elif action == 'delete_all':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        if item_type == 'movie':
            watchlist['watched']['movies'] = [i for i in watchlist['watched']['movies'] if i.get('id') != item_id]
        else:
            watchlist['watched']['series'].pop(sid, None)
        should_clear_cache = True
    elif action == 'delete_watch_instance' and item_type == 'movie':
        watchlist['watched']['movies'] = [w for w in watchlist['watched']['movies'] if w.get('watch_id') != request.form.get('watch_id')]
        should_clear_cache = True
    elif action == 'edit_watch_instance' and item_type == 'movie':
        watch_id = request.form.get('watch_id')
        for watch in watchlist['watched']['movies']:
            if watch.get('watch_id') == watch_id:
                watch['watched_on'] = request.form.get('watched_on') or None
                watch['rating'] = int(r) if (r := request.form.get('rating')) and r.isdigit() else None
                should_clear_cache = True
                break
    elif item_type == 'series':
        series_watch_id = request.form.get('series_watch_id')
        if action == 'start_new_series_watch':
            new_watch = {"series_watch_id": str(uuid.uuid4()), "watched_episodes": {}, "title": item_title_for_debug, "year": item_year_for_debug}
            if sid not in watchlist['watched']['series']: watchlist['watched']['series'][sid] = []
            watchlist['watched']['series'][sid].append(new_watch)
            watchlist['planned']['series'] = [s for s in watchlist['planned']['series'] if s.get('id') != item_id]
            should_clear_cache = True
        elif action == 'delete_series_watch':
            if sid in watchlist['watched']['series'] and series_watch_id:
                watchlist['watched']['series'][sid] = [w for w in watchlist['watched']['series'][sid] if w.get('series_watch_id') != series_watch_id]
                if not watchlist['watched']['series'][sid]: del watchlist['watched']['series'][sid]
                should_clear_cache = True
        else:
            watch_through = next((w for w_list in watchlist['watched']['series'].get(sid, []) for w in [w_list] if w.get('series_watch_id') == series_watch_id), None)
            if watch_through:
                if action == 'toggle_episode':
                    eid = request.form['episode_id']
                    if eid in watch_through['watched_episodes']:
                        del watch_through['watched_episodes'][eid]
                    else:
                        date = request.form.get('watched_on') or None
                        watch_through['watched_episodes'][eid] = {"watched_on": date}
                    should_clear_cache = True
                elif action == 'rate_series':
                    if r_str := request.form.get('rating'):
                        watch_through['rating'] = int(r_str)
                        should_clear_cache = True
                elif action in ['watch_season', 'unwatch_season', 'watch_all_episodes', 'unwatch_all_episodes']:
                    details = tmdb_api.get_series_details(item_id)
                    if details and details.get('seasons'):
                        episode_ids = []
                        if action in ['watch_season', 'unwatch_season']:
                            season_num = int(request.form['season_number'])
                            episode_ids = [ep['id'] for s in details.get('seasons', []) if s.get('season_number') == season_num for ep in s.get('episodes', [])]
                        else:
                            episode_ids = [ep['id'] for s in details.get('seasons', []) for ep in s.get('episodes', [])]

                        if action in ['watch_season', 'watch_all_episodes']:
                            date = request.form.get('watched_on') or None
                            for eid in episode_ids:
                                if eid not in watch_through['watched_episodes']: watch_through['watched_episodes'][eid] = {"watched_on": date}
                        else:
                            for eid in episode_ids:
                                if eid in watch_through['watched_episodes']: del watch_through['watched_episodes'][eid]
                        should_clear_cache = True

    if should_clear_cache:
        data_manager.save_watchlist(watchlist)
        data_manager.clear_suggestions_cache()

    if action == 'delete_all':
        return redirect(origin)

    response_data = {'status': 'success', 'action': action}
    if action in ['plan', 'remove_plan']:
        is_planned_after_action = any(i.get('id') == item_id for i in watchlist['planned'][internal])
        response_data['is_planned'] = is_planned_after_action

    if action == 'toggle_episode':
        response_data['is_planned'] = any(i.get('id') == item_id for i in watchlist['planned']['series'])
        watch_through = next((w for w_list in watchlist['watched']['series'].get(sid, []) for w in [w_list] if w.get('series_watch_id') == request.form.get('series_watch_id')), None)
        if watch_through:
            response_data['is_episode_watched'] = request.form.get('episode_id') in watch_through.get('watched_episodes', {})
            response_data['watched_on'] = watch_through.get('watched_episodes', {}).get(request.form.get('episode_id'), {}).get('watched_on')
            response_data['watched_episode_count'] = len(watch_through.get('watched_episodes', {}))
            series_details = tmdb_api.get_series_details(item_id)
            response_data['total_episode_count'] = series_details.get('total_episode_count')
            response_data['series_watch_id'] = request.form.get('series_watch_id')

    if action == 'delete_watch_instance':
        response_data['watch_id'] = request.form.get('watch_id')

    if action == 'edit_watch_instance':
        response_data['watch_id'] = request.form.get('watch_id')

    return jsonify(response_data)


@bp.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    return redirect(url_for('main.show_search_results', q=query) if query else url_for('main.index'))


@bp.route('/search_results')
def show_search_results():
    query, results = request.args.get('q', ''), []
    api_key = current_app.config['TMDB_API_KEY']
    if api_key and api_key != "YOUR_API_KEY_HERE":
        try:
            res = requests.get(f"{current_app.config['TMDB_BASE_URL']}/search/multi?api_key={api_key}&query={query}")
            res.raise_for_status()
            image_url = current_app.config['TMDB_IMAGE_URL']
            for item in res.json().get('results', []):
                media_type = item.get('media_type')
                if media_type == 'movie' and item.get('poster_path'):
                    results.append({"id": item.get('id'), "title": item.get('title'), "year": item.get('release_date', '')[:4], "poster_url": f"{image_url}{item.get('poster_path')}", "type": "movie"})
                elif media_type == 'tv' and item.get('poster_path'):
                    results.append({"id": item.get('id'), "title": item.get('name'), "year": item.get('first_air_date', '')[:4], "poster_url": f"{image_url}{item.get('poster_path')}", "type": "series"})
        except requests.RequestException as e:
            flash(f"API Error: {e}", "error")

    watchlist = data_manager.load_watchlist()
    p_m_ids, w_m_ids = {i['id'] for i in watchlist['planned']['movies']}, {i['id'] for i in watchlist['watched']['movies']}
    p_s_ids, w_s_ids = {i['id'] for i in watchlist['planned']['series']}, {int(id) for id in watchlist['watched']['series']}
    for item in results:
        is_movie = item['type'] == 'movie'
        item_id = item['id']
        if (is_movie and item_id in w_m_ids) or (not is_movie and item_id in w_s_ids):
            item['status'] = 'watched'
        elif (is_movie and item_id in p_m_ids) or (not is_movie and item_id in p_s_ids):
            item['status'] = 'planned'
        else:
            item['status'] = None
    return render_template('search_results.html', query=query, results=results)


@bp.route('/collection/<int:collection_id>')
def collection_details(collection_id):
    collection = tmdb_api.get_collection_details(collection_id)
    if not collection:
        flash("Could not retrieve collection details.", "error")
        return redirect(url_for('main.index'))

    watchlist = data_manager.load_watchlist()
    p_m_ids = {i['id'] for i in watchlist['planned']['movies']}
    w_m_ids = {i['id'] for i in watchlist['watched']['movies']}

    for item in collection.get('parts', []):
        item_id = item['id']
        if item_id in w_m_ids:
            item['status'] = 'watched'
        elif item_id in p_m_ids:
            item['status'] = 'planned'
        else:
            item['status'] = None
    return render_template('collection_details.html', collection=collection)


@bp.route('/collections')
def collections():
    suggestions_cache = data_manager.load_suggestions_cache()
    if 'collections_page' in suggestions_cache:
        cached_data = suggestions_cache['collections_page']
        completed_collections = cached_data.get('completed', [])
        in_progress_collections = cached_data.get('in_progress', [])
    else:
        print("Generating and caching new collections page...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
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
                            poster_url = f"{current_app.config['TMDB_IMAGE_URL']}{p}" if (p := collection_info.get('poster_path')) else ""
                            collections_dict[collection_id] = {'id': collection_id, 'name': collection_info.get('name'), 'poster_url': poster_url, 'watched_count': watched_count, 'total_count': len(parts)}

        all_collections = sorted(collections_dict.values(), key=lambda x: x.get('name', ''))
        completed_collections = [c for c in all_collections if c['watched_count'] == c['total_count']]
        in_progress_collections = [c for c in all_collections if c['watched_count'] != c['total_count']]

        suggestions_cache['collections_page'] = {'completed': completed_collections, 'in_progress': in_progress_collections}
        data_manager.save_suggestions_cache(suggestions_cache)

    return render_template('collections_list.html', completed_collections=completed_collections, in_progress_collections=in_progress_collections)


@bp.route('/stats')
@login_required
def stats():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    w_movies = watchlist['watched']['movies']
    w_series_dict = watchlist['watched']['series']
    today = datetime.now()

    # --- Scoring Dictionaries & Data Aggregation ---
    genre_scores, actor_scores, director_creator_scores, decade_scores = [defaultdict(float) for _ in range(4)]
    all_ratings = []
    daily_activity, monthly_activity = defaultdict(lambda: {'count': 0}), defaultdict(int)
    movie_watch_time_minutes, series_watch_time_minutes, total_episodes_watched = 0, 0, 0
    planned_provider_counts, watched_provider_scores = defaultdict(int), defaultdict(float)
    provider_meta = {}

    def calculate_score(rating, date_str):
        rating_score = (rating - 3) if rating is not None else 0
        time_decay = 1.0
        if date_str:
            try:
                days_since = (today - datetime.strptime(date_str, '%Y-%m-%d')).days
                time_decay = 0.997 ** max(0, days_since)
            except (ValueError, TypeError):
                pass
        return rating_score * time_decay

    # --- Process Movies ---
    for movie_watch in w_movies:
        movie_id_str = str(movie_watch['id'])
        if movie_id_str not in cache['movies']: continue
        meta = cache['movies'][movie_id_str]
        watched_on = movie_watch.get('watched_on')
        score = calculate_score(movie_watch.get('rating'), watched_on)

        if movie_watch.get('rating') is not None: all_ratings.append(movie_watch['rating'])
        for g in meta.get('genre', '').split(','):
            if g.strip(): genre_scores[g.strip()] += score
        for a in meta.get('actors', '').split(','):
            if a.strip(): actor_scores[a.strip()] += score
        if meta.get('director'): director_creator_scores[meta['director']] += score
        if meta.get('year'): decade_scores[f"{meta['year'][:3]}0s"] += score
        movie_watch_time_minutes += meta.get('runtime') or 0
        for p in meta.get('watch_providers', {}).get('flatrate', []):
            if p.get('name'):
                watched_provider_scores[p['name']] += score
                provider_meta.setdefault(p['name'], {'logo_url': p.get('logo_url')})

        if watched_on:
            try:
                watch_date = datetime.strptime(watched_on, '%Y-%m-%d')
                daily_activity[calendar.day_name[watch_date.weekday()]]['count'] += 1
                monthly_activity[watch_date.strftime('%Y-%m')] += 1
            except (ValueError, KeyError, TypeError):
                continue

    # --- Process Series ---
    all_series_episodes_by_series = defaultdict(dict)
    for sid, s_meta in cache.get('series', {}).items():
        for season in s_meta.get('seasons', []):
            for ep in season.get('episodes', []): all_series_episodes_by_series[sid][ep['id']] = ep
    for sid, watch_throughs in w_series_dict.items():
        if sid not in cache['series']: continue
        meta = cache['series'][sid]
        for p in meta.get('watch_providers', {}).get('flatrate', []):
            if p.get('name'): provider_meta.setdefault(p['name'], {'logo_url': p.get('logo_url')})

        for series_watch in watch_throughs:
            last_watched = max((ep.get('watched_on') for ep in series_watch.get('watched_episodes', {}).values() if ep.get('watched_on')), default=None)
            score = calculate_score(series_watch.get('rating'), last_watched)

            if series_watch.get('rating') is not None: all_ratings.append(series_watch['rating'])
            for g in meta.get('genre', '').split(','):
                if g.strip(): genre_scores[g.strip()] += score
            for a in meta.get('actors', '').split(','):
                if a.strip(): actor_scores[a.strip()] += score
            if meta.get('creator'): director_creator_scores[meta['creator']] += score
            if meta.get('year'): decade_scores[f"{meta['year'][:3]}0s"] += score
            for p in meta.get('watch_providers', {}).get('flatrate', []):
                if p.get('name'): watched_provider_scores[p['name']] += score

            total_episodes_watched += len(series_watch.get('watched_episodes', {}))
            for ep_id, ep_watch in series_watch.get('watched_episodes', {}).items():
                series_watch_time_minutes += all_series_episodes_by_series.get(sid, {}).get(ep_id, {}).get('runtime') or 0
                if ep_watch.get('watched_on'):
                    try:
                        watch_date = datetime.strptime(ep_watch['watched_on'], '%Y-%m-%d')
                        daily_activity[calendar.day_name[watch_date.weekday()]]['count'] += 1
                        monthly_activity[watch_date.strftime('%Y-%m')] += 1
                    except (ValueError, KeyError, TypeError):
                        continue

    # --- Provider Insights (Plan to Watch) ---
    for item_type, items in [('movies', watchlist['planned']['movies']), ('series', watchlist['planned']['series'])]:
        for item in items:
            providers = cache.get(item_type, {}).get(str(item['id']), {}).get('watch_providers', {}).get('flatrate', [])
            for p in providers:
                if p.get('name'):
                    planned_provider_counts[p['name']] += 1
                    provider_meta.setdefault(p['name'], {'logo_url': p.get('logo_url')})

    # --- Final Formatting ---
    total_watch_time_minutes = movie_watch_time_minutes + series_watch_time_minutes
    movies_time_percent = (movie_watch_time_minutes / total_watch_time_minutes * 100) if total_watch_time_minutes > 0 else 0
    ratings_counter = Counter(all_ratings)
    most_active = max(monthly_activity.items(), key=lambda i: i[1], default=('N/A', 0))

    stats_data = {"total_movie_watches": len(w_movies), "total_episodes": total_episodes_watched, "movie_watch_time_minutes": movie_watch_time_minutes, "series_watch_time_minutes": series_watch_time_minutes,
        "total_watch_time_minutes": total_watch_time_minutes, "time_breakdown": {"movies": round(movies_time_percent), "series": round(100 - movies_time_percent)},
        "daily_activity": sorted(daily_activity.items(), key=lambda i: list(calendar.day_name).index(i[0])), "max_daily_count": max((d['count'] for d in daily_activity.values()), default=0),
        "most_active_month": {"month": datetime.strptime(most_active[0], '%Y-%m').strftime('%B %Y') if most_active[0] != 'N/A' else 'N/A', "count": most_active[1]},
        "favorite_genres": sorted(genre_scores.items(), key=lambda i: i[1], reverse=True)[:10], "favorite_actors": sorted(actor_scores.items(), key=lambda i: i[1], reverse=True)[:10],
        "favorite_directors": sorted(director_creator_scores.items(), key=lambda i: i[1], reverse=True)[:10], "favorite_decades": sorted(decade_scores.items(), key=lambda i: i[1], reverse=True)[:5],
        "ratings_dist": {i: ratings_counter.get(i, 0) for i in range(5, 0, -1)}, "max_rating_count": max(ratings_counter.values()) if ratings_counter else 0,
        "planned_providers": [{'name': n, 'count': c, 'logo_url': provider_meta.get(n, {}).get('logo_url')} for n, c in sorted(planned_provider_counts.items(), key=lambda i: i[1], reverse=True)[:5]],
        "watched_providers": [{'name': n, 'score': s, 'logo_url': provider_meta.get(n, {}).get('logo_url')} for n, s in sorted(watched_provider_scores.items(), key=lambda i: i[1], reverse=True)[:5]]}
    return render_template('stats.html', stats=stats_data)


@bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', username=current_user.username)


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    watchlist = data_manager.load_watchlist()
    if request.method == 'POST':
        # Provider preferences
        provider_ids = [int(pid) for pid in request.form.getlist('provider_ids')]
        watchlist['user_preferences']['providers'] = provider_ids
        data_manager.save_watchlist(watchlist)

        # User account settings
        new_username = request.form.get('username')
        new_password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if new_username and new_username != current_user.username:
            if data_manager.find_user_by_username(new_username):
                flash('Username already exists.', 'error')
                return redirect(url_for('main.settings'))
            data_manager.update_user(current_user.id, new_username=new_username)
            flash('Username updated successfully!', 'success')

        if new_password:
            if new_password != password_confirm:
                flash('Passwords do not match.', 'error')
                return redirect(url_for('main.settings'))
            data_manager.update_user(current_user.id, new_password=new_password)
            flash('Password updated successfully!', 'success')

        data_manager.clear_suggestions_cache()  # Clear cache on preference change
        flash('Your settings have been saved!', 'success')
        return redirect(url_for('main.settings'))

    providers = tmdb_api.get_available_providers(region='AT')
    saved_provider_ids = set(watchlist.get('user_preferences', {}).get('providers', []))
    return render_template('settings.html', providers=providers, saved_provider_ids=saved_provider_ids)


@bp.route('/export_watchlist')
@login_required
def export_watchlist():
    """Exports the user's watchlist to a JSON file."""
    watchlist = data_manager.load_watchlist()
    return Response(
        json.dumps(watchlist, indent=4),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment;filename=watchlist.json'}
    )