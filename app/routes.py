# /app/routes.py
import uuid
import requests
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for, current_app, jsonify, Response)
from . import data_manager, tmdb_api, utils
from flask_login import login_user, logout_user, current_user, login_required
from .models import User
import json

bp = Blueprint('main', __name__)


# --- Authentication Routes ---
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.index'))
    if request.method == 'POST':
        username, password, remember = request.form.get('username'), request.form.get('password'), request.form.get('remember') is not None
        user_data = data_manager.find_user_by_username(username)
        user_obj = User(user_data['id'], user_data['username'], user_data['password_hash']) if user_data else None
        if user_obj is None or not user_obj.check_password(password):
            return jsonify({'status': 'error', 'message': 'Invalid username or password.'})
        login_user(user_obj, remember=remember)
        return jsonify({'status': 'success', 'redirect': url_for('main.index')})
    return render_template('login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('main.index'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        if data_manager.find_user_by_username(username):
            return jsonify({'status': 'error', 'message': 'Username already exists. Please choose another.'})
        users_db = data_manager.get_users_db()
        new_user = User(id=users_db['next_id'], username=username, password_hash='')
        new_user.set_password(password)
        users_db['users'].append({'id': new_user.id, 'username': new_user.username, 'password_hash': new_user.password_hash})
        users_db['next_id'] += 1
        data_manager.save_users_db(users_db)
        return jsonify({'status': 'success', 'message': 'Registration successful! Please log in.', 'redirect': url_for('main.login')})
    return render_template('register.html')


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@bp.route('/refresh_suggestions')
@login_required
def refresh_suggestions():
    data_manager.clear_suggestions_cache()
    return redirect(url_for('main.index', message='Suggestions have been refreshed!', category='success'))


# --- Main Routes ---
@bp.route('/')
def index():
    suggestions_cache = data_manager.load_suggestions_cache()
    if 'home_page' not in suggestions_cache:
        print("Generating and caching new homepage suggestions...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
        suggestions_cache['home_page'] = utils.generate_home_page_suggestions(watchlist, cache)
        data_manager.save_suggestions_cache(suggestions_cache)
    cached_data = suggestions_cache['home_page']
    return render_template('index.html', **cached_data)


@bp.route('/movies')
def movies():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    watches = {}
    for watch in watchlist['watched']['movies']: watches.setdefault(watch['id'], []).append(watch)
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
            latest_watch = max(watch_throughs, key=lambda w: max((e.get('watched_on') or '0001-01-01' for e in w.get('watched_episodes', {}).values()), default='0001-01-01'))
            w_ep_c, t_ep_c = len(latest_watch.get('watched_episodes', {})), details.get('total_episode_count', 0)
            last_on = max((e['watched_on'] for e in latest_watch.get('watched_episodes', {}).values() if e.get('watched_on')), default='N/A')
            status = 'Completed' if t_ep_c > 0 and w_ep_c == t_ep_c else 'In Progress'
            watched_items.append({**details, **latest_watch, 'type': 'series', 'watch_count': len(watch_throughs), 'watched_episode_count': w_ep_c, 'total_episode_count': t_ep_c, 'status': status, 'last_watched_on': last_on})
    watched_items.sort(key=lambda x: x.get('last_watched_on') or '0001-01-01', reverse=True)
    planned_items = [{**cache['series'][str(s['id'])], **s, 'type': 'series'} for s in watchlist['planned']['series'] if str(s['id']) in cache['series']]
    return render_template('items_list.html', item_type='series', watched_items=watched_items, planned_items=planned_items)


@bp.route('/item/<item_type>/<int:item_id>')
def item_detail(item_type, item_id):
    details_func = tmdb_api.get_movie_details if item_type == 'movie' else tmdb_api.get_series_details
    details = details_func(item_id)
    if not details:
        return redirect(url_for('main.index', message=f"Could not retrieve details for this {item_type}.", category="error"))
    if item_type == 'movie' and details.get('collection'):
        collection_details = tmdb_api.get_collection_details(details['collection']['id'])
        if not collection_details or len(collection_details.get('parts', [])) <= 1:
            details['collection'] = None
    watchlist = data_manager.load_watchlist()
    today, origin = datetime.now().strftime('%Y-%m-%d'), request.referrer or url_for('main.index')
    item_to_show = {**details, 'type': item_type}
    if item_type == 'movie':
        watch_history = sorted([i for i in watchlist['watched']['movies'] if i.get('id') == item_id], key=lambda x: x.get('watched_on') or '0001-01-01', reverse=True)
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['movies'])
        return render_template('details.html', item=item_to_show, is_planned=is_planned, is_watched=bool(watch_history), today=today, origin=origin, watch_history=watch_history)
    else:  # series
        watch_histories = watchlist['watched']['series'].get(str(item_id), [])
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['series'])
        return render_template('details.html', item=item_to_show, is_planned=is_planned, is_watched=bool(watch_histories), today=today, origin=origin, watch_histories=watch_histories)


