from flask import Blueprint

api = Blueprint('api', __name__)

from .models import Permission
from . import (common, floors, bookings, rooms, properties, categories,
               all_status, rate_plan, season, room_online, blocks)


@api.app_context_processor
def inject_permissions():
    return dict(Permission=Permission)
