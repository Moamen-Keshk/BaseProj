from flask import Flask
from flask_bootstrap import Bootstrap
from flask_cors import CORS
from flask_mail import Mail
from flask_moment import Moment
from flask_pagedown import PageDown
from flask_sqlalchemy import SQLAlchemy
from config import config
import os
from firebase_admin import initialize_app, get_app
from firebase_admin import credentials
import pymysql
from flask_socketio import SocketIO

pymysql.install_as_MySQLdb()

bootstrap = Bootstrap()
mail = Mail()
moment = Moment()
db = SQLAlchemy()
pagedown = PageDown()
socketio = SocketIO(
    message_queue='redis://localhost:6379/0',
    cors_allowed_origins="*",
    async_mode='threading'  # 👉 Force standard threading
)


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    firebase_cert_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')

    if firebase_cert_path and os.path.exists(firebase_cert_path):
        try:
            get_app()
        except ValueError:
            initialize_app(credentials.Certificate(firebase_cert_path))
    else:
        print(
            "⚠️ WARNING: GOOGLE_APPLICATION_CREDENTIALS not found or invalid. Firebase Admin SDK will not be initialized.")

    # 1. Standard CORS
    CORS(app, resources={r"/*": {"origins": "*"}})

    bootstrap.init_app(app)
    mail.init_app(app)
    moment.init_app(app)
    db.init_app(app)
    pagedown.init_app(app)
    socketio.init_app(app)

    if app.config['SSL_REDIRECT']:
        from flask_sslify import SSLify
        SSLify(app)

    # 3. Register Blueprints
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')


    from .api.channel_manager import channel_manager as channel_manager_blueprint
    app.register_blueprint(channel_manager_blueprint, url_prefix='/channel_manager')

    from .api.payments import payments_bp as payments_blueprint
    app.register_blueprint(payments_blueprint, url_prefix='/payments')

    return app