@bp.route('/item/<item_type>/<int:item_id>/action', methods=['POST'])
@login_required
def item_detail_action(item_type, item_id):
    internal, watchlist = ('movies' if item_type == 'movie' else 'series'), data_manager.load_watchlist()
    should_clear_cache, action = False, request.form.get('action')
    sid, origin = str(item_id), request.args.get('origin', url_for(f'main.{internal}'))
    response_data = {'status': 'success', 'action': action}

    if action == 'plan':
        if not any(i['id'] == item_id for i in watchlist['planned'][internal]):
            watchlist['planned'][internal].append({"id": item_id})
            should_clear_cache = True
            response_data['message'] = "Added to 'Plan to Watch'."
    elif action == 'remove_plan':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        should_clear_cache = True
        response_data['message'] = "Removed from 'Plan to Watch'."
    elif action == 'watch' and item_type == 'movie':
        new_watch = {"id": item_id, "watch_id": str(uuid.uuid4()), "watched_on": request.form.get('watched_on') or None, "rating": int(r) if (r := request.form.get('rating')) else None}
        watchlist['watched']['movies'].append(new_watch)
        watchlist['planned']['movies'] = [i for i in watchlist['planned']['movies'] if i.get('id') != item_id]
        should_clear_cache = True
        response_data['message'] = "Watch record added."
    elif action == 'delete_all':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        if item_type == 'movie':
            watchlist['watched']['movies'] = [i for i in watchlist['watched']['movies'] if i.get('id') != item_id]
        else:
            watchlist['watched']['series'].pop(sid, None)
        should_clear_cache = True
        data_manager.save_watchlist(watchlist)
        data_manager.clear_suggestions_cache()
        return jsonify({'status': 'success', 'message': 'All records for this item have been deleted.', 'redirect': origin})
    elif action == 'delete_watch_instance' and item_type == 'movie':
        watch_id = request.form.get('watch_id')
        watchlist['watched']['movies'] = [w for w in watchlist['watched']['movies'] if w.get('watch_id') != watch_id]
        response_data.update({'watch_id': watch_id, 'message': 'Watch record deleted.'})
        should_clear_cache = True
    elif action == 'edit_watch_instance' and item_type == 'movie':
        watch_id = request.form.get('watch_id')
        for watch in watchlist['watched']['movies']:
            if watch.get('watch_id') == watch_id:
                watch['watched_on'] = request.form.get('watched_on') or None
                watch['rating'] = int(r) if (r := request.form.get('rating')) and r.isdigit() else None
                response_data.update({'watch_id': watch_id, 'message': 'Watch record updated.'})
                should_clear_cache = True
                break
    elif item_type == 'series':
        series_watch_id = request.form.get('series_watch_id')
        if action == 'start_new_series_watch':
            new_watch = {"series_watch_id": str(uuid.uuid4()), "watched_episodes": {}}
            watchlist['watched']['series'].setdefault(sid, []).append(new_watch)
            watchlist['planned']['series'] = [s for s in watchlist['planned']['series'] if s.get('id') != item_id]
            should_clear_cache = True
            response_data['message'] = "New watch started for this series."
        elif action == 'delete_series_watch':
            if sid in watchlist['watched']['series'] and series_watch_id:
                watchlist['watched']['series'][sid] = [w for w in watchlist['watched']['series'][sid] if w.get('series_watch_id') != series_watch_id]
                if not watchlist['watched']['series'][sid]: del watchlist['watched']['series'][sid]
                should_clear_cache = True
                response_data['message'] = "Watch history for this session deleted."
        else:
            watch_through = next((w for w in watchlist['watched']['series'].get(sid, []) if w.get('series_watch_id') == series_watch_id), None)
            if watch_through:
                if action == 'toggle_episode':
                    eid = request.form['episode_id']
                    if eid in watch_through['watched_episodes']:
                        del watch_through['watched_episodes'][eid]
                        response_data['message'] = "Episode marked as unwatched."
                    else:
                        watch_through['watched_episodes'][eid] = {"watched_on": request.form.get('watched_on') or None}
                        response_data['message'] = "Episode marked as watched."
                    should_clear_cache = True
                elif action == 'rate_series':
                    if r_str := request.form.get('rating'):
                        watch_through['rating'] = int(r_str)
                        response_data['message'] = "Series rating updated."
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
                        date = request.form.get('watched_on') or None
                        if action.startswith('watch'):
                            for eid in episode_ids: watch_through['watched_episodes'].setdefault(eid, {"watched_on": date})
                            response_data['message'] = "Episodes marked as watched."
                        else:
                            for eid in episode_ids: watch_through['watched_episodes'].pop(eid, None)
                            response_data['message'] = "Episodes marked as unwatched."
                        should_clear_cache = True
    if should_clear_cache:
        data_manager.save_watchlist(watchlist)
        data_manager.clear_suggestions_cache()
    if action in ['plan', 'remove_plan']:
        response_data['is_planned'] = any(i['id'] == item_id for i in watchlist['planned'][internal])
    if action == 'toggle_episode':
        watch_through = next((w for w_list in watchlist['watched']['series'].get(sid, []) for w in [w_list] if w.get('series_watch_id') == request.form.get('series_watch_id')), None)
        if watch_through:
            response_data['is_episode_watched'] = request.form.get('episode_id') in watch_through.get('watched_episodes', {})
            response_data['watched_on'] = watch_through.get('watched_episodes', {}).get(request.form.get('episode_id'), {}).get('watched_on')
            response_data['watched_episode_count'] = len(watch_through.get('watched_episodes', {}))
            series_details = tmdb_api.get_series_details(item_id)
            response_data['total_episode_count'] = series_details.get('total_episode_count')
            response_data['series_watch_id'] = request.form.get('series_watch_id')
    return jsonify(response_data)


