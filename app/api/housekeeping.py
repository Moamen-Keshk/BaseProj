from collections import defaultdict
from datetime import UTC, datetime

from flask import request, jsonify
from sqlalchemy import func

from app.api.constants import Constants
from app.api.decorators import require_active_staff
from app.api.models import Booking, Room, RoomCleaningLog
from app.api.utils.housekeeping_logic import resolve_housekeeping_display_status
from .. import db
from . import api


@api.route('/properties/<int:property_id>/housekeeping', methods=['GET'])
@require_active_staff
def get_housekeeping_data(property_id):
    date_str = request.args.get('date')
    if not date_str:
        target_date = datetime.now(UTC).date()
    else:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'status': 'fail',
                'message': 'Invalid date format. Expected YYYY-MM-DD.',
            }), 400

    today = datetime.now(UTC).date()
    active_status_ids = [
        Constants.BookingStatusCoding['Confirmed'],
        Constants.BookingStatusCoding['Checked In'],
    ]

    if target_date < today:
        # --- PAST: Return Audit Logs ---
        logs = db.session.query(RoomCleaningLog, Room).join(
            Room, RoomCleaningLog.room_id == Room.id
        ).filter(
            RoomCleaningLog.property_id == property_id,
            func.date(RoomCleaningLog.timestamp) == target_date
        ).order_by(RoomCleaningLog.timestamp.desc()).all()

        log_data = []
        for log, room in logs:
            entry = log.to_json()
            entry['room_number'] = room.room_number
            log_data.append(entry)

        return jsonify({'type': 'past', 'data': log_data}), 200

    elif target_date > today:
        # --- FUTURE: Forecast based on Bookings ---
        rooms = Room.query.filter_by(property_id=property_id).order_by(Room.room_number).all()
        overlapping_bookings = Booking.query.filter(
            Booking.property_id == property_id,
            Booking.status_id.in_(active_status_ids),
            Booking.check_in <= target_date,
            Booking.check_out >= target_date,
        ).all()
        bookings_by_room = defaultdict(list)
        for booking in overlapping_bookings:
            bookings_by_room[booking.room_id].append(booking)
        forecast_data = []

        for room in rooms:
            room_bookings = bookings_by_room.get(room.id, [])

            if not room_bookings:
                # Room is totally empty on this date
                status = "Clean"
            else:
                # Check if this date is a check-out day or check-in day for any of the overlapping bookings
                is_checkout = any(b.check_out == target_date for b in room_bookings)
                is_checkin = any(b.check_in == target_date for b in room_bookings)

                if is_checkout:
                    status = "To be cleaned"  # Guest leaves, room gets dirty
                elif is_checkin:
                    status = "To be refreshed"  # Guest arrives, just needs a refresh
                else:
                    status = "Expected Occupied"

            forecast_data.append({
                'room_id': room.id,
                'room_number': room.room_number,
                'forecast_status': status
            })

        return jsonify({'type': 'future', 'data': forecast_data}), 200

    # --- TODAY: Return the rooms' live housekeeping status ---
    rooms = Room.query.filter_by(property_id=property_id).order_by(Room.room_number).all()
    active_bookings = Booking.query.filter(
        Booking.property_id == property_id,
        Booking.status_id.in_(active_status_ids),
        Booking.check_in <= today,
        Booking.check_out > today,
    ).all()
    occupied_room_ids = {booking.room_id for booking in active_bookings}
    current_data = []

    for room in rooms:
        base_status_id = room.cleaning_status_id
        base_status = Constants.RoomCleaningStatusCoding.get(base_status_id, 'Unknown')
        has_active_stay = room.id in occupied_room_ids
        display_status_id = resolve_housekeeping_display_status(base_status_id, has_active_stay)
        display_status = Constants.RoomCleaningStatusCoding.get(display_status_id, 'Unknown')

        current_data.append({
            'id': room.id,
            'room_id': room.id,
            'room_number': room.room_number,
            'cleaning_status_id': display_status_id,
            'cleaning_status': display_status,
            'base_cleaning_status_id': base_status_id,
            'base_cleaning_status': base_status,
            'is_occupied': has_active_stay,
        })

    return jsonify({'type': 'today', 'data': current_data}), 200
