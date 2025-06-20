import os
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, flash
from jinja2 import DictLoader
from datetime import datetime
from collections import Counter
import webbrowser
import threading
import random
import uuid

# --- API Configuration ---
TMDB_API_KEY = "YOUR_API_KEY_HERE"  # <--- IMPORTANT! PASTE YOUR KEY HERE
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# --- Application Setup ---
app = Flask(__name__)
app.secret_key = 'a_new_supersecretkey_for_flashing'


# --- Custom Jinja Filter ---
def format_runtime(minutes):
    if not minutes: return ""
    try:
        minutes = int(minutes)
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0: return f"{hours}h {mins}m"
        return f"{mins}m"
    except (ValueError, TypeError):
        return ""


app.jinja_env.filters['format_runtime'] = format_runtime

# --- HTML Templates ---
LAYOUT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Watchlist</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #111827; color: #d1d5db; }
        .card { background-color: #1f2937; border: 1px solid #374151; }
        .btn {
            background-color: #3b82f6; color: white; padding: 0.75rem 1.5rem; border-radius: 0.5rem;
            font-weight: 600; text-align: center; transition: background-color 0.2s; display: inline-block;
        }
        .btn:hover { background-color: #2563eb; }
        .btn-secondary { background-color: #4f46e5; }
        .btn-secondary:hover { background-color: #4338ca; }
        .btn-danger { background-color: #dc2626; }
        .btn-danger:hover { background-color: #b91c1c; }
        .nav-link { color: #9ca3af; transition: color 0.2s; }
        .nav-link:hover, .nav-link.active { color: white; }
        .rating-star { color: #f59e0b; }
        .alert { padding: 1rem; margin-bottom: 1rem; border-radius: 0.5rem; }
        .alert-error { background-color: #991b1b; color: #fecaca; }
        .alert-success { background-color: #166534; color: #bbf7d0; }
        .alert-info { background-color: #1e3a8a; color: #bfdbfe; }

        summary { list-style: none; cursor: pointer; }
        summary::-webkit-details-marker { display: none; }
        summary:focus-visible { outline: 2px solid #3b82f6; outline-offset: 4px; border-radius: 4px; }
        .disclosure-arrow { transition: transform 0.2s; display: inline-block; }
        details[open] > summary .disclosure-arrow { transform: rotate(0deg); }
        details:not([open]) > summary .disclosure-arrow { transform: rotate(-90deg); }
        details[open] > summary ~ * { animation: sweep 0.4s ease-in-out; }
        @keyframes sweep {
            0% { opacity: 0; transform: translateY(-1rem); }
            100% { opacity: 1; transform: translateY(0); }
        }

        .rating-group { display: flex; flex-direction: row-reverse; justify-content: center; align-items: center; }
        .rating-group input { display: none; }
        .rating-group label { cursor: pointer; padding: 0.5rem; border-radius: 0.375rem; transition: background-color 0.2s; }
        .rating-group label:hover { background-color: #4b5563; }
        .rating-group label .star { font-size: 1.875rem; line-height: 2.25rem; color: #4b5563; transition: color 0.2s; }
        .rating-group label .rating-number { font-size: 0.75rem; line-height: 1rem; color: #9ca3af; }
        .rating-group input:checked ~ label .star,
        .rating-group:hover label:hover ~ label .star,
        .rating-group:hover label:hover .star { color: #f59e0b; }
        .rating-group input:checked + label .rating-number { color: white; }

        .tab-btn {
            padding: 0.5rem 1rem; border-radius: 0.375rem; font-weight: 500;
            color: #9ca3af; transition: all 0.2s; border: 2px solid transparent;
        }
        .tab-btn.active, .tab-btn:hover { background-color: #374151; color: white; }
        .tab-btn.active { border-color: #3b82f6; }

        .details-scroll::-webkit-scrollbar { width: 8px; }
        .details-scroll::-webkit-scrollbar-track { background: #1f2937; }
        .details-scroll::-webkit-scrollbar-thumb { background-color: #4b5563; border-radius: 4px; border: 2px solid #1f2937; }
        .details-scroll::-webkit-scrollbar-thumb:hover { background-color: #6b7280; }
        .details-scroll { scrollbar-width: thin; scrollbar-color: #4b5563 #1f2937; }

        .aspect-w-16 { position: relative; padding-bottom: 56.25%; }
        .aspect-h-9 { height: 0; }
        .aspect-w-16 > * { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
    </style>
    <link rel="stylesheet" href="https://rsms.me/inter/inter.css">
</head>
<body class="min-h-screen">
    <nav class="bg-gray-900 p-4 shadow-lg sticky top-0 z-50">
        <div class="container mx-auto flex justify-between items-center">
            <div class="flex items-center space-x-8">
                 <a href="/" class="text-2xl font-bold text-white">My Watchlist</a>
                 <div class="hidden md:flex items-center space-x-2">
                    <a href="{{ url_for('index') }}" class="nav-link text-lg px-3 {% if request.path == url_for('index') %}active{% endif %}">Home</a>
                    <a href="{{ url_for('movies') }}" class="nav-link text-lg px-3 {% if request.path == url_for('movies') %}active{% endif %}">Movies</a>
                    <a href="{{ url_for('series') }}" class="nav-link text-lg px-3 {% if request.path == url_for('series') %}active{% endif %}">Series</a>
                    <a href="{{ url_for('stats') }}" class="nav-link text-lg px-3 {% if request.path == url_for('stats') %}active{% endif %}">Statistics</a>
                 </div>
            </div>
            <div class="w-full max-w-xs">
                <form action="{{ url_for('search') }}" method="post" class="relative">
                    <input type="search" name="query" placeholder="Search to add movies & series..." class="w-full bg-gray-700 border border-gray-600 rounded-lg py-2 px-4 text-white focus:ring-blue-500 focus:border-blue-500" required>
                    <button type="submit" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    </button>
                </form>
            </div>
        </div>
    </nav>
    <main class="container mx-auto p-4 md:p-8">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    <footer class="text-center p-4 text-gray-500 text-sm">
        <p>Movie Tracker App © 2025</p>
    </footer>
    <script>
        function showTab(section, type, clickedButton) {
            const contentPanels = document.querySelectorAll(`div[id^="${section}-"][class~="tab-content"]`);
            contentPanels.forEach(panel => { panel.style.display = 'none'; });
            const activePanel = document.getElementById(`${section}-${type}-content`);
            if (activePanel) { activePanel.style.display = 'block'; }
            const tabButtons = clickedButton.parentElement.querySelectorAll('.tab-btn');
            tabButtons.forEach(button => { button.classList.remove('active'); });
            clickedButton.classList.add('active');
        }
    </script>
</body>
</html>
"""
INDEX_HTML = """
{% extends 'layout.html' %}
{% block content %}
<div class="text-center">
    <h1 class="text-4xl md:text-5xl font-extrabold mb-4">Welcome to Your Watchlist</h1>
    <p class="text-lg text-gray-400 mb-12">Select a category to view your collection or use the search bar to add something new.</p>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
        <a href="{{ url_for('movies') }}" class="card p-10 rounded-lg text-center transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl hover:border-blue-500">
            <h2 class="text-3xl font-bold text-blue-400">Movies Collection</h2>
            <p class="mt-2 text-gray-400">View your 'Plan to Watch' and 'Watched' movies.</p>
        </a>
        <a href="{{ url_for('series') }}" class="card p-10 rounded-lg text-center transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl hover:border-purple-500">
            <h2 class="text-3xl font-bold text-purple-400">Series Collection</h2>
            <p class="mt-2 text-gray-400">Track your watched episodes and series progress.</p>
        </a>
    </div>
</div>

<div class="mt-20 text-left">
    <div class="flex flex-wrap items-end justify-between border-b-2 border-gray-700 pb-2 mb-8 gap-4">
        <h2 class="text-3xl font-bold">From Your 'Plan to Watch' List</h2>
        <div id="planned-tabs" class="flex-shrink-0 flex space-x-1 rounded-lg bg-gray-800 p-1">
            <button class="tab-btn active" onclick="showTab('planned', 'movie', this)">Movies</button>
            <button class="tab-btn" onclick="showTab('planned', 'series', this)">Series</button>
        </div>
    </div>
    <div id="planned-movie-content" class="tab-content">
        {% if planned_movie_suggestions %}
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
            {% for item in planned_movie_suggestions %}
            <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}" class="card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl">
                <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
                <div class="p-4"><h3 class="font-bold text-lg truncate">{{ item.title }}</h3><p class="text-sm text-gray-400">{{ item.year }}</p></div>
            </a>
            {% endfor %}
        </div>
        {% else %}<p class="text-gray-400">No movie suggestions from your 'Plan to Watch' list.</p>{% endif %}
    </div>
    <div id="planned-series-content" class="tab-content" style="display: none;">
        {% if planned_series_suggestions %}
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
            {% for item in planned_series_suggestions %}
            <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}" class="card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl">
                <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
                <div class="p-4"><h3 class="font-bold text-lg truncate">{{ item.title }}</h3><p class="text-sm text-gray-400">{{ item.year }}</p></div>
            </a>
            {% endfor %}
        </div>
        {% else %}<p class="text-gray-400">No series suggestions from your 'Plan to Watch' list.</p>{% endif %}
    </div>
</div>

<div class="mt-20 text-left">
    <div class="flex flex-wrap items-end justify-between border-b-2 border-gray-700 pb-2 mb-8 gap-4">
        <h2 class="text-3xl font-bold">You Might Like These</h2>
        <div id="smart-tabs" class="flex-shrink-0 flex space-x-1 rounded-lg bg-gray-800 p-1">
            <button class="tab-btn active" onclick="showTab('smart', 'movie', this)">Movies</button>
            <button class="tab-btn" onclick="showTab('smart', 'series', this)">Series</button>
        </div>
    </div>
    <div id="smart-movie-content" class="tab-content">
        {% if smart_movie_suggestions %}
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
            {% for item in smart_movie_suggestions %}
            <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}" class="card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl">
                <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
                <div class="p-4"><h3 class="font-bold text-lg truncate">{{ item.title }}</h3><p class="text-sm text-gray-400">{{ item.year }}</p></div>
            </a>
            {% endfor %}
        </div>
        {% else %}<p class="text-gray-400">Watch some movies to get personalized suggestions!</p>{% endif %}
    </div>
    <div id="smart-series-content" class="tab-content" style="display: none;">
        {% if smart_series_suggestions %}
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
            {% for item in smart_series_suggestions %}
            <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}" class="card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl">
                <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
                <div class="p-4"><h3 class="font-bold text-lg truncate">{{ item.title }}</h3><p class="text-sm text-gray-400">{{ item.year }}</p></div>
            </a>
            {% endfor %}
        </div>
        {% else %}<p class="text-gray-400">Watch some series to get personalized suggestions!</p>{% endif %}
    </div>
</div>
{% endblock %}
"""
ITEMS_LIST_HTML = """
{% extends 'layout.html' %}
{% block content %}
<details id="planned-section" class="mb-8" open>
    <summary class="text-3xl font-bold border-b-2 {% if item_type == 'movies' %}border-blue-500{% else %}border-purple-500{% endif %} pb-2 mb-6 flex items-center justify-between">
        <span>Plan to Watch ({{ planned_items|length }})</span>
        <span class="disclosure-arrow text-gray-400 text-2xl">▼</span>
    </summary>
    <div class="pt-2">
        {% if planned_items %}
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
            {% for item in planned_items %}
            <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}"
               class="item-card card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl">
                <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
                <div class="p-4">
                    <h3 class="font-bold text-lg truncate">{{ item.title }}</h3>
                    <p class="text-sm text-gray-400">{{ item.year }}</p>
                </div>
            </a>
            {% endfor %}
        </div>
        {% else %}
        <p class="text-gray-400 pt-4">You haven't planned to watch any {{ item_type }} yet.</p>
        {% endif %}
    </div>
</details>

<details id="watched-section" class="mb-8" open>
    <summary class="text-3xl font-bold border-b-2 {% if item_type == 'movies' %}border-blue-500{% else %}border-purple-500{% endif %} pb-2 mb-6 flex items-center justify-between">
        {% if item_type == 'movies' %}
            <span>Watched ({{ watched_items|length }})</span>
        {% else %}
            <span>In Progress & Watched ({{ watched_items|length }})</span>
        {% endif %}
        <span class="disclosure-arrow text-gray-400 text-2xl">▼</span>
    </summary>
    <div class="pt-2">
        {% if watched_items %}
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
            {% for item in watched_items %}
            <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}"
               class="item-card card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl relative">

                {% if item.type == 'movie' and item.get('watch_count', 0) > 1 %}
                <div class="absolute top-2 right-2 z-10 bg-blue-600 text-white text-xs font-bold px-2 py-1 rounded-full shadow-lg">
                    Watched x{{ item.watch_count }}
                </div>
                {% elif item.type == 'series' %}
                <div class="absolute top-0 left-0 right-0 z-10 bg-black bg-opacity-60 text-white text-xs font-bold p-1 text-center">
                    {% if item.status == 'Completed' %}
                        <span class="text-green-400">✔</span> Completed
                    {% else %}
                        {{ item.watched_episode_count }} / {{ item.total_episode_count }} Episodes
                    {% endif %}
                </div>
                {% endif %}

                <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
                <div class="p-4">
                    <h3 class="font-bold text-lg truncate">{{ item.title }}</h3>
                    <p class="text-sm text-gray-400">
                        Last watched: {{ item.get('last_watched_on') or item.get('watched_on', 'N/A') }}
                    </p>
                    <div class="flex items-center mt-2">
                        {% set rating = item.get('rating')|int if item.get('rating') else 0 %}
                        {% for i in range(rating) %}<span class="rating-star">★</span>{% endfor %}{% for i in range(5 - rating) %}<span class="text-gray-600">★</span>{% endfor %}
                    </div>
                </div>
            </a>
            {% endfor %}
        </div>
        {% else %}
        <p class="text-gray-400 pt-4">You haven't marked any {{ item_type }} as watched yet.</p>
        {% endif %}
    </div>
</details>
{% endblock %}
"""
SEARCH_RESULTS_HTML = """
{% extends 'layout.html' %}
{% block content %}
<h2 class="text-3xl font-bold mb-6">Search Results for "{{ query }}"</h2>
{% if results %}
<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
    {% for item in results %}
    <div class="card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl relative">
        <a href="{{ url_for('item_detail', item_type=item.type, item_id=item.id) }}" class="absolute inset-0 z-10"></a>
        <div class="relative">
            {% if item.status == 'planned' %}
                <div class="absolute top-2 right-2 z-20" title="In Plan to Watch">
                    <div class="bg-blue-600 bg-opacity-80 rounded-full p-2 flex items-center justify-center">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="white" stroke="white" stroke-width="1"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                    </div>
                </div>
            {% elif item.status == 'watched' %}
                <div class="absolute top-2 right-2 z-20" title="Already Watched or In Progress">
                    <div class="bg-green-600 bg-opacity-80 rounded-full p-2 flex items-center justify-center">
                         <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                    </div>
                </div>
            {% else %}
                <form action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=url_for('show_search_results', q=query)) }}" method="POST" class="absolute top-2 right-2 z-20">
                     <input type="hidden" name="action" value="plan">
                     <button type="submit" title="Add to Plan to Watch" class="bg-black bg-opacity-50 hover:bg-opacity-75 rounded-full p-2 transition-all">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="white" stroke="black" stroke-width="1"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                     </button>
                </form>
            {% endif %}
            <div class="absolute top-2 left-2 z-20 rounded-full px-2 py-1 text-xs font-bold {% if item.type == 'movie' %} bg-blue-600 text-white {% else %} bg-purple-600 text-white {% endif %}">
                {{ item.type|capitalize }}
            </div>
            <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text={{ item.title|replace(' ', '+') }}';" class="w-full h-auto object-cover aspect-[2/3]">
            <div class="p-4">
                <h3 class="font-bold text-lg truncate">{{ item.title }}</h3>
                <p class="text-sm text-gray-400">{{ item.year }}</p>
            </div>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="text-center card p-8">
    <h3 class="text-2xl font-bold">No results found for "{{ query }}"</h3>
    <p class="text-gray-400 mt-2">Please try a different search term.</p>
    <a href="{{ url_for('index') }}" class="btn mt-6">Back to Home</a>
</div>
{% endif %}
{% endblock %}
"""
DETAIL_HTML = """
{% extends 'layout.html' %}
{% block content %}
<div class="mb-6">
    <a href="{{ origin or url_for(internal_type) }}" class="inline-flex items-center text-gray-400 hover:text-white transition-colors group">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2 h-5 w-5 transform group-hover:-translate-x-1 transition-transform"><path d="M19 12H5"></path><polyline points="12 19 5 12 12 5"></polyline></svg>
        Back to {{ internal_type|capitalize }}
    </a>
</div>
<div class="card rounded-lg overflow-hidden">
    <div class="md:flex">
        <div class="md:w-2/5 md:max-w-sm flex-shrink-0 bg-gray-800 p-6 flex flex-col">
            <img src="{{ item.poster_url }}" alt="Poster for {{ item.title }}" class="w-full h-auto object-cover rounded-md shadow-lg" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';">
        </div>

        <div class="p-6 md:p-8 flex flex-col flex-grow">
            <div class="flex justify-between items-start gap-4">
                <h2 class="text-4xl font-bold text-white flex-grow">{{ item.title }}</h2>

                <div class="flex items-center flex-shrink-0 gap-x-2">
                    {% if item.trailer_key %}
                    <button id="open-trailer-modal" class="btn !bg-gray-700 hover:!bg-gray-600 flex items-center justify-center gap-2 !py-2 !px-3" title="Watch Trailer">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                        <span class="text-sm font-semibold">Trailer</span>
                    </button>
                    {% endif %}

                    <form method="POST" action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=origin) }}" class="flex">
                        {% if is_planned %}
                            <input type="hidden" name="action" value="remove_plan">
                            <button type="submit" class="btn !bg-blue-600 hover:!bg-blue-500 flex-shrink-0 flex items-center !py-2 !px-3" title="In 'Plan to Watch'. Click to remove.">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                            </button>
                        {% else %}
                             <input type="hidden" name="action" value="plan">
                             <button type="submit" class="btn !bg-gray-700 hover:!bg-gray-600 flex-shrink-0 flex items-center !py-2 !px-3" title="Add to 'Plan to Watch'">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                             </button>
                        {% endif %}
                    </form>

                    {% if is_watched or is_planned %}
                    <form method="POST" action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=origin) }}" class="flex" onsubmit="return confirm('Are you sure you want to delete this item AND all its history? This action cannot be undone.');">
                        <input type="hidden" name="action" value="delete_all">
                        <button type="submit" class="btn btn-danger flex-shrink-0 flex items-center !py-2 !px-3" title="Delete all records for this item">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"><path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                        </button>
                    </form>
                    {% endif %}
                </div>
            </div>

            <p class="text-lg text-gray-400 my-2">
                {{ item.year }}
                {% if item.type == 'movie' and item.runtime %}• {{ item.runtime|format_runtime }}{% endif %}
                {% if item.type == 'series' and item.number_of_seasons %}• {{ item.number_of_seasons }} Seasons{% endif %}
                {% if item.type == 'series' and item.number_of_episodes %}({{ item.number_of_episodes }} Episodes){% endif %}
                 • {{ item.genre }}
            </p>

            <div class="space-y-4 my-4">
                <p><strong class="font-semibold text-gray-300">Main Actors:</strong> <span class="text-gray-400">{{ item.actors }}</span></p>
                <p><strong class="font-semibold text-gray-300">Plot:</strong> <span class="text-gray-400 mt-1">{{ item.plot }}</span></p>
            </div>

            {% if item.watch_providers and item.watch_providers.flatrate %}
            <div class="my-4">
                <p class="font-semibold text-gray-300">Available to stream on:</p>
                <a href="{{ item.watch_providers.link }}" target="_blank" rel="noopener noreferrer" class="block mt-2 p-3 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors" title="See all streaming options">
                    <div class="flex items-center gap-4 flex-wrap">
                        {% for provider in item.watch_providers.flatrate %}
                            <img src="{{ provider.logo_url }}" alt="{{ provider.name }}" title="{{ provider.name }}" class="h-10 w-10 rounded-md object-cover">
                        {% endfor %}
                        <span class="text-sm text-gray-400 ml-auto flex-shrink-0 group-hover:text-white">View all options →</span>
                    </div>
                </a>
            </div>
            {% endif %}

            {% if item.type == 'movie' %}
                <div class="flex-grow flex flex-col mt-4">
                    <div class="flex-grow">
                    {% if watch_history %}
                    <details class="space-y-4 mb-4" open>
                        <summary class="text-xl font-bold text-white border-b border-gray-600 pb-2 flex items-center justify-between">Watch History</summary>
                        <div class="pt-3 space-y-3">
                            {% for watch in watch_history %}
                            <div class="flex items-center justify-between gap-x-4 p-3 bg-gray-800 rounded-lg">
                                <div class="flex items-center gap-x-3">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-gray-400 flex-shrink-0"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                                    <p class="text-sm text-gray-200">Watched on <strong class="font-semibold text-white">{{ watch.watched_on }}</strong></p>
                                </div>
                                <div class="flex items-center gap-x-4">
                                    <div class="flex-shrink-0 rating-star">{{ '★' * watch.rating }}<span class="text-gray-600">{{ '★' * (5 - watch.rating) }}</span></div>
                                    <form action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=origin) }}" method="POST" onsubmit="return confirm('Delete this watch record?');">
                                        <input type="hidden" name="action" value="delete_watch_instance"><input type="hidden" name="watch_id" value="{{ watch.watch_id }}">
                                        <button type="submit" title="Delete record" class="bg-red-800 hover:bg-red-700 text-white p-2 rounded-full transition-colors"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"><path fill="currentColor" d="M19 6.41L17.59 5L12 10.59L6.41 5L5 6.41L10.59 12L5 17.59L6.41 19L12 13.41L17.59 19L19 17.59L13.41 12L19 6.41z"/></svg></button>
                                    </form>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </details>
                    {% endif %}
                    </div>
                    <form method="POST" action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=origin) }}" class="space-y-4 border-2 border-gray-600 rounded-lg p-4 bg-gray-800 mt-auto">
                         <input type="hidden" name="action" value="watch">
                        <h3 class="font-bold text-lg text-center text-white">{% if is_watched %}Add New Watch Record{% else %}I've Watched This{% endif %}</h3>
                        <div><label for="watched_on" class="block text-sm font-medium text-gray-300 mb-1">Watched On</label><input type="date" name="watched_on" required value="{{ today }}" class="w-full bg-gray-700 border-gray-600 rounded-lg p-2 text-white" style="color-scheme: dark;"></div>
                        <div><label class="block text-sm font-medium text-gray-300 mb-2">Your Rating</label><div class="bg-gray-700 rounded-lg p-2"><div class="rating-group">
                            {% for i in range(5, 0, -1) %}<input type="radio" id="rating-{{ i }}" name="rating" value="{{ i }}" required><label for="rating-{{ i }}"><span class="star">★</span><span class="rating-number">{{ i }}</span></label>{% endfor %}
                        </div></div></div>
                        <button type="submit" class="w-full btn !py-2">{% if is_watched %}Add Watch Record{% else %}Add to 'Watched'{% endif %}</button>
                    </form>
                </div>
            {% endif %}
        </div>
    </div>

    {% if item.type == 'series' %}
    <div class="p-4 md:p-6 border-t-2 border-gray-700">
        <div class="flex items-start justify-between gap-4 mb-4">
             <div class="flex-grow">
                <h2 class="text-2xl font-bold">Episode Tracker</h2>
                {% set watched_count = watched_episode_ids|length %}{% set total_count = item.total_episode_count %}
                {% if total_count > 0 %}{% set progress_percent = (watched_count / total_count * 100)|round %}<div class="w-full bg-gray-700 rounded-full h-2.5 mt-2"><div class="bg-blue-600 h-2.5 rounded-full" style="width: {{ progress_percent }}%"></div></div><p class="text-sm text-gray-400 mt-1">{{ watched_count }} of {{ total_count }} episodes watched.</p>{% endif %}
            </div>
            <form method="POST" action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=origin) }}" class="space-y-2 border border-gray-600 rounded-lg p-2 bg-gray-800 flex-shrink-0">
                <input type="hidden" name="action" value="rate_series"><h3 class="font-bold text-sm text-center text-white">Rate This Series</h3><div class="bg-gray-700 rounded-lg"><div class="rating-group !justify-around">
                    {% set current_rating = watched_series_data.get('rating')|int if watched_series_data else 0 %}
                    {% for i in range(5, 0, -1) %}<input type="radio" id="rating-{{ i }}" name="rating" value="{{ i }}" required {% if i == current_rating %}checked{% endif %} onchange="this.form.submit()"><label for="rating-{{ i }}" class="!p-1"><span class="star !text-xl">★</span></label>{% endfor %}
                </div></div>
            </form>
        </div>
        <div class="space-y-2 max-h-[60vh] overflow-y-auto pr-2 details-scroll">
        {% for season in item.seasons %}{% if season.episodes %}{% set watched_in_season = season.episodes|selectattr('id', 'in', watched_episode_ids)|list %}<details class="bg-gray-800 rounded-lg" {% if season.season_number > 0 and (watched_in_season|length < season.episode_count or not watched_in_season) %}open{% endif %}><summary class="p-3 font-bold text-lg cursor-pointer flex justify-between items-center hover:bg-gray-700 rounded-t-lg transition-colors"><span>{{ season.name }} ({{ watched_in_season|length }} / {{ season.episode_count }})</span><span class="disclosure-arrow text-gray-400 text-2xl">▼</span></summary><div class="border-t border-gray-700 p-2 md:p-3 space-y-2">
            {% for episode in season.episodes %}<div class="flex items-center justify-between rounded-md p-1.5 {% if episode.id in watched_episode_ids %}bg-green-900/40{% else %}bg-gray-900/30{% endif %}"><div class="flex items-center gap-x-3"><span class="text-gray-400 font-mono text-xs sm:text-sm w-16 text-center">S{{ "%02d"|format(season.season_number) }}E{{ "%02d"|format(episode.episode_number) }}</span><div class="flex-grow"><p class="font-semibold text-sm">{{ episode.name }}</p></div></div><form method="POST" action="{{ url_for('item_detail_action', item_type=item.type, item_id=item.id, title=item.title, origin=origin) }}" class="ml-2"><input type="hidden" name="action" value="toggle_episode"><input type="hidden" name="episode_id" value="{{ episode.id }}"><input type="hidden" name="watched_on" value="{{ today }}"><button type="submit" class="btn !py-1 !px-2 text-xs whitespace-nowrap {% if episode.id in watched_episode_ids %}!bg-red-600 hover:!bg-red-700{% else %}!bg-blue-600 hover:!bg-blue-700{% endif %}">{% if episode.id in watched_episode_ids %}Unwatch{% else %}Watch{% endif %}</button></form></div>{% endfor %}
        </div></details>{% endif %}{% endfor %}
        </div>
    </div>
    {% endif %}
