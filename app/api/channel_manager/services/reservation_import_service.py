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
        reservation_status = reservation_payload.get('status', 'new').lower()  # 'new', 'modified', 'cancelled'

        link = ChannelReservationLink.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_reservation_id=external_id,
        ).first()

        internal_room_id = ReservationImportService._resolve_internal_room_id(connection, reservation_payload)

        # 1. Update Existing Booking
        if link:
            booking = Booking.query.get(link.internal_booking_id)
            if booking:
                # Handle Cancellations
                if reservation_status == 'cancelled':
                    if hasattr(booking, 'status'):
                        booking.status = 'cancelled'
                    link.status = 'cancelled'
                # Handle Modifications
                else:
                    if hasattr(booking, 'first_name') and reservation_payload.get('guest_name'):
                        booking.first_name = reservation_payload.get('guest_name')
                    if hasattr(booking, 'check_in'):
                        booking.check_in = reservation_payload['checkin_date']
                    if hasattr(booking, 'check_out'):
                        booking.check_out = reservation_payload['checkout_date']
                    if hasattr(booking, 'room_id') and internal_room_id:
                        booking.room_id = internal_room_id
                    link.status = 'modified'

                db.session.commit()

                # --- FIX: Call your actual sync function ---
                from app.api.channel_manager.services.pms_sync import queue_booking_ari_sync
                queue_booking_ari_sync(booking, reason=f"OTA Modification: {connection.channel_code}")

            return booking

        # 2. Ignore cancellations for bookings we don't have
        if reservation_status == 'cancelled':
            return None

            # 3. Create New Booking
        booking = Booking()
        if hasattr(booking, 'property_id'):
            booking.property_id = connection.property_id
        if hasattr(booking, 'first_name'):
            booking.first_name = reservation_payload.get('guest_name')
        if hasattr(booking, 'check_in'):
            booking.check_in = reservation_payload['checkin_date']
        if hasattr(booking, 'check_out'):
            booking.check_out = reservation_payload['checkout_date']
        if hasattr(booking, 'room_id') and internal_room_id:
            booking.room_id = internal_room_id
        if hasattr(booking, 'source'):
            booking.source = connection.channel_code
        if hasattr(booking, 'status'):
            booking.status = 'confirmed'

        payment_info = getattr(reservation_payload, 'payment_info', None)
        if payment_info and payment_info.card_number:
            try:
                # IMPORTANT: Send to Stripe (or your payment gateway) immediately
                # Example: stripe.Token.create(card={"number": payment_info.card_number, ...})
                secure_stripe_token = "tok_123456789"  # Replace with actual gateway call

                # Save the safe token to your database
                if hasattr(booking, 'stripe_token'):
                    booking.stripe_token = secure_stripe_token

                if payment_info.is_vcc and hasattr(booking, 'is_ota_vcc'):
                    booking.is_ota_vcc = True

            except Exception as e:
                # Log that card tokenization failed, but don't stop the booking import
                print(f"Failed to tokenize OTA card: {e}")

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

        # --- FIX: Call your actual sync function ---
        from app.api.channel_manager.services.pms_sync import queue_booking_ari_sync
        queue_booking_ari_sync(booking, reason=f"New OTA Booking: {connection.channel_code}")

        return booking