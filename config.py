import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "hard-to-guess-string"
    BCRYPT_LOG_ROUNDS = int(os.environ.get("BCRYPT_LOG_ROUNDS", 12))

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1"]
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ["true", "on", "1"]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    MAIL_SUBJECT_PREFIX = os.environ.get("MAIL_SUBJECT_PREFIX", "[PLS]")
    MAIL_SENDER = os.environ.get("MAIL_SENDER", "keshkmoamen89@gmail.com")
    ADMIN_EMAIL = os.environ.get("FLASKY_ADMIN")

    SSL_REDIRECT = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True

    POSTS_PER_PAGE = int(os.environ.get("POSTS_PER_PAGE", 20))
    FOLLOWERS_PER_PAGE = int(os.environ.get("FOLLOWERS_PER_PAGE", 50))
    COMMENTS_PER_PAGE = int(os.environ.get("COMMENTS_PER_PAGE", 30))
    SLOW_DB_QUERY_TIME = float(os.environ.get("SLOW_DB_QUERY_TIME", 0.5))

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or os.path.join(basedir, "uploads")

    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    @staticmethod
    def init_app(app):
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DEV_DATABASE_URL")
        or "sqlite:///" + os.path.join(basedir, "data-dev.sqlite")
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "sqlite://"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(basedir, "data.sqlite")
    )

    @classmethod
    def init_app(cls, app):
        super().init_app(app)

        import logging
        from logging.handlers import SMTPHandler

        credentials = None
        secure = None

        if cls.MAIL_USERNAME and cls.MAIL_PASSWORD:
            credentials = (cls.MAIL_USERNAME, cls.MAIL_PASSWORD)
            if cls.MAIL_USE_TLS:
                secure = ()

        if cls.ADMIN_EMAIL:
            mail_handler = SMTPHandler(
                mailhost=(cls.MAIL_SERVER, cls.MAIL_PORT),
                fromaddr=cls.MAIL_SENDER,
                toaddrs=[cls.ADMIN_EMAIL],
                subject=f"{cls.MAIL_SUBJECT_PREFIX} Application Error",
                credentials=credentials,
                secure=secure,
            )
            mail_handler.setLevel(logging.ERROR)
            app.logger.addHandler(mail_handler)


class HerokuConfig(ProductionConfig):
    SSL_REDIRECT = bool(os.environ.get("DYNO"))

    @classmethod
    def init_app(cls, app):
        super().init_app(app)

        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

        import logging
        from logging import StreamHandler

        stream_handler = StreamHandler()
        stream_handler.setLevel(logging.INFO)
        app.logger.addHandler(stream_handler)


class DockerConfig(ProductionConfig):
    @classmethod
    def init_app(cls, app):
        super().init_app(app)

        import logging
        from logging import StreamHandler

        stream_handler = StreamHandler()
        stream_handler.setLevel(logging.INFO)
        app.logger.addHandler(stream_handler)


class UnixConfig(ProductionConfig):
    @classmethod
    def init_app(cls, app):
        super().init_app(app)

        import logging
        from logging.handlers import SysLogHandler

        syslog_handler = SysLogHandler()
        syslog_handler.setLevel(logging.INFO)
        app.logger.addHandler(syslog_handler)


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "heroku": HerokuConfig,
    "docker": DockerConfig,
    "unix": UnixConfig,
    "default": DevelopmentConfig,
}