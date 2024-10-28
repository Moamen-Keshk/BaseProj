from flask import Blueprint

api = Blueprint('api', __name__)

from .models import Permission
from . import common, floors


@api.app_context_processor
def inject_permissions():
    return dict(Permission=Permission)
