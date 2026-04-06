from sqlalchemy import func
from datetime import UTC, datetime
from flask import request, jsonify
from app.api.models import RoomCleaningLog, Booking, Room
from app.api.constants import Constants
from .. import db
from . import api

@api.route('/properties/<int:property_id>/housekeeping', methods=['GET'])
def get_housekeeping_data(property_id):
    date_str = request.args.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    today = datetime.now(UTC).date()

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
        rooms = Room.query.filter_by(property_id=property_id).all()
        forecast_data = []

        for room in rooms:
            # Find any active bookings that overlap with this target date
            # Ignore canceled or No-show bookings
            overlapping_bookings = Booking.query.filter(
                Booking.room_id == room.id,
                Booking.status_id.in_([
                    Constants.BookingStatusCoding['Confirmed'],
                    Constants.BookingStatusCoding['Checked In']
                ]),
                Booking.check_in <= target_date,
                Booking.check_out >= target_date
            ).all()

            if not overlapping_bookings:
                # Room is totally empty on this date
                status = "Clean"
            else:
                # Check if this date is a check-out day or check-in day for any of the overlapping bookings
                is_checkout = any(b.check_out == target_date for b in overlapping_bookings)
                is_checkin = any(b.check_in == target_date for b in overlapping_bookings)

                if is_checkout:
                    status = "To be cleaned"  # Guest leaves, room gets dirty
                elif is_checkin:
                    status = "To be refreshed"  # Guest arrives, just needs a refresh
                else:
                    status = "Expected Idle"  # The date falls directly in the middle of a guest's stay

            forecast_data.append({
                'room_id': room.id,
                'room_number': room.room_number,
                'forecast_status': status
            })

        return jsonify({'type': 'future', 'data': forecast_data}), 200

    # --- TODAY: Return the rooms' live housekeeping status ---
    rooms = Room.query.filter_by(property_id=property_id).order_by(Room.room_number).all()
    current_data = []

    for room in rooms:
        current_data.append({
            'room_id': room.id,
            'room_number': room.room_number,
            'cleaning_status_id': room.cleaning_status_id,
            'cleaning_status': Constants.RoomCleaningStatusCoding.get(room.cleaning_status_id, 'Unknown')
        })

    return jsonify({'type': 'today', 'data': current_data}), 200
