from app import db
from app.api.constants import Constants
from app.api.models import RoomCleaningLog


MANUAL_ALLOWED_STATUS_IDS = {
    Constants.RoomCleaningStatusCoding['Dirty'],
    Constants.RoomCleaningStatusCoding['Clean'],
    Constants.RoomCleaningStatusCoding['Refresh'],
    Constants.RoomCleaningStatusCoding['Service'],
    Constants.RoomCleaningStatusCoding['Ready'],
}

SYSTEM_ONLY_STATUS_IDS = {
    Constants.RoomCleaningStatusCoding['Waiting'],
    Constants.RoomCleaningStatusCoding['Occupied'],
}


def is_manual_cleaning_status_allowed(status_id):
    return status_id in MANUAL_ALLOWED_STATUS_IDS


def resolve_housekeeping_display_status(base_status_id, has_active_stay):
    occupied_status_id = Constants.RoomCleaningStatusCoding['Occupied']
    clean_status_id = Constants.RoomCleaningStatusCoding['Clean']
    ready_status_id = Constants.RoomCleaningStatusCoding['Ready']

    if has_active_stay and base_status_id in {clean_status_id, ready_status_id, None}:
        return occupied_status_id

    return base_status_id


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
