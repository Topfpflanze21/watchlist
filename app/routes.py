# /app/routes.py
import uuid
import random
import requests
from datetime import datetime
from collections import Counter
from flask import (Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify)
from . import data_manager, tmdb_api, utils

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()

    planned_movies = watchlist['planned']['movies']
    planned_series = watchlist['planned']['series']
    random.shuffle(planned_movies)
    random.shuffle(planned_series)

    p_movie_suggs = [{**cache['movies'][str(i['id'])], 'type': 'movie'} for i in planned_movies[:6] if str(i['id']) in cache['movies']]
    p_series_suggs = [{**cache['series'][str(i['id'])], 'type': 'series'} for i in planned_series[:6] if str(i['id']) in cache['series']]

    return render_template('index.html', planned_movie_suggestions=p_movie_suggs, planned_series_suggestions=p_series_suggs, smart_movie_suggestions=utils.get_smart_suggestions('movies'),
        smart_series_suggestions=utils.get_smart_suggestions('series'))


@bp.route('/movies')
def movies():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    watches = {}
    for watch in watchlist['watched']['movies']:
        watches.setdefault(watch['id'], []).append(watch)

    watched_items = sorted([({**cache['movies'][str(id)], **max(w, key=lambda x: x['watched_on']), 'watch_count': len(w), 'type': 'movie'}) for id, w in watches.items() if str(id) in cache['movies']], key=lambda x: x['watched_on'], reverse=True)

    planned_items = [{**cache['movies'][str(m['id'])], **m, 'type': 'movie'} for m in watchlist['planned']['movies'] if str(m['id']) in cache['movies']]
    return render_template('items_list.html', item_type='movies', watched_items=watched_items, planned_items=planned_items)


@bp.route('/series')
def series():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    watched_items = []
    for sid, sdata in watchlist['watched']['series'].items():
        if sid in cache['series']:
            details = cache['series'][sid]
            w_ep_c = len(sdata.get('watched_episodes', {}))
            t_ep_c = details.get('total_episode_count', 0)
            last_on = max(e['watched_on'] for e in sdata['watched_episodes'].values()) if sdata.get('watched_episodes') else 'N/A'
            status = 'Completed' if t_ep_c > 0 and w_ep_c == t_ep_c else 'In Progress'
            watched_items.append({**details, **sdata, 'type': 'series', 'watched_episode_count': w_ep_c, 'total_episode_count': t_ep_c, 'status': status, 'last_watched_on': last_on})

    watched_items.sort(key=lambda x: x['last_watched_on'], reverse=True)
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

    watchlist = data_manager.load_watchlist()
    today = datetime.now().strftime('%Y-%m-%d')
    item_to_show = {**details, 'type': item_type}
    origin = request.referrer or url_for(f'main.{internal_type}')

    if item_type == 'movie':
        watch_history = sorted([i for i in watchlist['watched']['movies'] if i.get('id') == item_id], key=lambda x: x['watched_on'], reverse=True)
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['movies'])
        is_watched = bool(watch_history)
        if is_watched: item_to_show.update(watch_history[0])
        return render_template('details.html', item=item_to_show, is_planned=is_planned, is_watched=is_watched, today=today, origin=origin, watch_history=watch_history, internal_type=internal_type)
    else:  # series
        sdata = watchlist['watched']['series'].get(str(item_id))
        ep_ids = list(sdata['watched_episodes'].keys()) if sdata and 'watched_episodes' in sdata else []
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['series'])
        is_watched = bool(sdata)
        return render_template('details.html', item=item_to_show, is_planned=is_planned, is_watched=is_watched, today=today, origin=origin, watched_series_data=sdata, watched_episode_ids=ep_ids, internal_type=internal_type)


