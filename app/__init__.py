# /app/__init__.py
from flask import Flask
from config import Config

def create_app(config_class=Config):
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register the custom Jinja filter
    from . import utils
    app.jinja_env.filters['format_runtime'] = utils.format_runtime

    # Import and register the routes blueprint
    from . import routes
    app.register_blueprint(routes.bp)

    return app