</div>

{% if item.recommendations %}
<div class="mt-12">
    <h2 class="text-3xl font-bold mb-6 text-white border-b-2 border-gray-700 pb-2">You Might Also Like</h2>
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6 pt-6">
        {% for rec in item.recommendations %}
        <a href="{{ url_for('item_detail', item_type=rec.type, item_id=rec.id) }}" class="card rounded-lg overflow-hidden transform hover:-translate-y-2 transition-transform duration-300 shadow-lg hover:shadow-2xl">
            <img src="{{ rec.poster_url }}" alt="Poster for {{ rec.title }}" onerror="this.onerror=null;this.src='https://placehold.co/500x750/1f2937/d1d5db?text=No+Image';" class="w-full h-auto object-cover aspect-[2/3]">
            <div class="p-4">
                <h3 class="font-bold text-lg truncate">{{ rec.title }}</h3>
                <p class="text-sm text-gray-400">{{ rec.year }}</p>
            </div>
        </a>
        {% endfor %}
    </div>
</div>
{% endif %}

{% if item.trailer_key %}
<div id="trailer-modal" class="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-[999] hidden p-4">
    <div class="bg-gray-900 p-2 md:p-4 rounded-lg shadow-2xl relative w-full max-w-4xl">
         <button id="close-trailer-modal" class="absolute -top-3 -right-3 text-white bg-red-600 rounded-full h-8 w-8 flex items-center justify-center text-2xl font-bold leading-none z-10" aria-label="Close trailer">×</button>
         <div class="aspect-w-16 aspect-h-9">
             <iframe id="trailer-iframe" src="https://www.youtube.com/embed/{{ item.trailer_key }}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
         </div>
    </div>
