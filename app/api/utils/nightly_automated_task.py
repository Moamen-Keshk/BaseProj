from app import db
from app.api.models import Room, Booking
from app.api.constants import Constants
from datetime import datetime
from app.celery_app import celery
from app.api.utils.housekeeping_logic import (
    REFRESH_STATUS_ID,
    WAITING_STATUS_ID,
    should_auto_refresh_for_arrival,
    should_auto_set_waiting,
    apply_room_cleaning_status,
)


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
        if room and should_auto_set_waiting(room.cleaning_status_id):
            apply_room_cleaning_status(
                room,
                booking.property_id,
                WAITING_STATUS_ID,
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
        if room is None:
            continue

        # Make sure no one is checking out of this room today
        overlapping_checkout = Booking.query.filter(
            Booking.room_id == room.id,
            Booking.check_out == today
        ).first()

        if should_auto_refresh_for_arrival(
            room.cleaning_status_id,
            has_checkout_today=overlapping_checkout is not None,
        ):
            apply_room_cleaning_status(
                room,
                booking.property_id,
                REFRESH_STATUS_ID,
                'Night Audit',
                allow_system=True,
            )

    db.session.commit()
