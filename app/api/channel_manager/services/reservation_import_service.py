from app import db
from app.api.channel_manager.models import ChannelReservationLink, ChannelRoomMap
from app.api.models import Booking


class ReservationImportService:
    @staticmethod
    def _resolve_internal_room_id(connection, reservation_payload: dict):
        external_room_id = reservation_payload.get('external_room_id')
        if not external_room_id:
            return None

        mapping = ChannelRoomMap.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_room_id=external_room_id,
            is_active=True
        ).first()

        return mapping.internal_room_id if mapping else None

    @staticmethod
    def import_one(connection, reservation_payload: dict):
        external_id = reservation_payload['external_reservation_id']

        link = ChannelReservationLink.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_reservation_id=external_id,
        ).first()

        internal_room_id = ReservationImportService._resolve_internal_room_id(connection, reservation_payload)

        if link:
            booking = Booking.query.get(link.internal_booking_id)
            if booking:
                if hasattr(booking, 'first_name') and reservation_payload.get('guest_name'):
                    booking.first_name = reservation_payload.get('guest_name')
                if hasattr(booking, 'email') and reservation_payload.get('guest_email'):
                    booking.email = reservation_payload.get('guest_email')
                if hasattr(booking, 'check_in'):
                    booking.check_in = reservation_payload['checkin_date']
                if hasattr(booking, 'check_out'):
                    booking.check_out = reservation_payload['checkout_date']
                if hasattr(booking, 'room_id') and internal_room_id:
                    booking.room_id = internal_room_id
                db.session.commit()
            return booking

        booking = Booking()

        if hasattr(booking, 'property_id'):
            booking.property_id = connection.property_id
        if hasattr(booking, 'first_name'):
            booking.first_name = reservation_payload.get('guest_name')
        if hasattr(booking, 'email'):
            booking.email = reservation_payload.get('guest_email')
        if hasattr(booking, 'check_in'):
            booking.check_in = reservation_payload['checkin_date']
        if hasattr(booking, 'check_out'):
            booking.check_out = reservation_payload['checkout_date']
        if hasattr(booking, 'room_id') and internal_room_id:
            booking.room_id = internal_room_id
        if hasattr(booking, 'source'):
            booking.source = connection.channel_code
        if hasattr(booking, 'external_id'):
            booking.external_id = external_id

        db.session.add(booking)
        db.session.flush()

        link = ChannelReservationLink(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_reservation_id=external_id,
            external_version=reservation_payload.get('external_version'),
            internal_booking_id=booking.id,
            status='imported',
        )
        db.session.add(link)
        db.session.commit()

        return booking