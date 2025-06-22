# /app/__init__.py
from flask import Flask
from config import Config
from flask_login import LoginManager

# Create the login manager instance
login_manager = LoginManager()
login_manager.login_view = 'main.login' # The route to redirect to for login
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize the login manager with the app
    login_manager.init_app(app)

    # Register the user loader function
    from . import data_manager
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        user_data = data_manager.find_user_by_id(user_id)
        if user_data:
            return User(id=user_data['id'], username=user_data['username'], password_hash=user_data['password_hash'])
        return None

    from . import utils
    app.jinja_env.filters['format_runtime'] = utils.format_runtime

    from . import routes
    app.register_blueprint(routes.bp)

    return app