</div>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const openBtn = document.getElementById('open-trailer-modal');
        const closeBtn = document.getElementById('close-trailer-modal');
        const modal = document.getElementById('trailer-modal');
        const iframe = document.getElementById('trailer-iframe');

        if (!modal || !iframe) return;
        const originalSrc = iframe.src;

        const openModal = () => {
            modal.classList.remove('hidden');
            iframe.src = originalSrc + (originalSrc.includes('?') ? '&' : '?') + 'autoplay=1';
        };

        const closeModal = () => {
            modal.classList.add('hidden');
            iframe.src = originalSrc.split("?")[0];
        };

        if (openBtn) { openBtn.addEventListener('click', openModal); }
        if (closeBtn) { closeBtn.addEventListener('click', closeModal); }
        modal.addEventListener('click', (event) => { if (event.target === modal) { closeModal(); } });
        document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !modal.classList.contains('hidden')) { closeModal(); } });
    });
</script>
{% endif %}
{% endblock %}
"""
STATS_HTML = """
{% extends 'layout.html' %}
{% block content %}
<h1 class="text-4xl font-bold mb-8 text-center">Your Watchlist Statistics</h1>
<div class="grid grid-cols-1 md:grid-cols-3 gap-6 text-center mb-12">
    <div class="card p-6 rounded-lg"><h2 class="text-xl font-semibold text-gray-300">Unique Movies Watched</h2><p class="text-5xl font-bold text-blue-400 mt-2">{{ stats.total_movies }}</p></div>
    <div class="card p-6 rounded-lg"><h2 class="text-xl font-semibold text-gray-300">TV Episodes Watched</h2><p class="text-5xl font-bold text-purple-400 mt-2">{{ stats.total_episodes }}</p></div>
    <div class="card p-6 rounded-lg"><h2 class="text-xl font-semibold text-gray-300">Total Movie Viewings</h2><p class="text-5xl font-bold text-white mt-2">{{ stats.total_movie_watches }}</p></div>
