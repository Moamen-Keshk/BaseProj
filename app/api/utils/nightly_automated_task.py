from app import db
from app.api.models import Room, Booking
from app.api.constants import Constants
from datetime import datetime
from app.celery_app import celery
from app.api.utils.housekeeping_logic import apply_room_cleaning_status


@celery.task
def daily_housekeeping_status_update():
    today = datetime.today().date()

    # 1. Guest to check out today but not yet -> 'Waiting'
    checkouts_today = Booking.query.filter(
        Booking.check_out == today,
        Booking.status_id == Constants.BookingStatusCoding['Checked In']
    ).all()

    for booking in checkouts_today:
        room = Room.query.get(booking.room_id)
        if room:
            apply_room_cleaning_status(
                room,
                booking.property_id,
                Constants.RoomCleaningStatusCoding['Waiting'],
                'Night Audit',
                allow_system=True,
            )

    # 2. Room checking in today, no checkout today, and is 'Clean' -> 'Refresh'
    checkins_today = Booking.query.filter(
        Booking.check_in == today,
        Booking.status_id == Constants.BookingStatusCoding['Confirmed']
    ).all()

    for booking in checkins_today:
        room = Room.query.get(booking.room_id)
        if room and room.cleaning_status_id == Constants.RoomCleaningStatusCoding['Clean']:
            # Make sure no one is checking out of this room today
            overlapping_checkout = Booking.query.filter(
                Booking.room_id == room.id,
                Booking.check_out == today
            ).first()

            if not overlapping_checkout:
                apply_room_cleaning_status(
                    room,
                    booking.property_id,
                    Constants.RoomCleaningStatusCoding['Refresh'],
                    'Night Audit',
                    allow_system=True,
                )

    db.session.commit()