@bp.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    return redirect(url_for('main.show_search_results', q=query) if query else url_for('main.index'))


@bp.route('/search_results')
def show_search_results():
    query, results, api_key = request.args.get('q', ''), [], current_app.config['TMDB_API_KEY']
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
            return redirect(url_for('main.index', message=f"API Error: {e}", category="error"))
    watchlist = data_manager.load_watchlist()
    p_m_ids, w_m_ids = {i['id'] for i in watchlist['planned']['movies']}, {i['id'] for i in watchlist['watched']['movies']}
    p_s_ids, w_s_ids = {int(id) for id in watchlist['planned']['series']}, {int(id) for id in watchlist['watched']['series']}
    for item in results:
        is_movie, item_id = (item['type'] == 'movie'), item['id']
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
        return redirect(url_for('main.index', message="Could not retrieve collection details.", category="error"))
    watchlist = data_manager.load_watchlist()
    p_m_ids, w_m_ids = {i['id'] for i in watchlist['planned']['movies']}, {i['id'] for i in watchlist['watched']['movies']}
    for item in collection.get('parts', []):
        if item['id'] in w_m_ids:
            item['status'] = 'watched'
        elif item['id'] in p_m_ids:
            item['status'] = 'planned'
        else:
            item['status'] = None
    return render_template('collection_details.html', collection=collection)


@bp.route('/collections')
def collections():
    suggestions_cache = data_manager.load_suggestions_cache()
    if 'collections_page' not in suggestions_cache:
        print("Generating and caching new collections page...")
        watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
        suggestions_cache['collections_page'] = utils.generate_collections_page_suggestions(watchlist, cache)
        data_manager.save_suggestions_cache(suggestions_cache)
    cached_data = suggestions_cache['collections_page']
    return render_template('collections_list.html', **cached_data)


# --- User Profile, Settings, Stats ---
@bp.route('/stats')
@login_required
def stats():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    stats_data = utils.generate_stats_page_data(watchlist, cache)
    return render_template('stats.html', stats=stats_data)


@bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', username=current_user.username)


@bp.route('/settings', methods=['GET'])
@login_required
def settings():
    watchlist = data_manager.load_watchlist()
    providers = tmdb_api.get_available_providers(region='AT')
    saved_provider_ids = set(watchlist.get('user_preferences', {}).get('providers', []))
    return render_template('settings.html', providers=providers, saved_provider_ids=saved_provider_ids)

@bp.route('/check_username', methods=['POST'])
@login_required
def check_username():
    username = request.form.get('username', '').strip()
    if not username:
        return jsonify({'available': False})
    if username.lower() == current_user.username.lower():
        return jsonify({'available': True}) # Same as current user
    user = data_manager.find_user_by_username(username)
    return jsonify({'available': user is None})

