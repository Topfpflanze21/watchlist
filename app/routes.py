# /app/routes.py
import uuid
import random
import requests
import calendar
from datetime import datetime
from collections import Counter, defaultdict
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
            latest_watch = max(watch_throughs, key=lambda w: max((e.get('watched_on', '0001-01-01') for e in w.get('watched_episodes', {}).values()), default='0001-01-01'))

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
def item_detail_action(item_type, item_id):
    internal, watchlist = ('movies' if item_type == 'movie' else 'series'), data_manager.load_watchlist()
    origin = request.args.get('origin', url_for(f'main.{internal}'))
    action = request.form.get('action')
    sid = str(item_id)

    if action == 'plan':
        if not any(i.get('id') == item_id for i in watchlist['planned'][internal]):
            watchlist['planned'][internal].append({"id": item_id})
            data_manager.save_watchlist(watchlist)
    elif action == 'remove_plan':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        data_manager.save_watchlist(watchlist)
    elif action == 'watch' and item_type == 'movie':
        watched_on = request.form.get('watched_on') or None
        rating = int(request.form['rating']) if request.form.get('rating') else None
        new_watch = {"id": item_id, "watch_id": str(uuid.uuid4()), "watched_on": watched_on, "rating": rating}
        watchlist['watched']['movies'].append(new_watch)
        watchlist['planned']['movies'] = [i for i in watchlist['planned']['movies'] if i.get('id') != item_id]
        data_manager.save_watchlist(watchlist)
    elif action == 'delete_all':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        if item_type == 'movie':
            watchlist['watched']['movies'] = [i for i in watchlist['watched']['movies'] if i.get('id') != item_id]
        else:
            watchlist['watched']['series'].pop(sid, None)
        data_manager.save_watchlist(watchlist)
        flash(f"Successfully deleted all records.", "success")
        return redirect(origin)
    elif action == 'delete_watch_instance' and item_type == 'movie':
        watch_id = request.form.get('watch_id')
        watchlist['watched']['movies'] = [w for w in watchlist['watched']['movies'] if w.get('watch_id') != watch_id]
        data_manager.save_watchlist(watchlist)
    # --- Series Multi-Watch Actions ---
    elif item_type == 'series':
        series_watch_id = request.form.get('series_watch_id')

        if action == 'start_new_series_watch':
            new_watch = {"series_watch_id": str(uuid.uuid4()), "watched_episodes": {}}
            # Be explicit about creating the list if it doesn't exist
            if sid not in watchlist['watched']['series']:
                watchlist['watched']['series'][sid] = []
            watchlist['watched']['series'][sid].append(new_watch)
            watchlist['planned']['series'] = [s for s in watchlist['planned']['series'] if s.get('id') != item_id]
            data_manager.save_watchlist(watchlist)
            return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))

        elif action == 'delete_series_watch':
            if sid in watchlist['watched']['series'] and series_watch_id:
                watchlist['watched']['series'][sid] = [w for w in watchlist['watched']['series'][sid] if w.get('series_watch_id') != series_watch_id]
                if not watchlist['watched']['series'][sid]:  # If no watch histories are left, remove the series key
                    del watchlist['watched']['series'][sid]
                data_manager.save_watchlist(watchlist)
            return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))

        # Find the specific watch-through to modify
        watch_through = None
        if sid in watchlist['watched']['series'] and series_watch_id:
            for w in watchlist['watched']['series'][sid]:
                if w.get('series_watch_id') == series_watch_id:
                    watch_through = w
                    break

        if not watch_through:  # Should not happen if series_watch_id is provided
            return jsonify({'status': 'error', 'message': 'Watch history not found.'}), 404

        date = request.form.get('watched_on') or None
        if action == 'toggle_episode':
            eid = request.form['episode_id']
            if eid in watch_through['watched_episodes']:
                del watch_through['watched_episodes'][eid]
            else:
                watch_through['watched_episodes'][eid] = {"watched_on": date}
            data_manager.save_watchlist(watchlist)

        elif action == 'rate_series':
            rating_str = request.form.get('rating')
            if rating_str:
                watch_through['rating'] = int(rating_str)
                data_manager.save_watchlist(watchlist)

        elif action in ['watch_season', 'unwatch_season', 'watch_all_episodes', 'unwatch_all_episodes']:
            details = tmdb_api.get_series_details(item_id)
            if not details or not details.get('seasons'):
                return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))

            episode_ids = []
            if action in ['watch_season', 'unwatch_season']:
                season_num = int(request.form['season_number'])
                episode_ids = [ep['id'] for s in details.get('seasons', []) if s.get('season_number') == season_num for ep in s.get('episodes', [])]
            elif action in ['watch_all_episodes', 'unwatch_all_episodes']:
                episode_ids = [ep['id'] for s in details.get('seasons', []) for ep in s.get('episodes', [])]

            if action in ['watch_season', 'watch_all_episodes']:
                for eid in episode_ids:
                    if eid not in watch_through['watched_episodes']:
                        watch_through['watched_episodes'][eid] = {"watched_on": date}
            elif action in ['unwatch_season', 'unwatch_all_episodes']:
                for eid in episode_ids:
                    if eid in watch_through['watched_episodes']:
                        del watch_through['watched_episodes'][eid]

            data_manager.save_watchlist(watchlist)
            return redirect(url_for('main.item_detail', item_type=item_type, item_id=item_id, origin=origin))

    # AJAX response for most actions
    response_data = {'status': 'success', 'action': action}
    if item_type == 'series':
        cache = data_manager.load_cache()
        watch_histories = watchlist['watched']['series'].get(str(item_id), [])
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['series'])

        response_data.update({'is_watched': bool(watch_histories), 'is_planned': is_planned})

        if action == 'toggle_episode':
            series_watch_id = request.form.get('series_watch_id')
            current_watch = next((w for w in watch_histories if w['series_watch_id'] == series_watch_id), None)
            if current_watch:
                eid = request.form['episode_id']
                is_watched_ep = eid in current_watch.get('watched_episodes', {})
                response_data.update({'episode_id': eid, 'series_watch_id': series_watch_id, 'is_episode_watched': is_watched_ep, 'watched_on': current_watch['watched_episodes'][eid].get('watched_on') if is_watched_ep else None,
                    'watched_episode_count': len(current_watch.get('watched_episodes', {})), 'total_episode_count': cache.get("series", {}).get(sid, {}).get("total_episode_count", 0)})
    elif item_type == 'movie':
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['movies'])
        watch_history = [i for i in watchlist['watched']['movies'] if i.get('id') == item_id]
        response_data.update({'is_planned': is_planned, 'is_watched': bool(watch_history)})
        if action == 'watch':
            response_data['new_watch_record'] = sorted(watch_history, key=lambda x: x.get('watched_on') or '0001-01-01', reverse=True)[0]
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
    w_series_dict = watchlist['watched']['series']

    # --- Main Data Aggregation ---
    all_ratings = []
    actors = []
    directors_creators = []
    genres = []
    decades = []
    daily_activity = defaultdict(lambda: {'count': 0, 'runtime': 0})
    monthly_activity = defaultdict(lambda: {'count': 0, 'runtime': 0})
    movie_watch_time_minutes = 0
    series_watch_time_minutes = 0
    total_episodes_watched = 0

    # 1. Process Movies
    for movie_watch in w_movies:
        movie_id_str = str(movie_watch['id'])
        if movie_id_str not in cache['movies']: continue
        meta = cache['movies'][movie_id_str]
        if movie_watch.get('rating') is not None: all_ratings.append(movie_watch['rating'])
        if meta.get('actors'): actors.extend([a.strip() for a in meta['actors'].split(',') if a.strip()])
        if meta.get('director'): directors_creators.append(meta['director'])
        if meta.get('genre'): genres.extend([g.strip() for g in meta['genre'].split(',') if g.strip()])
        if meta.get('year'): decades.append(f"{meta['year'][:3]}0s")
        runtime = meta.get('runtime') or 0
        movie_watch_time_minutes += runtime
        try:
            watch_date_str = movie_watch.get('watched_on')
            if not watch_date_str: continue
            watch_date = datetime.strptime(watch_date_str, '%Y-%m-%d')
            day_name = calendar.day_name[watch_date.weekday()]
            month_key = watch_date.strftime('%Y-%m')
            daily_activity[day_name]['count'] += 1
            daily_activity[day_name]['runtime'] += runtime
            monthly_activity[month_key]['count'] += 1
            monthly_activity[month_key]['runtime'] += runtime
        except (ValueError, KeyError, TypeError):
            continue

    # 2. Process Series (with multi-watch)
    # FIX: Create a nested dictionary for episode metadata to prevent ID collisions between different series.
    all_series_episodes_by_series = defaultdict(dict)
    if 'series' in cache:
        for sid_cache, s_meta in cache['series'].items():
            for season in s_meta.get('seasons', []):
                for ep in season.get('episodes', []):
                    all_series_episodes_by_series[sid_cache][ep['id']] = ep

    for sid, watch_throughs in w_series_dict.items():
        if sid not in cache['series']: continue
        meta = cache['series'][sid]

        for series_watch in watch_throughs:
            if series_watch.get('rating') is not None: all_ratings.append(series_watch['rating'])
        if meta.get('actors'): actors.extend([a.strip() for a in meta['actors'].split(',') if a.strip()])
        if meta.get('creator'): directors_creators.append(meta['creator'])
        if meta.get('genre'): genres.extend([g.strip() for g in meta['genre'].split(',') if g.strip()])
        if meta.get('year'): decades.append(f"{meta['year'][:3]}0s")

        for series_watch in watch_throughs:
            total_episodes_watched += len(series_watch.get('watched_episodes', {}))
            for ep_id, ep_watch in series_watch.get('watched_episodes', {}).items():
                # FIX: Look up the episode metadata from the series-specific nested dictionary.
                episode_meta = all_series_episodes_by_series.get(sid, {}).get(ep_id)
                runtime = episode_meta.get('runtime') if episode_meta else 0
                if not runtime: continue
                series_watch_time_minutes += runtime
                try:
                    watch_date_str = ep_watch.get('watched_on')
                    if not watch_date_str: continue
                    watch_date = datetime.strptime(watch_date_str, '%Y-%m-%d')
                    day_name = calendar.day_name[watch_date.weekday()]
                    month_key = watch_date.strftime('%Y-%m')
                    daily_activity[day_name]['count'] += 1
                    daily_activity[day_name]['runtime'] += runtime
                    monthly_activity[month_key]['count'] += 1
                    monthly_activity[month_key]['runtime'] += runtime
                except (ValueError, KeyError, TypeError):
                    continue

    # --- Final Calculations ---
    total_watch_time_minutes = movie_watch_time_minutes + series_watch_time_minutes
    most_active_month = max(monthly_activity.items(), key=lambda i: i[1]['count']) if monthly_activity else ('N/A', {'count': 0})
    day_order = list(calendar.day_name)
    sorted_daily_activity = sorted(daily_activity.items(), key=lambda i: day_order.index(i[0]))
    max_daily_count = max((d[1]['count'] for d in sorted_daily_activity), default=0)
    movies_time_percent = (movie_watch_time_minutes / total_watch_time_minutes * 100) if total_watch_time_minutes > 0 else 0
    unique_movies = len({m['id'] for m in w_movies})
    total_movie_watches = len(w_movies)

    stats_data = {"total_movies": unique_movies, "total_movie_watches": total_movie_watches, "total_episodes": total_episodes_watched, "movie_watch_time_minutes": movie_watch_time_minutes, "series_watch_time_minutes": series_watch_time_minutes,
                  "total_watch_time_minutes": total_watch_time_minutes, "total_items": len(all_ratings), "ratings_dist": dict(sorted(Counter(all_ratings).items(), key=lambda i: i[0], reverse=True)), "rewatches": total_movie_watches - unique_movies,
                  "favorite_genres": Counter(genres).most_common(10), "favorite_actors": Counter(actors).most_common(10), "favorite_directors": Counter(d for d in directors_creators if d).most_common(10),
                  "favorite_decades": Counter(decades).most_common(5), "daily_activity": sorted_daily_activity, "max_daily_count": max_daily_count,
                  "most_active_month": {"month": datetime.strptime(most_active_month[0], '%Y-%m').strftime('%B %Y') if most_active_month[0] != 'N/A' else 'N/A', "count": most_active_month[1]['count']},
                  "time_breakdown": {"movies": round(movies_time_percent), "series": round(100 - movies_time_percent), }}
    return render_template('stats.html', stats=stats_data)