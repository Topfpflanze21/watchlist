# /app/tmdb_api.py
import requests
from flask import current_app
from . import data_manager


def find_trailer_key(videos_results):
    """Finds the best trailer key from a list of video results."""
    trailer, teaser = None, None
    for video in videos_results:
        if video.get('site') == 'YouTube':
            is_official_trailer = video.get('type') == 'Trailer' and video.get('official', False)
            if is_official_trailer: return video.get('key')
            if video.get('type') == 'Trailer' and not trailer: trailer = video.get('key')
            if video.get('type') == 'Teaser' and not teaser: teaser = video.get('key')
    return trailer or teaser


def get_movie_details(movie_id):
    """Fetches detailed movie information from TMDB, using a cache to avoid redundant API calls."""
    cache = data_manager.load_cache()
    cache_entry = cache.get("movies", {}).get(str(movie_id))
    if cache_entry and 'trailer_key' in cache_entry and 'watch_providers' in cache_entry and 'director' in cache_entry:
        return cache_entry

    api_key = current_app.config['TMDB_API_KEY']
    if not api_key or api_key == "YOUR_API_KEY_HERE": return None

    try:
        url = f"{current_app.config['TMDB_BASE_URL']}/movie/{movie_id}?api_key={api_key}&append_to_response=credits,recommendations,videos,watch/providers"
        res = requests.get(url)
        res.raise_for_status()
        d = res.json()
        image_url = current_app.config['TMDB_IMAGE_URL']
        director = next((p['name'] for p in d.get("credits", {}).get("crew", []) if p.get('job') == 'Director'), "")
        collection = d.get('belongs_to_collection')

        data = {"id": d.get("id"), "title": d.get("title"), "year": d.get("release_date", "")[:4], "poster_url": f"{image_url}{d.get('poster_path')}" if d.get('poster_path') else "", "genre": ", ".join([g['name'] for g in d.get("genres", [])]),
            "actors": ", ".join([c['name'] for c in d.get("credits", {}).get("cast", [])[:5]]), "director": director, "plot": d.get("overview"), "runtime": d.get('runtime'), 'trailer_key': find_trailer_key(d.get("videos", {}).get("results", [])),
            'collection': collection,
            'recommendations': [{"id": r.get("id"), "title": r.get("title"), "type": "movie", "poster_url": f"{image_url}{r.get('poster_path')}", "year": r.get("release_date", "")[:4], } for r in d.get("recommendations", {}).get("results", []) if
                                   r.get('poster_path')][:12]}

        providers = d.get('watch/providers', {}).get('results', {}).get('AT', {})
        data['watch_providers'] = {'link': providers.get('link', ''),
            'flatrate': sorted([{'name': p.get('provider_name'), 'logo_url': f"{image_url}{p.get('logo_path')}"} for p in providers.get('flatrate', []) if p.get('logo_path')], key=lambda x: x.get('display_priority', 99))}

        cache["movies"][str(movie_id)] = data
        data_manager.save_cache(cache)
        return data
    except requests.RequestException as e:
        print(f"Error fetching movie details for ID {movie_id}: {e}")
        return None


def get_collection_details(collection_id):
    """Fetches details for a movie collection from TMDB."""
    api_key = current_app.config['TMDB_API_KEY']
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        return None

    try:
        url = f"{current_app.config['TMDB_BASE_URL']}/collection/{collection_id}?api_key={api_key}"
        res = requests.get(url)
        res.raise_for_status()
        d = res.json()
        image_url = current_app.config['TMDB_IMAGE_URL']

        parts = sorted(d.get('parts', []), key=lambda x: x.get('release_date') or '9999-99-99')

        data = {"id": d.get("id"), "name": d.get("name"), "overview": d.get("overview"), "poster_url": f"{image_url}{d.get('poster_path')}" if d.get('poster_path') else "",
            "parts": [{"id": p.get("id"), "title": p.get("title"), "year": p.get("release_date", "")[:4], "poster_url": f"{image_url}{p.get('poster_path')}" if p.get('poster_path') else "", "type": "movie"} for p in parts if p.get('poster_path')]}
        return data
    except requests.RequestException as e:
        print(f"Error fetching collection details for ID {collection_id}: {e}")
        return None