@bp.route('/item/<item_type>/<int:item_id>/action', methods=['POST'])
def item_detail_action(item_type, item_id):
    internal, watchlist = ('movies' if item_type == 'movie' else 'series'), data_manager.load_watchlist()
    origin = request.args.get('origin', url_for(f'main.{internal}'))
    action = request.form.get('action')
    title = request.args.get('title', 'The item')

    if action == 'plan':
        if not any(i.get('id') == item_id for i in watchlist['planned'][internal]):
            watchlist['planned'][internal].append({"id": item_id});
            data_manager.save_watchlist(watchlist)
    elif action == 'remove_plan':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        data_manager.save_watchlist(watchlist);
    elif action == 'watch' and item_type == 'movie':
        watchlist['watched']['movies'].append({"id": item_id, "watch_id": str(uuid.uuid4()), "watched_on": request.form['watched_on'], "rating": int(request.form['rating'])})
        watchlist['planned']['movies'] = [i for i in watchlist['planned']['movies'] if i.get('id') != item_id]
        data_manager.save_watchlist(watchlist);
    elif action == 'delete_all':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        if item_type == 'movie':
            watchlist['watched']['movies'] = [i for i in watchlist['watched']['movies'] if i.get('id') != item_id]
        else:
            watchlist['watched']['series'].pop(str(item_id), None)
        data_manager.save_watchlist(watchlist);
        return redirect(origin)
    elif action == 'delete_watch_instance' and item_type == 'movie':
        watchlist['watched']['movies'] = [w for w in watchlist['watched']['movies'] if w.get('watch_id') != request.form.get('watch_id')]
        data_manager.save_watchlist(watchlist);
    elif action == 'toggle_episode' and item_type == 'series':
        sid, eid, date = str(item_id), request.form['episode_id'], request.form['watched_on']
        entry = watchlist['watched']['series'].setdefault(sid, {"id": item_id, "watched_episodes": {}})
        if eid in entry['watched_episodes']:
            del entry['watched_episodes'][eid]
        else:
            entry['watched_episodes'][eid] = {"watched_on": date}
        if not entry['watched_episodes'] and not any(i.get('id') == item_id for i in watchlist['planned']['series']):
            del watchlist['watched']['series'][sid]
        watchlist['planned']['series'] = [i for i in watchlist['planned']['series'] if i.get('id') != item_id]
        data_manager.save_watchlist(watchlist)
    elif action == 'watch_season' and item_type == 'series':
        season_num_str = request.form.get('season_number')
        if not season_num_str: return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
        season_num_to_watch = int(season_num_str)
        date, sid = request.form['watched_on'], str(item_id)
        details = tmdb_api.get_series_details(item_id)
        if not details or not details.get('seasons'): return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
        episode_ids_to_add = [ep['id'] for season in details.get('seasons', []) if season.get('season_number') == season_num_to_watch for ep in season.get('episodes', [])]
        if episode_ids_to_add:
            entry = watchlist['watched']['series'].setdefault(sid, {"id": item_id, "watched_episodes": {}})
            for eid in episode_ids_to_add:
                if eid not in entry['watched_episodes']: entry['watched_episodes'][eid] = {"watched_on": date}
            watchlist['planned']['series'] = [i for i in watchlist['planned']['series'] if i.get('id') != item_id]
            data_manager.save_watchlist(watchlist)
        return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
    elif action == 'unwatch_season' and item_type == 'series':
        season_num_str = request.form.get('season_number')
        if not season_num_str: return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
        season_num_to_unwatch = int(season_num_str)
        sid, details = str(item_id), tmdb_api.get_series_details(item_id)
        if not details or not details.get('seasons'): return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
        episode_ids_to_remove = [ep['id'] for season in details.get('seasons', []) if season.get('season_number') == season_num_to_unwatch for ep in season.get('episodes', [])]
        if sid in watchlist['watched']['series'] and 'watched_episodes' in watchlist['watched']['series'][sid]:
            for eid in episode_ids_to_remove:
                if eid in watchlist['watched']['series'][sid]['watched_episodes']: del watchlist['watched']['series'][sid]['watched_episodes'][eid]
            if not watchlist['watched']['series'][sid]['watched_episodes'] and 'rating' not in watchlist['watched']['series'][sid]:
                del watchlist['watched']['series'][sid]
            data_manager.save_watchlist(watchlist)
        return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
    elif action in ['watch_all_episodes', 'unwatch_all_episodes'] and item_type == 'series':
        # These are heavy actions, a reload is fine.
        if action == 'watch_all_episodes':
            details = tmdb_api.get_series_details(item_id)
            if details and details.get('seasons'):
                sid, date = str(item_id), request.form['watched_on']
                entry = watchlist['watched']['series'].setdefault(sid, {"id": item_id, "watched_episodes": {}})
                all_episode_ids = [ep['id'] for season in details.get('seasons', []) for ep in season.get('episodes', [])]
                for eid in all_episode_ids:
                    if eid not in entry['watched_episodes']: entry['watched_episodes'][eid] = {"watched_on": date}
                watchlist['planned']['series'] = [i for i in watchlist['planned']['series'] if i.get('id') != item_id]
                data_manager.save_watchlist(watchlist)
        else: # unwatch
            if str(item_id) in watchlist['watched']['series']:
                del watchlist['watched']['series'][str(item_id)]
                data_manager.save_watchlist(watchlist)
        return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))
    elif action == 'rate_series' and item_type == 'series':
        entry = watchlist['watched']['series'].setdefault(str(item_id), {"id": item_id, "watched_episodes": {}})
        entry['rating'] = int(request.form['rating'])
        data_manager.save_watchlist(watchlist);

    # AJAX response for most actions
    response_data = {'status': 'success', 'action': action}
    if item_type == 'series':
        cache = data_manager.load_cache()
        sdata = watchlist['watched']['series'].get(str(item_id))
        watched_count = len(sdata.get('watched_episodes', {})) if sdata else 0
        total_count = cache.get("series", {}).get(str(item_id), {}).get("total_episode_count", 0)
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['series'])
        response_data.update({
            'watched_episode_count': watched_count, 'total_episode_count': total_count,
            'is_watched': bool(sdata), 'is_planned': is_planned })
        if action == 'toggle_episode':
            eid = request.form['episode_id']
            is_watched_ep = sdata and eid in sdata.get('watched_episodes', {})
            response_data['episode_id'] = eid
            response_data['is_episode_watched'] = is_watched_ep
            if is_watched_ep: response_data['watched_on'] = sdata['watched_episodes'][eid]['watched_on']
    elif item_type == 'movie':
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['movies'])
        watch_history = [i for i in watchlist['watched']['movies'] if i.get('id') == item_id]
        response_data.update({'is_planned': is_planned, 'is_watched': bool(watch_history)})
        if action == 'watch':
            response_data['new_watch_record'] = sorted(watch_history, key=lambda x: x['watched_on'], reverse=True)[0]
        if action == 'delete_watch_instance':
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


@bp.route('/stats')
def stats():
    watchlist, cache = data_manager.load_watchlist(), data_manager.load_cache()
    w_movies = watchlist['watched']['movies']
    w_series = list(watchlist['watched']['series'].values())

    all_ratings = [i['rating'] for i in w_movies if 'rating' in i] + [s['rating'] for s in w_series if 'rating' in s]

    genres = []
    watched_item_ids = {m['id'] for m in w_movies} | {s['id'] for s in w_series}
    for item_id in watched_item_ids:
        meta = cache['movies'].get(str(item_id)) or cache['series'].get(str(item_id))
        if meta and meta.get('genre'):
            genres.extend([g.strip() for g in meta['genre'].split(',') if g.strip()])

    stats_data = {"total_movies": len({m['id'] for m in w_movies}), "total_movie_watches": len(w_movies), "total_episodes": sum(len(s.get('watched_episodes', {})) for s in w_series), "total_items": len(all_ratings),
        "ratings_dist": dict(sorted(Counter(all_ratings).items(), key=lambda i: i[0], reverse=True)), "genre_dist": Counter(genres).most_common(10)}
    return render_template('stats.html', stats=stats_data)