@bp.route('/change_username', methods=['POST'])
@login_required
def change_username():
    new_username = request.form.get('username', '').strip()
    if not new_username or new_username.lower() == current_user.username.lower():
        return jsonify({'status': 'error', 'message': 'Please enter a new username.'})
    if data_manager.find_user_by_username(new_username):
        return jsonify({'status': 'error', 'message': 'Username already exists.'})

    if data_manager.update_user(current_user.id, new_username=new_username):
        # Update the username in the session
        logout_user()
        user_data = data_manager.find_user_by_id(current_user.id)
        login_user(User(user_data['id'], user_data['username'], user_data['password_hash']), remember=True)
        return jsonify({'status': 'success', 'message': 'Username updated successfully!', 'new_username': new_username})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to update username.'})

@bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    password_confirm = request.form.get('password_confirm')

    if not current_password or not new_password or not password_confirm:
        return jsonify({'status': 'error', 'message': 'Please fill in all password fields.'})
    if not current_user.check_password(current_password):
        return jsonify({'status': 'error', 'message': 'Your current password was incorrect.'})
    if new_password != password_confirm:
        return jsonify({'status': 'error', 'message': 'New passwords do not match.'})

    if data_manager.update_user(current_user.id, new_password=new_password):
        return jsonify({'status': 'success', 'message': 'Password updated successfully!'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to update password.'})

@bp.route('/save_providers', methods=['POST'])
@login_required
def save_providers():
    watchlist = data_manager.load_watchlist()
    new_providers = {int(pid) for pid in request.form.getlist('provider_ids[]')}
    watchlist.setdefault('user_preferences', {})['providers'] = list(new_providers)
    data_manager.save_watchlist(watchlist)
    data_manager.clear_suggestions_cache()
    return jsonify({'status': 'success', 'message': 'Watch providers updated!', 'count': len(new_providers)})


@bp.route('/export_watchlist')
@login_required
def export_watchlist():
    watchlist = data_manager.load_watchlist()
    return Response(json.dumps(watchlist, indent=4), mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=watchlist.json'})


@bp.route('/import_watchlist', methods=['POST'])
@login_required
def import_watchlist():
    message, category = 'An unexpected error occurred.', 'error'
    if 'watchlist_file' not in request.files:
        message, category = 'No file part in the request.', 'error'
    else:
        file = request.files['watchlist_file']
        if file.filename == '':
            message, category = 'No file selected.', 'error'
        elif file and file.filename.endswith('.json'):
            try:
                content = file.read()
                new_watchlist = json.loads(content)
                if 'watched' not in new_watchlist or 'planned' not in new_watchlist or 'user_preferences' not in new_watchlist:
                    raise ValueError("Invalid watchlist format.")
                data_manager.save_watchlist(new_watchlist)
                utils.sync_cache_with_watchlist(current_app._get_current_object())
                print("Import successful. Regenerating suggestions cache...")
                watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
                suggestions_cache = data_manager.load_suggestions_cache()
                suggestions_cache['home_page'] = utils.generate_home_page_suggestions(watchlist, cache)
                suggestions_cache['collections_page'] = utils.generate_collections_page_suggestions(watchlist, cache)
                data_manager.save_suggestions_cache(suggestions_cache)
                print("Suggestions cache regenerated.")
                message, category = 'Watchlist imported and all suggestions have been updated!', 'success'
            except (json.JSONDecodeError, ValueError) as e:
                message, category = f'Error importing file: Invalid JSON or format. {e}', 'error'
            except Exception as e:
                message, category = f'An unexpected error occurred: {e}', 'error'
        else:
            message, category = 'Invalid file type. Please upload a .json file.', 'error'
    return redirect(url_for('main.profile', message=message, category=category))


@bp.route('/clear_watchlist', methods=['POST'])
@login_required
def clear_watchlist():
    if data_manager.clear_user_data():
        return jsonify({'status': 'success', 'message': 'Your watchlist data has been successfully cleared.'})
    else:
        return jsonify({'status': 'error', 'message': 'There was an error clearing your watchlist data.'})


@bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user_id_to_delete = current_user.id
    user_username_to_delete = current_user.username
    logout_user()
    if data_manager.delete_user(user_id_to_delete):
        return jsonify({'status': 'success', 'message': f'Account "{user_username_to_delete}" has been permanently deleted.', 'redirect': url_for('main.index')})
    else:
        return jsonify({'status': 'error', 'message': 'There was an error deleting your account.'})