def get_series_details(series_id):
    """Fetches detailed series information from TMDB, including all episodes."""
    cache = data_manager.load_cache()
    entry = cache.get("series", {}).get(str(series_id))
    if entry and entry.get("has_season_data") and 'trailer_key' in entry and 'watch_providers' in entry and 'creator' in entry:
        return entry

    api_key = current_app.config['TMDB_API_KEY']
    if not api_key or api_key == "YOUR_API_KEY_HERE": return None

    try:
        url = f"{current_app.config['TMDB_BASE_URL']}/tv/{series_id}?api_key={api_key}&append_to_response=aggregate_credits,recommendations,videos,watch/providers"
        res = requests.get(url)
        res.raise_for_status()
        d = res.json()
        image_url = current_app.config['TMDB_IMAGE_URL']
        creator = ", ".join([c['name'] for c in d.get("created_by", [])])

        data = {"id": d.get("id"), "title": d.get("name"), "year": d.get("first_air_date", "")[:4], "poster_url": f"{image_url}{d.get('poster_path')}" if d.get('poster_path') else "", "genre": ", ".join([g['name'] for g in d.get("genres", [])]),
            "actors": ", ".join([c['name'] for c in d.get("aggregate_credits", {}).get("cast", [])[:5]]), "creator": creator, "plot": d.get("overview"), "number_of_seasons": d.get('number_of_seasons'), "number_of_episodes": d.get('number_of_episodes'), "seasons": [],
            "total_episode_count": 0, "has_season_data": True, 'trailer_key': find_trailer_key(d.get("videos", {}).get("results", [])),
            'recommendations': [{"id": r.get("id"), "title": r.get("name"), "type": "series", "poster_url": f"{image_url}{r.get('poster_path')}", "year": r.get("first_air_date", "")[:4], } for r in d.get("recommendations", {}).get("results", []) if
                                   r.get('poster_path')][:12]}

        providers = d.get('watch/providers', {}).get('results', {}).get('AT', {})
        data['watch_providers'] = {'link': providers.get('link', ''),
            'flatrate': sorted([{'name': p.get('provider_name'), 'logo_url': f"{image_url}{p.get('logo_path')}"} for p in providers.get('flatrate', []) if p.get('logo_path')], key=lambda x: x.get('display_priority', 99))}

        # Fetch episodes for each season
        for season_sum in d.get('seasons', []):
            s_num = season_sum.get('season_number')
            try:
                s_res = requests.get(f"{current_app.config['TMDB_BASE_URL']}/tv/{series_id}/season/{s_num}?api_key={api_key}")
                s_res.raise_for_status()
                s_d = s_res.json()
                eps = s_d.get('episodes', [])
                data["seasons"].append({"season_number": s_d.get("season_number"), "name": s_d.get("name"), "episode_count": len(eps),
                    "episodes": [{"episode_number": ep.get("episode_number"), "name": ep.get("name"), "id": f"s{s_num:02d}e{ep.get('episode_number'):02d}", "runtime": ep.get('runtime')} for ep in eps]})
                data["total_episode_count"] += len(eps)
            except requests.RequestException:
                continue

        cache["series"][str(series_id)] = data
        data_manager.save_cache(cache)
        return data
    except requests.RequestException as e:
        print(f"Error fetching series details for ID {series_id}: {e}")
        return None

def get_available_providers(region='AT'):
    """Fetches a combined list of movie and TV watch providers for a given region."""
    cache = data_manager.load_cache()
    if 'providers_cache' in cache and region in cache['providers_cache']:
        return cache['providers_cache'][region]

    api_key = current_app.config['TMDB_API_KEY']
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        return []

    all_providers = {}
    image_url = current_app.config['TMDB_IMAGE_URL']

    for provider_type in ['movie', 'tv']:
        try:
            url = f"{current_app.config['TMDB_BASE_URL']}/watch/providers/{provider_type}?api_key={api_key}&watch_region={region}"
            res = requests.get(url)
            res.raise_for_status()
            data = res.json()
            for provider in data.get('results', []):
                provider_id = provider.get('provider_id')
                if provider_id not in all_providers and provider.get('logo_path'):
                    all_providers[provider_id] = {
                        'id': provider_id,
                        'name': provider.get('provider_name'),
                        'logo_url': f"{image_url}{provider.get('logo_path')}"
                    }
        except requests.RequestException as e:
            print(f"Error fetching {provider_type} providers for region {region}: {e}")
            continue

    sorted_providers = sorted(all_providers.values(), key=lambda x: x['name'].lower())

    if 'providers_cache' not in cache:
        cache['providers_cache'] = {}
    cache['providers_cache'][region] = sorted_providers
    data_manager.save_cache(cache)

    return sorted_providers