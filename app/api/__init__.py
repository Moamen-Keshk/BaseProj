from flask import Blueprint

api = Blueprint('api', __name__)

# 1. Import the new PMS-specific permissions
from app.api.models import PMSPermission

# 2. Keep your existing route imports
from . import (
    common,
    floors,
    bookings,
    rooms,
    properties,
    categories,
    payment_status,
    rate_plan,
    season,
    room_online,
    blocks,
    users,
    amenities,
booking_status,
housekeeping
)

# 3. Inject the new PMSPermission into your templates
@api.app_context_processor
def inject_permissions():
    return dict(PMSPermission=PMSPermission)