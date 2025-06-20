# Watchlist App

A simple and modern web application built with Flask to track movies and TV series you plan to watch or have already watched. The app uses The Movie Database (TMDB) API to fetch details, posters, and recommendations.

## Features

-   **Track Movies & Series:** Maintain separate lists for "Plan to Watch" and "Watched".
-   **Detailed Information:** View posters, plots, ratings, runtime, actors, and more.
-   **Episode Tracking:** Mark individual episodes of a series as watched and track your progress.
-   **TMDB Integration:** Search for any movie or series to add to your lists.
-   **Smart Suggestions:** Get personalized recommendations based on your viewing history.
-   **Statistics:** See an overview of your watching habits, including favorite genres and rating distributions.
-   **Trailer Playback:** Watch movie and series trailers directly in the app.

## Tech Stack

-   **Backend:** Python 3, Flask
-   **Frontend:** HTML, Tailwind CSS, Vanilla JavaScript
-   **API:** The Movie Database (TMDB)
-   **Data Storage:** Local JSON files
-   **Dependencies:** Requests, python-dotenv

## Setup and Installation

Follow these steps to get the application running on your local machine.

### 1. Prerequisites

-   Python 3.8 or newer
-   A free API key from [The Movie Database (TMDB)](https://www.themoviedb.org/signup)

### 2. Clone the Repository

```bash
git clone https://github.com/Topfpflanze21/watchlist.git
cd Watchlist

# Create a virtual environment
python -m venv .venv
```

### 3. Create Virtual Environment and Install Dependencies

```bash
# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install the required packages
pip install -r requirements.txt
```

### 4. Configuration

The application requires an API key to function.  

1.  Create a file named `.env` in the root of the project directory.
2.  Add your `TMDB_API_KEY` and a secret key to this file. The `SECRET_KEY` can be any long, random string.

Your `.env` file should look like this:

```bash
# .env file

SECRET_KEY="your-super-random-and-secret-key-here"
TMDB_API_KEY="your-tmdb-api-key-goes-here"
```

### 5. Run the Application

Once the setup is complete, you can run the app with:

```bash
python run.py
```

The application will start, and a new tab should open in your web browser at http://127.0.0.1:5000.