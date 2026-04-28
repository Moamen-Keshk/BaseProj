from datetime import datetime
from app import db
from app.api.channel_manager.models import ChannelReservationLink, ChannelRoomMap, ChannelRatePlanMap
from app.api.models import Booking, Room
from flask_socketio import SocketIO
from app.api.utils.pricing_engine import get_room_sellable_type_id

# 👉 IMPORT THE VCC MODEL AND ENCRYPTION UTILITY
from app.api.payments.models import BookingVCC
from app.api.payments.services import sync_invoice_for_booking
from app.api.payments.utils import encrypt_data
from app.api.utils.notifications import (
    notify_booking_cancelled,
    notify_booking_changed,
    notify_new_booking,
    sync_arrival_issue_notification,
)


class ReservationImportService:
    @staticmethod
    def _resolve_internal_room(connection, reservation_payload: dict):
        room_stays = reservation_payload.get('room_stays', [])
        first_room = room_stays[0] if room_stays else {}
        external_room_id = first_room.get('external_room_id')

        if not external_room_id:
            return None

        mapping = ChannelRoomMap.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_room_id=external_room_id,
            is_active=True
        ).first()

        if not mapping:
            return None, None

        if mapping.internal_room_type_id:
            room = next(
                (
                    candidate for candidate in Room.query.filter_by(property_id=connection.property_id)
                    .order_by(Room.room_number).all()
                    if get_room_sellable_type_id(candidate) == mapping.internal_room_type_id
                ),
                None,
            )
            return (room.id if room else None), mapping.internal_room_type_id

        return mapping.internal_room_id, None

    @staticmethod
    def import_one(connection, reservation_payload: dict):
        external_id = reservation_payload.get('external_reservation_id')
        reservation_status = reservation_payload.get('status', 'new').lower()

        # --- 1. EXTRACT DATA FROM OTA PAYLOAD ---
        room_stays = reservation_payload.get('room_stays', [])
        first_room = room_stays[0] if room_stays else {}
        guest = reservation_payload.get('guest', {})

        check_in_str = first_room.get('check_in_date')
        check_out_str = first_room.get('check_out_date')

        # Parse strings into datetime.date objects for precise mapping
        check_in_date = datetime.strptime(check_in_str, "%Y-%m-%d").date() if check_in_str else None
        check_out_date = datetime.strptime(check_out_str, "%Y-%m-%d").date() if check_out_str else None

        link = ChannelReservationLink.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
            external_reservation_id=external_id,
        ).first()

        internal_room_id, internal_room_type_id = ReservationImportService._resolve_internal_room(connection, reservation_payload)
        external_rate_plan_id = first_room.get('external_rate_plan_id')
        rate_plan_mapping = None
        if external_rate_plan_id:
            rate_plan_mapping = ChannelRatePlanMap.query.filter_by(
                property_id=connection.property_id,
                channel_code=connection.channel_code,
                external_rate_plan_id=str(external_rate_plan_id),
                is_active=True,
            ).first()

        # --- 2. UPDATE EXISTING BOOKING ---
        if link:
            booking = Booking.query.get(link.internal_booking_id)
            if booking:
                if reservation_status == 'cancelled':
                    booking.status_id = 5  # Example: 5 is usually Cancelled in your BookingStatus
                    link.status = 'cancelled'
                else:
                    # Update Guest Details
                    booking.first_name = guest.get('first_name', booking.first_name)
                    booking.last_name = guest.get('last_name', booking.last_name)
                    booking.email = guest.get('email', booking.email)
                    booking.phone = guest.get('phone', booking.phone)

                    # Update Room & Rate Details
                    booking.number_of_adults = first_room.get('guests', booking.number_of_adults)
                    booking.rate = reservation_payload.get('total_price', booking.rate)
                    if rate_plan_mapping:
                        booking.rate_plan_id = rate_plan_mapping.internal_rate_plan_id
                        booking.pricing_channel_code = connection.channel_code
                    if internal_room_id:
                        booking.room_id = internal_room_id
                    if internal_room_type_id:
                        booking.requested_room_type_id = internal_room_type_id

                    # Update Dates safely
                    if check_in_date and check_out_date:
                        booking.check_in = check_in_date
                        booking.check_in_day = check_in_date.day
                        booking.check_in_month = check_in_date.month
                        booking.check_in_year = check_in_date.year

                        booking.check_out = check_out_date
                        booking.check_out_day = check_out_date.day
                        booking.check_out_month = check_out_date.month
                        booking.check_out_year = check_out_date.year

                        booking.number_of_days = (check_out_date - check_in_date).days

                    link.status = 'modified'

                    db.session.flush()  # Ensure booking updates are flushed before VCC checks

                    # 👉 NEW: Update or Add VCC Data during a modification
                    card_data = reservation_payload.get('payment_card')
                    if card_data and card_data.get('is_virtual'):
                        existing_vcc = BookingVCC.query.filter_by(booking_id=booking.id).first()

                        encrypted_card = encrypt_data(card_data.get('card_number'))
                        encrypted_cvc = encrypt_data(card_data.get('cvc'))

                        if existing_vcc:
                            existing_vcc.encrypted_card_number = encrypted_card
                            existing_vcc.encrypted_cvc = encrypted_cvc
                            existing_vcc.exp_month = card_data.get('expiration_month')
                            existing_vcc.exp_year = card_data.get('expiration_year')
                        else:
                            new_vcc = BookingVCC(
                                booking_id=booking.id,
                                encrypted_card_number=encrypted_card,
                                encrypted_cvc=encrypted_cvc,
                                exp_month=card_data.get('expiration_month'),
                                exp_year=card_data.get('expiration_year')
                            )
                            db.session.add(new_vcc)

                booking.update_payment_status()
                sync_invoice_for_booking(booking)
                db.session.commit()

                if reservation_status == 'cancelled':
                    notify_booking_cancelled(
                        property_id=booking.property_id,
                        booking_id=booking.id,
                        guest_name=' '.join(part for part in [booking.first_name, booking.last_name] if part).strip() or 'Guest',
                        booking_reference=f"#{booking.confirmation_number}" if booking.confirmation_number else None,
                    )
                else:
                    notify_booking_changed(
                        booking,
                        change_label=f'updated from {connection.channel_code}',
                    )
                    sync_arrival_issue_notification(booking)
                db.session.commit()

                from app.api.channel_manager.services.pms_sync import queue_booking_ari_sync
                queue_booking_ari_sync(booking, reason=f"OTA Modification: {connection.channel_code}")

            return booking

        # --- 3. IGNORE CANCELLATIONS FOR UNKNOWN BOOKINGS ---
        if reservation_status == 'cancelled':
            return None

        # --- 4. CREATE NEW BOOKING ---
        booking = Booking()

        # Base Identifiers
        booking.property_id = connection.property_id
        if internal_room_id:
            booking.room_id = internal_room_id
        if internal_room_type_id:
            booking.requested_room_type_id = internal_room_type_id
        if rate_plan_mapping:
            booking.rate_plan_id = rate_plan_mapping.internal_rate_plan_id
        booking.pricing_channel_code = connection.channel_code
        booking.source = connection.channel_code
        booking.status_id = 1  # Default to 1 (Confirmed) based on your BookingStatus table

        # Guest Info Mapping
        booking.first_name = guest.get('first_name')
        booking.last_name = guest.get('last_name')
        booking.email = guest.get('email')
        booking.phone = guest.get('phone')
        booking.number_of_adults = first_room.get('guests', 1)
        booking.rate = reservation_payload.get('total_price', 0.0)

        # Deep Date Mapping
        if check_in_date and check_out_date:
            booking.check_in = check_in_date
            booking.check_in_day = check_in_date.day
            booking.check_in_month = check_in_date.month
            booking.check_in_year = check_in_date.year

            booking.check_out = check_out_date
            booking.check_out_day = check_out_date.day
            booking.check_out_month = check_out_date.month
            booking.check_out_year = check_out_date.year

            booking.number_of_days = (check_out_date - check_in_date).days

        db.session.add(booking)
        db.session.flush()  # Flush to generate the booking.id for the link and VCC

        # 👉 NEW: Extract and Encrypt VCC Data for New Bookings
        card_data = reservation_payload.get('payment_card')
        if card_data and card_data.get('is_virtual'):
            try:
                new_vcc = BookingVCC(
                    booking_id=booking.id,
                    encrypted_card_number=encrypt_data(card_data.get('card_number')),
                    encrypted_cvc=encrypt_data(card_data.get('cvc')),
                    exp_month=card_data.get('expiration_month'),
                    exp_year=card_data.get('expiration_year')
                )
                db.session.add(new_vcc)

                # Flag the booking model directly if it has this attribute
                if hasattr(booking, 'is_ota_vcc'):
                    booking.is_ota_vcc = True

            except Exception as e:
                print(f"Failed to encrypt and save OTA VCC: {e}")

        booking.update_payment_status()
        sync_invoice_for_booking(booking)

        # Create the OTA Link
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

        notify_new_booking(booking, source_label=connection.channel_code)
        sync_arrival_issue_notification(booking)
        db.session.commit()

        print(f"🔔 EMITTING TO REDIS FOR PROPERTY: {booking.property_id}")
        # 👉 Ensure async_mode='threading' is passed here too!
        external_sio = SocketIO(
            message_queue='redis://localhost:6379/0',
            async_mode='threading'
        )

        external_sio.emit('calendar_updated', {
            'property_id': booking.property_id,
            'message': 'New reservation pulled'
        })

        # Trigger PMS Sync
        from app.api.channel_manager.services.pms_sync import queue_booking_ari_sync
        queue_booking_ari_sync(booking, reason=f"New OTA Booking: {connection.channel_code}")

        return booking
