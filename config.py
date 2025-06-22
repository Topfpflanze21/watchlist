# /config.py
import os
from dotenv import load_dotenv

# Load variables from .env file into environment
load_dotenv()

class Config:
    """Flask configuration variables."""
    # Security (reads from .env file, with a fallback)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-default-fallback-key'

    # TMDB API (reads from .env file)
    TMDB_API_KEY = os.environ.get('TMDB_API_KEY')

    TMDB_BASE_URL = "https://api.themoviedb.org/3"
    TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

    # Data Files
    WATCHLIST_FILE = "watchlist.json"
    CACHE_FILE = "metadata_cache.json"
    SUGGESTIONS_CACHE_FILE = "suggestions_cache.json"