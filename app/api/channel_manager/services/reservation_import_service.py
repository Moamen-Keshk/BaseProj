from app import db
from app.api.channel_manager.models import ChannelReservationLink
from app.api.models import Booking


class ReservationImportService:
    @staticmethod
    def import_one(connection, reservation_payload: dict):
        external_id = reservation_payload["external_reservation_id"]

        link = ChannelReservationLink.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_reservation_id=external_id,
        ).first()

        if link:
            booking = Booking.query.get(link.internal_booking_id)
            if booking:
                booking.guest_name = reservation_payload.get("guest_name") or booking.guest_name
                booking.email = reservation_payload.get("guest_email") or booking.email
                booking.check_in = reservation_payload["checkin_date"]
                booking.check_out = reservation_payload["checkout_date"]
                db.session.commit()
            return booking

        booking = Booking(
            property_id=connection.property_id,
            guest_name=reservation_payload.get("guest_name"),
            email=reservation_payload.get("guest_email"),
            check_in=reservation_payload["checkin_date"],
            check_out=reservation_payload["checkout_date"],
        )
        db.session.add(booking)
        db.session.flush()

        link = ChannelReservationLink(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_reservation_id=external_id,
            external_version=reservation_payload.get("external_version"),
            internal_booking_id=booking.id,
            status="imported",
        )
        db.session.add(link)
        db.session.commit()

        return booking