</div>
<div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <div class="card p-6 rounded-lg">
        <h3 class="text-2xl font-bold mb-4">Ratings Distribution (All Items)</h3>
        {% if stats.total_items > 0 %}
        <div class="space-y-3">
            {% for rating, count in stats.ratings_dist.items() %}
            <div class="flex items-center"><div class="w-20 text-right mr-4"><span class="font-semibold">{{ '★' * rating }}</span></div><div class="flex-1 bg-gray-700 rounded-full h-6"><div class="bg-yellow-500 h-6 rounded-full text-right pr-2 text-black font-bold flex items-center justify-end" style="width: {{ (count / stats.total_items * 100)|round|int }}%;">{{ count }}</div></div></div>
            {% endfor %}
        </div>
        {% else %}<p class="text-gray-400">No rated items yet.</p>{% endif %}
    </div>
    <div class="card p-6 rounded-lg">
        <h3 class="text-2xl font-bold mb-4">Favorite Genres (From Watched Items)</h3>
        <div class="space-y-2">
            {% if stats.genre_dist %}{% for genre, count in stats.genre_dist %}<div class="flex justify-between items-center text-lg"><span>{{ genre }}</span><span class="font-bold bg-blue-500 text-white rounded-full px-3 py-1 text-sm">{{ count }}</span></div>{% endfor %}{% else %}<p class="text-gray-400">No items watched yet to calculate favorite genres.</p>{% endif %}
        </div>
    </div>
