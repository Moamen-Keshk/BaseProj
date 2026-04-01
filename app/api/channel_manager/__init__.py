from flask import Blueprint

channel_manager = Blueprint('channel_manager', __name__)

from . import routes
