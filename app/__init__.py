from flask import Flask
from flask_bootstrap import Bootstrap
from flask_cors import CORS
from flask_mail import Mail
from flask_moment import Moment
from flask_pagedown import PageDown
from flask_sqlalchemy import SQLAlchemy
from config import config
import os
from firebase_admin import initialize_app
from firebase_admin import credentials
import pymysql
pymysql.install_as_MySQLdb()

bootstrap = Bootstrap()
mail = Mail()
moment = Moment()
db = SQLAlchemy()
pagedown = PageDown()
cred = credentials.Certificate(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    CORS(app)

    bootstrap.init_app(app)
    mail.init_app(app)
    moment.init_app(app)
    db.init_app(app)
    pagedown.init_app(app)
    initialize_app(cred)

    if app.config['SSL_REDIRECT']:
        from flask_sslify import SSLify
        SSLify(app)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')

    return app