</div>
{% endblock %}
"""

app.jinja_loader = DictLoader({'layout.html': LAYOUT_HTML, 'index.html': INDEX_HTML, 'items_list.html': ITEMS_LIST_HTML, 'search_results.html': SEARCH_RESULTS_HTML, 'detail.html': DETAIL_HTML, 'stats.html': STATS_HTML})

# --- Data Storage and Migration ---
WATCHLIST_FILE = "watchlist.json"
CACHE_FILE = "metadata_cache.json"


def load_json_file(filename, default_data):
    if not os.path.exists(filename): return default_data
    try:
        with open(filename, "r", encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else default_data
    except (IOError, json.JSONDecodeError):
        return default_data


def save_json_file(filename, data):
    with open(filename, "w", encoding='utf-8') as f: json.dump(data, f, indent=4)


def migrate_watchlist_add_uuids_to_movies(watchlist):
    made_changes = False
    if 'movies' in watchlist.get('watched', {}) and isinstance(watchlist['watched']['movies'], list):
        for record in watchlist['watched']['movies']:
            if 'watch_id' not in record:
                record['watch_id'] = str(uuid.uuid4())
                made_changes = True
    return made_changes


def load_watchlist():
    default = {"watched": {"movies": [], "series": {}}, "planned": {"movies": [], "series": []}}
    watchlist = load_json_file(WATCHLIST_FILE, default)
    if migrate_watchlist_add_uuids_to_movies(watchlist):
        print("Migrating movie watchlist: Added unique IDs.")
        save_json_file(WATCHLIST_FILE, watchlist)
    if 'series' not in watchlist.get('watched', {}) or isinstance(watchlist['watched']['series'], list):
        print("Migrating series data to new episode-tracking format...")
        watchlist['watched']['series'] = {}
        save_json_file(WATCHLIST_FILE, watchlist)
        print("Series data migration complete.")
    return watchlist


def save_watchlist(data): save_json_file(WATCHLIST_FILE, data)


def load_cache(): return load_json_file(CACHE_FILE, {"movies": {}, "series": {}})


def save_cache(data): save_json_file(CACHE_FILE, data)


# --- API and Data Fetching ---
def find_trailer_key(videos_results):
    trailer, teaser = None, None
    for video in videos_results:
        if video.get('site') == 'YouTube':
            is_official_trailer = video.get('type') == 'Trailer' and video.get('official', False)
            if is_official_trailer: return video.get('key')
            if video.get('type') == 'Trailer' and not trailer: trailer = video.get('key')
            if video.get('type') == 'Teaser' and not teaser: teaser = video.get('key')
    return trailer or teaser


def get_movie_details(movie_id):
    cache = load_cache()
    cache_entry = cache.get("movies", {}).get(str(movie_id))
    if cache_entry and 'trailer_key' in cache_entry and 'watch_providers' in cache_entry: return cache_entry
    if not TMDB_API_KEY or TMDB_API_KEY == "YOUR_API_KEY_HERE": return None
    try:
        url = f"{TMDB_BASE_URL}/movie/{movie_id}?api_key={TMDB_API_KEY}&append_to_response=credits,recommendations,videos,watch/providers"
        res = requests.get(url)
        res.raise_for_status()
        d = res.json()
        data = {"id": d.get("id"), "title": d.get("title"), "poster_url": f"{TMDB_IMAGE_URL}{d.get('poster_path')}" if d.get('poster_path') else "", "genre": ", ".join([g['name'] for g in d.get("genres", [])]),
                "actors": ", ".join([c['name'] for c in d.get("credits", {}).get("cast", [])[:5]]), "plot": d.get("overview"), "year": d.get("release_date", "")[:4], "runtime": d.get('runtime')}

        recs = []
        for r in d.get("recommendations", {}).get("results", []):
            if r.get('poster_path') and r.get('id'):
                recs.append({"id": r.get("id"), "title": r.get("title"), "poster_url": f"{TMDB_IMAGE_URL}{r.get('poster_path')}", "year": r.get("release_date", "")[:4], "type": "movie"})
        data['recommendations'] = recs[:12]
        data['trailer_key'] = find_trailer_key(d.get("videos", {}).get("results", []))

        providers_data = d.get('watch/providers', {}).get('results', {}).get('AT')
        processed_providers = {'link': '', 'flatrate': []}
        if providers_data:
            processed_providers['link'] = providers_data.get('link', '')
            if 'flatrate' in providers_data:
                processed_providers['flatrate'] = sorted([{'name': p.get('provider_name'), 'logo_url': f"{TMDB_IMAGE_URL}{p.get('logo_path')}"} for p in providers_data['flatrate'] if p.get('logo_path')], key=lambda x: x.get('display_priority', 99))
        data['watch_providers'] = processed_providers

        cache["movies"][str(movie_id)] = data
        save_cache(cache)
        return data
    except requests.RequestException as e:
        print(f"Error fetching movie details for ID {movie_id}: {e}");
        return None


def get_series_details(series_id):
    cache = load_cache()
    entry = cache.get("series", {}).get(str(series_id))
    if entry and entry.get("has_season_data") and 'trailer_key' in entry and 'watch_providers' in entry: return entry
    if not TMDB_API_KEY or TMDB_API_KEY == "YOUR_API_KEY_HERE": return None
    try:
        url = f"{TMDB_BASE_URL}/tv/{series_id}?api_key={TMDB_API_KEY}&append_to_response=aggregate_credits,recommendations,videos,watch/providers"
        res = requests.get(url)
        res.raise_for_status()
        d = res.json()
        data = {"id": d.get("id"), "title": d.get("name"), "poster_url": f"{TMDB_IMAGE_URL}{d.get('poster_path')}" if d.get('poster_path') else "", "genre": ", ".join([g['name'] for g in d.get("genres", [])]),
                "actors": ", ".join([c['name'] for c in d.get("aggregate_credits", {}).get("cast", [])[:5]]), "plot": d.get("overview"), "year": d.get("first_air_date", "")[:4], "seasons": [], "total_episode_count": 0, "has_season_data": True,
                "number_of_seasons": d.get('number_of_seasons'), "number_of_episodes": d.get('number_of_episodes')}

        recs = []
        for r in d.get("recommendations", {}).get("results", []):
            if r.get('poster_path') and r.get('id'):
                recs.append({"id": r.get("id"), "title": r.get("name"), "poster_url": f"{TMDB_IMAGE_URL}{r.get('poster_path')}", "year": r.get("first_air_date", "")[:4], "type": "series"})
        data['recommendations'] = recs[:12]
        data['trailer_key'] = find_trailer_key(d.get("videos", {}).get("results", []))

        providers_data = d.get('watch/providers', {}).get('results', {}).get('AT')
        processed_providers = {'link': '', 'flatrate': []}
        if providers_data:
            processed_providers['link'] = providers_data.get('link', '')
            if 'flatrate' in providers_data:
                processed_providers['flatrate'] = sorted([{'name': p.get('provider_name'), 'logo_url': f"{TMDB_IMAGE_URL}{p.get('logo_path')}"} for p in providers_data['flatrate'] if p.get('logo_path')], key=lambda x: x.get('display_priority', 99))
        data['watch_providers'] = processed_providers

        for season_sum in d.get('seasons', []):
            s_num = season_sum.get('season_number')
            try:
                s_res = requests.get(f"{TMDB_BASE_URL}/tv/{series_id}/season/{s_num}?api_key={TMDB_API_KEY}")
                s_res.raise_for_status()
                s_d = s_res.json()
                s_obj = {"season_number": s_d.get("season_number"), "name": s_d.get("name"), "episodes": [], "episode_count": 0}
                eps = s_d.get('episodes', [])
                for ep in eps: s_obj["episodes"].append({"episode_number": ep.get("episode_number"), "name": ep.get("name"), "id": f"s{s_num:02d}e{ep.get('episode_number'):02d}"})
                s_obj["episode_count"] = len(eps)
                data["total_episode_count"] += len(eps)
                data["seasons"].append(s_obj)
            except requests.RequestException:
                continue
        cache["series"][str(series_id)] = data
        save_cache(cache)
        return data
    except requests.RequestException as e:
        print(f"Error fetching series details for ID {series_id}: {e}");
        return None


def sync_cache_with_watchlist():
    print("Syncing metadata cache with watchlist...")
    watchlist, cache, fetched = load_watchlist(), load_cache(), 0
    all_item_ids = {'movie': [], 'series': []}
    for m in watchlist['watched']['movies'] + watchlist['planned']['movies']: all_item_ids['movie'].append(str(m['id']))
    for s_id in list(watchlist['watched']['series'].keys()) + [str(s['id']) for s in watchlist['planned']['series']]: all_item_ids['series'].append(s_id)

    for mid in set(all_item_ids['movie']):
        if mid not in cache['movies'] or 'watch_providers' not in cache['movies'][mid]:
            if get_movie_details(int(mid)): fetched += 1
    for sid in set(all_item_ids['series']):
        if sid not in cache['series'] or 'watch_providers' not in cache['series'][sid]:
            if get_series_details(int(sid)): fetched += 1
    print(f"Sync complete. Fetched metadata for {fetched} item(s)." if fetched > 0 else "Cache is up to date.")


def get_smart_suggestions(item_type):
    watchlist, cache, today = load_watchlist(), load_cache(), datetime.now()
    singular = 'movie' if item_type == 'movies' else 'series'
    if item_type == 'movies':
        user_ids = {i['id'] for i in watchlist['watched']['movies']} | {i['id'] for i in watchlist['planned']['movies']}
        source_items = watchlist['watched']['movies']
    else:  # series
        user_ids = {int(id) for id in watchlist['watched']['series']} | {i['id'] for i in watchlist['planned']['series']}
        source_items = list(watchlist['watched']['series'].values())

    scores, data = {}, {}
    for item in source_items:
        id_str = str(item['id'])
        if id_str not in cache[item_type] or 'recommendations' not in cache[item_type][id_str]: continue
        rating = item.get('rating', 3)
        date_str = item.get('watched_on') if item_type == 'movies' else (max(e['watched_on'] for e in item['watched_episodes'].values()) if item.get('watched_episodes') else None)
        if not date_str: continue
        try:
            days = max(0, (today - datetime.strptime(date_str, '%Y-%m-%d')).days)
            score = (rating ** 2) * (0.98 ** days)
            for rec in cache[item_type][id_str].get('recommendations', []):
                if rec.get('id') and rec['id'] not in user_ids:
                    scores[rec['id']] = scores.get(rec['id'], 0) + score
                    if rec['id'] not in data: data[rec['id']] = {**rec, 'type': singular}
        except (ValueError, TypeError):
            continue
    return [data[id] for id, score in sorted(scores.items(), key=lambda i: i[1], reverse=True)[:12]]


# --- Flask Routes ---
@app.route('/')
def index():
    watchlist, cache = load_watchlist(), load_cache()
    p_movies, p_series = watchlist['planned']['movies'], watchlist['planned']['series']
    random.shuffle(p_movies);
    random.shuffle(p_series)
    p_movie_suggs = [{**cache['movies'][str(i['id'])], 'type': 'movie'} for i in p_movies[:6] if str(i['id']) in cache['movies']]
    p_series_suggs = [{**cache['series'][str(i['id'])], 'type': 'series'} for i in p_series[:6] if str(i['id']) in cache['series']]
    return render_template('index.html', planned_movie_suggestions=p_movie_suggs, planned_series_suggestions=p_series_suggs, smart_movie_suggestions=get_smart_suggestions('movies'), smart_series_suggestions=get_smart_suggestions('series'))


@app.route('/movies')
def movies():
    watchlist, cache = load_watchlist(), load_cache()
    watches = {}
    for watch in watchlist['watched']['movies']: watches.setdefault(watch['id'], []).append(watch)
    watched = sorted([({**cache['movies'][str(id)], **max(w, key=lambda x: x['watched_on']), 'watch_count': len(w), 'type': 'movie'}) for id, w in watches.items() if str(id) in cache['movies']], key=lambda x: x['watched_on'], reverse=True)
    planned = [{**cache['movies'][str(m['id'])], **m, 'type': 'movie'} for m in watchlist['planned']['movies'] if str(m['id']) in cache['movies']]
    return render_template('items_list.html', item_type='movies', watched_items=watched, planned_items=planned)


@app.route('/series')
def series():
    watchlist, cache = load_watchlist(), load_cache()
    watched = []
    for sid, sdata in watchlist['watched']['series'].items():
        if sid in cache['series']:
            details = cache['series'][sid]
            w_ep_c = len(sdata.get('watched_episodes', {}))
            t_ep_c = details.get('total_episode_count', 0)
            last_on = max(e['watched_on'] for e in sdata['watched_episodes'].values()) if sdata.get('watched_episodes') else 'N/A'
            status = 'Completed' if t_ep_c > 0 and w_ep_c == t_ep_c else 'In Progress'
            watched.append({**details, **sdata, 'type': 'series', 'watched_episode_count': w_ep_c, 'total_episode_count': t_ep_c, 'status': status, 'last_watched_on': last_on})
    watched.sort(key=lambda x: x['last_watched_on'], reverse=True)
    planned = [{**cache['series'][str(s['id'])], **s, 'type': 'series'} for s in watchlist['planned']['series'] if str(s['id']) in cache['series']]
    return render_template('items_list.html', item_type='series', watched_items=watched, planned_items=planned)


@app.route('/item/<item_type>/<int:item_id>')
def item_detail(item_type, item_id):
    internal_type = 'movies' if item_type == 'movie' else 'series'
    details_func = get_movie_details if item_type == 'movie' else get_series_details
    details = details_func(item_id)
    if not details:
        flash("Could not retrieve item details.", "error")
        return redirect(url_for(internal_type))

    watchlist = load_watchlist()
    today = datetime.now().strftime('%Y-%m-%d')
    item_to_show = {**details, 'type': item_type}
    origin = request.referrer or url_for(internal_type)

    if item_type == 'movie':
        watch_history = sorted([i for i in watchlist['watched']['movies'] if i.get('id') == item_id], key=lambda x: x['watched_on'], reverse=True)
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['movies'])
        is_watched = bool(watch_history)
        if is_watched: item_to_show.update(watch_history[0])
        return render_template('detail.html', item=item_to_show, is_planned=is_planned, is_watched=is_watched, today=today, origin=origin, watch_history=watch_history, internal_type=internal_type)
    else:  # series
        sdata = watchlist['watched']['series'].get(str(item_id))
        ep_ids = list(sdata['watched_episodes'].keys()) if sdata and 'watched_episodes' in sdata else []
        is_planned = any(i.get('id') == item_id for i in watchlist['planned']['series'])
        is_watched = bool(sdata)
        return render_template('detail.html', item=item_to_show, is_planned=is_planned, is_watched=is_watched, today=today, origin=origin, watched_series_data=sdata, watched_episode_ids=ep_ids, internal_type=internal_type)


@app.route('/item/<item_type>/<int:item_id>/action', methods=['POST'])
def item_detail_action(item_type, item_id):
    internal, watchlist = ('movies' if item_type == 'movie' else 'series'), load_watchlist()
    origin = request.args.get('origin', url_for(internal))
    action = request.form.get('action')
    title = request.args.get('title', 'The item')

    if action == 'plan':
        if not any(i.get('id') == item_id for i in watchlist['planned'][internal]):
            watchlist['planned'][internal].append({"id": item_id});
            save_watchlist(watchlist)
            flash(f"Added '{title}' to 'Plan to Watch'.", "success")
    elif action == 'remove_plan':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        save_watchlist(watchlist);
        flash(f"Removed '{title}' from 'Plan to Watch'.", "success")
    elif action == 'watch' and item_type == 'movie':
        watchlist['watched']['movies'].append({"id": item_id, "watch_id": str(uuid.uuid4()), "watched_on": request.form['watched_on'], "rating": int(request.form['rating'])})
        watchlist['planned']['movies'] = [i for i in watchlist['planned']['movies'] if i.get('id') != item_id]
        save_watchlist(watchlist);
        flash(f"Added watch record for '{title}'.", "success")
    elif action == 'delete_all':
        watchlist['planned'][internal] = [i for i in watchlist['planned'][internal] if i.get('id') != item_id]
        if item_type == 'movie':
            watchlist['watched']['movies'] = [i for i in watchlist['watched']['movies'] if i.get('id') != item_id]
        else:
            watchlist['watched']['series'].pop(str(item_id), None)
        save_watchlist(watchlist);
        flash(f"Deleted all records for '{title}'.", "success")
        return redirect(origin)
    elif action == 'delete_watch_instance' and item_type == 'movie':
        watchlist['watched']['movies'] = [w for w in watchlist['watched']['movies'] if w.get('watch_id') != request.form.get('watch_id')]
        save_watchlist(watchlist);
        flash("Watch record deleted.", "success")
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
        save_watchlist(watchlist)
    elif action == 'rate_series' and item_type == 'series':
        entry = watchlist['watched']['series'].setdefault(str(item_id), {"id": item_id, "watched_episodes": {}})
        entry['rating'] = int(request.form['rating'])
        save_watchlist(watchlist);
        flash(f"Rated '{title}'.", "success")

    return redirect(url_for('item_detail', item_type=item_type, item_id=item_id, origin=origin))


@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    return redirect(url_for('show_search_results', q=query) if query else url_for('index'))


@app.route('/search_results')
def show_search_results():
    query, results = request.args.get('q', ''), []
    if TMDB_API_KEY and TMDB_API_KEY != "YOUR_API_KEY_HERE":
        try:
            res = requests.get(f"{TMDB_BASE_URL}/search/multi?api_key={TMDB_API_KEY}&query={query}")
            res.raise_for_status()
            for item in res.json().get('results', []):
                if item.get('media_type') == 'movie' and item.get('poster_path'):
                    results.append({"id": item.get('id'), "title": item.get('title'), "year": item.get('release_date', '')[:4], "poster_url": f"{TMDB_IMAGE_URL}{item.get('poster_path')}", "type": "movie"})
                elif item.get('media_type') == 'tv' and item.get('poster_path'):
                    results.append({"id": item.get('id'), "title": item.get('name'), "year": item.get('first_air_date', '')[:4], "poster_url": f"{TMDB_IMAGE_URL}{item.get('poster_path')}", "type": "series"})
        except requests.RequestException as e:
            flash(f"API Error: {e}", "error")

    watchlist = load_watchlist()
    p_m_ids, w_m_ids = {i['id'] for i in watchlist['planned']['movies']}, {i['id'] for i in watchlist['watched']['movies']}
    p_s_ids, w_s_ids = {i['id'] for i in watchlist['planned']['series']}, {int(id) for id in watchlist['watched']['series']}
    for item in results:
        is_movie = item['type'] == 'movie'
        item['status'] = 'watched' if (is_movie and item['id'] in w_m_ids) or (not is_movie and item['id'] in w_s_ids) else 'planned' if (is_movie and item['id'] in p_m_ids) or (not is_movie and item['id'] in p_s_ids) else None
    return render_template('search_results.html', query=query, results=results)


@app.route('/stats')
def stats():
    watchlist, cache = load_watchlist(), load_cache()
    w_movies, w_series = watchlist['watched']['movies'], list(watchlist['watched']['series'].values())
    m_ratings = [i['rating'] for i in w_movies if 'rating' in i]
    s_ratings = [s['rating'] for s in w_series if 'rating' in s]
    all_ratings = m_ratings + s_ratings
    genres = []
    w_ids = {m['id'] for m in w_movies} | {s['id'] for s in w_series}
    for item_id in w_ids:
        meta = cache['movies'].get(str(item_id)) or cache['series'].get(str(item_id))
        if meta and meta.get('genre'): genres.extend([g.strip() for g in meta['genre'].split(',') if g.strip()])
    stats_data = {"total_movies": len({m['id'] for m in w_movies}), "total_movie_watches": len(w_movies), "total_episodes": sum(len(s.get('watched_episodes', {})) for s in w_series), "total_items": len(all_ratings),
                  "ratings_dist": dict(sorted(Counter(all_ratings).items(), key=lambda i: i[0], reverse=True)), "genre_dist": Counter(genres).most_common(10)}
    return render_template('stats.html', stats=stats_data)


# --- Main Execution ---
if __name__ == '__main__':
    url = "http://127.0.0.1:5000"
    print(f"Starting server, opening browser at {url}")
    if not TMDB_API_KEY or TMDB_API_KEY == "YOUR_API_KEY_HERE":
        print("\n" + "=" * 50 + "\nWARNING: TMDB_API_KEY is not set!\n" + "=" * 50 + "\n")

    load_watchlist()
    threading.Thread(target=sync_cache_with_watchlist, daemon=True).start()
    threading.Timer(1.25, lambda: webbrowser.open(url)).start()
    app.run(port=5000, debug=False)