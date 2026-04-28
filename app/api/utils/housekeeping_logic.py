from app import db
from app.api.constants import Constants
from app.api.models import RoomCleaningLog


DIRTY_STATUS_ID = Constants.RoomCleaningStatusCoding['Dirty']
WAITING_STATUS_ID = Constants.RoomCleaningStatusCoding['Waiting']
CLEAN_STATUS_ID = Constants.RoomCleaningStatusCoding['Clean']
REFRESH_STATUS_ID = Constants.RoomCleaningStatusCoding['Refresh']
SERVICE_STATUS_ID = Constants.RoomCleaningStatusCoding['Service']
OCCUPIED_STATUS_ID = Constants.RoomCleaningStatusCoding['Occupied']
READY_STATUS_ID = Constants.RoomCleaningStatusCoding['Ready']

ACTIVE_BOOKING_STATUS_IDS = {
    Constants.BookingStatusCoding['Confirmed'],
    Constants.BookingStatusCoding['Checked In'],
}


MANUAL_ALLOWED_STATUS_IDS = {
    DIRTY_STATUS_ID,
    CLEAN_STATUS_ID,
    REFRESH_STATUS_ID,
    SERVICE_STATUS_ID,
    READY_STATUS_ID,
}

SYSTEM_ONLY_STATUS_IDS = {
    WAITING_STATUS_ID,
    OCCUPIED_STATUS_ID,
}


def is_manual_cleaning_status_allowed(status_id):
    return status_id in MANUAL_ALLOWED_STATUS_IDS


def is_housekeeping_active_booking_status(status_id):
    return status_id in ACTIVE_BOOKING_STATUS_IDS


def resolve_housekeeping_display_status(base_status_id, has_active_stay):
    if has_active_stay and base_status_id in {CLEAN_STATUS_ID, READY_STATUS_ID, None}:
        return OCCUPIED_STATUS_ID

    return base_status_id


def resolve_forecast_status(*, has_arrival, has_departure, has_active_stay):
    if has_departure:
        return 'To be cleaned'
    if has_arrival:
        return 'To be refreshed'
    if has_active_stay:
        return 'Expected Occupied'
    return 'Clean'


def should_auto_refresh_for_arrival(current_status_id, *, has_checkout_today):
    if has_checkout_today:
        return False
    return current_status_id in {CLEAN_STATUS_ID, READY_STATUS_ID}


def should_auto_set_waiting(current_status_id):
    return current_status_id in {CLEAN_STATUS_ID, READY_STATUS_ID, OCCUPIED_STATUS_ID, None}


def apply_room_cleaning_status(room, property_id, new_status_id, user_name, *, allow_system=False):
    if room is None:
        raise ValueError('Room not found.')

    if new_status_id is None:
        raise ValueError('A cleaning status is required.')

    if not allow_system and not is_manual_cleaning_status_allowed(new_status_id):
        raise ValueError('This housekeeping status can only be set automatically by the system.')

    if room.cleaning_status_id == new_status_id:
        return False

    old_status = room.cleaning_status_id
    room.cleaning_status_id = new_status_id
    db.session.add(room)
    db.session.add(
        RoomCleaningLog(
            property_id=property_id,
            room_id=room.id,
            user_name=user_name or 'System',
            old_status_id=old_status,
            new_status_id=new_status_id,
        )
    )
    return True
