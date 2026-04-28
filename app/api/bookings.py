import logging
import os
from datetime import timedelta, datetime
from types import SimpleNamespace
from flask import request, make_response, jsonify
from sqlalchemy import or_, and_, cast, String, func

from . import api
from app.api.models import Booking, RoomOnline, BookingRate, BookingStatus, GuestMessage, Room, RatePlan
from .. import db
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.constants import Constants
from app.api.payments.services import record_booking_payment, sync_invoice_for_booking
from app.api.utils.housekeeping_logic import (
    ACTIVE_BOOKING_STATUS_IDS,
    REFRESH_STATUS_ID,
    should_auto_refresh_for_arrival,
    apply_room_cleaning_status,
)

# --- CHANNEL MANAGER IMPORTS ---
from app.api.channel_manager.models import ChannelReservationLink
from app.api.channel_manager.services.pms_sync import (
    queue_booking_ari_sync,
    queue_booking_transition_ari_sync,
)
from app.api.payments.models import Invoice
from app.api.utils.notifications import (
    clear_notifications,
    notify_booking_cancelled,
    notify_booking_changed,
    notify_guest_message_received,
    notify_new_booking,
    notify_overbooking_issue,
    sync_arrival_issue_notification,
    NotificationType,
)
from app.api.utils.revenue_management import (
    DIRECT_CHANNEL_CODE,
    build_dynamic_quote,
    resolve_dynamic_nightly_rate,
)


def _normalize_phone_number(phone_number):
    if not phone_number:
        return ''

    stripped = ''.join(ch for ch in str(phone_number) if ch.isdigit() or ch == '+')
    if stripped.startswith('00'):
        return f"+{stripped[2:]}"
    if stripped.startswith('+'):
        return stripped
    return stripped


def _normalize_guest_name(first_name, last_name):
    return ' '.join(part for part in [(first_name or '').strip(), (last_name or '').strip()] if part) or 'Guest'


def _select_booking_for_inbound_message(normalized_phone):
    if not normalized_phone:
        return None

    lookup_fragment = normalized_phone[-7:] if len(normalized_phone) >= 7 else normalized_phone
    candidate_query = Booking.query.filter(Booking.phone.isnot(None))
    if lookup_fragment:
        candidate_query = candidate_query.filter(Booking.phone.like(f"%{lookup_fragment}%"))

    candidates = candidate_query.order_by(Booking.check_out.desc(), Booking.id.desc()).limit(50).all()
    exact_matches = [booking for booking in candidates if _normalize_phone_number(booking.phone) == normalized_phone]
    if not exact_matches:
        return None

    today = datetime.utcnow().date()
    active_matches = [
        booking for booking in exact_matches
        if booking.check_in and booking.check_out
        and booking.check_in - timedelta(days=1) <= today <= booking.check_out + timedelta(days=1)
    ]
    if active_matches:
        return active_matches[0]

    recent_matches = [
        booking for booking in exact_matches
        if booking.check_out and booking.check_out >= today - timedelta(days=30)
    ]
    if recent_matches:
        return recent_matches[0]

    return exact_matches[0]


def _queue_guest_message_delivery(task_callable, *, guest_message, **task_kwargs):
    try:
        task_callable.delay(message_id=guest_message.id, **task_kwargs)
    except Exception as exc:
        logging.exception("Failed to queue guest communication: %s", str(exc))
        guest_message.delivery_status = 'failed'
        guest_message.delivery_error = 'Failed to queue delivery task.'
        db.session.commit()
        raise


def _resolve_booking_rate_plan(booking):
    rate_plan_id = getattr(booking, 'rate_plan_id', None)
    if rate_plan_id in (None, ''):
        return None

    try:
        rate_plan_id = int(rate_plan_id)
    except (TypeError, ValueError):
        return None

    return RatePlan.query.filter_by(
        id=rate_plan_id,
        property_id=getattr(booking, 'property_id', None),
        is_active=True,
    ).first()


def _resolve_booking_nightly_rate(booking, target_date, *, stay_length):
    rate_plan = _resolve_booking_rate_plan(booking)
    if rate_plan is not None:
        nightly_rate = resolve_dynamic_nightly_rate(
            rate_plan=rate_plan,
            stay_date=target_date,
            stay_length=stay_length,
            adults=int(getattr(booking, 'number_of_adults', None) or 2),
            children=int(getattr(booking, 'number_of_children', None) or 0),
            channel_code=getattr(booking, 'pricing_channel_code', None) or DIRECT_CHANNEL_CODE,
            room_id=getattr(booking, 'room_id', None),
        )
        return nightly_rate, rate_plan.id

    room_online = RoomOnline.query.filter_by(
        room_id=booking.room_id,
        date=target_date
    ).first()
    if room_online is not None:
        return float(room_online.price), room_online.rate_plan_id

    return 0.0, None


@api.route('/properties/<int:property_id>/bookings', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def new_booking(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        user_id = get_current_user()  # Still getting this just to mark the creator
        booking_data = request.get_json()
        auto_check_in = bool(booking_data.get('auto_check_in', False))
        initial_amount_paid = float(booking_data.get('amount_paid') or 0.0)
        payment_method = booking_data.get('payment_method') or 'cash'
        payment_reference = booking_data.get('payment_reference')
        payment_notes = booking_data.get('payment_notes')
        initial_payment_status = booking_data.get('initial_payment_status') or 'succeeded'
        initial_payment_source = booking_data.get('initial_payment_source') or (
            'front_desk' if auto_check_in else 'manual'
        )
        initial_payment_channel = booking_data.get('external_channel')

        try:
            booking = Booking.from_json(booking_data)
        except ValueError as ve:
            print(str(ve))
            return make_response(jsonify({'status': 'fail', 'message': str(ve)})), 400

        # ---> Prevent Overbooking / Double Bookings <---
        is_available = check_room_availability(
            room_id=booking.room_id,
            check_in=booking.check_in,
            check_out=booking.check_out
        )

        if not is_available:
            notify_overbooking_issue(
                property_id=property_id,
                room_id=booking.room_id,
                check_in=booking.check_in,
                check_out=booking.check_out,
            )
            db.session.commit()
            return make_response(jsonify({
                "status": "error",
                "message": "The selected room is already booked for these dates. Please choose different dates or another room."
            })), 409

        # Force the property_id from the secured URL to prevent payload tampering
        booking.property_id = property_id
        booking.creator_id = user_id
        booking.pricing_channel_code = booking.pricing_channel_code or DIRECT_CHANNEL_CODE
        booking.amount_paid = 0.0

        assign_nightly_rates(booking)
        booking.update_payment_status()
        db.session.add(booking)
        db.session.flush()
        sync_invoice_for_booking(booking)

        if initial_amount_paid > 0:
            record_booking_payment(
                booking=booking,
                amount=initial_amount_paid,
                payment_method=payment_method,
                source=initial_payment_source,
                status=initial_payment_status,
                reference=payment_reference,
                notes=payment_notes,
                recorded_by=user_id,
                external_channel=initial_payment_channel,
                is_vcc=payment_method == 'ota_vcc',
            )

        if auto_check_in:
            checked_in_status = db.session.query(BookingStatus).filter_by(code='CHECKED IN').first()
            if not checked_in_status:
                raise ValueError('Checked In status not configured in the system.')
            booking.change_status(checked_in_status.id)

        # Apply the housekeeping rule for same-day check-ins
        handle_same_day_checkin_housekeeping(booking)

        db.session.commit()

        notify_new_booking(booking, actor_uid=user_id)
        sync_arrival_issue_notification(booking)
        db.session.commit()

        if booking.email:
            from app.api.utils.guest_communication_task import send_booking_email_task
            send_booking_email_task.delay(booking_id=booking.id, property_id=property_id)

        queue_booking_ari_sync(booking, 'booking_created')

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking submitted successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in new_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to submit booking. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/send_message', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def send_guest_message(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json() or {}
        subject = (data.get('subject') or '').strip()
        message_body = (data.get('message') or '').strip()

        if not subject or not message_body:
            return make_response(jsonify({'status': 'fail', 'message': 'Subject and message are required.'})), 400

        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking or not booking.email:
            return make_response(jsonify({'status': 'fail', 'message': 'Booking or guest email not found.'})), 404

        email_log = GuestMessage(
            booking_id=booking.id,
            property_id=property_id,
            direction='outbound',
            channel='email',
            subject=subject,
            message_body=message_body,
            is_read=True,
            delivery_status='queued',
            sent_by_user_id=get_current_user(),
        )
        db.session.add(email_log)
        db.session.commit()

        from app.api.utils.guest_communication_task import send_guest_message
        _queue_guest_message_delivery(
            send_guest_message,
            guest_message=email_log,
            email=booking.email,
            subject=f"{subject} DO NOT REPLY",
            message_body=message_body,
            property_id=property_id,
            first_name=booking.first_name,
            last_name=booking.last_name,
        )

        return make_response(jsonify({
            'status': 'success',
            'message': 'Message queued for delivery.',
            'data': email_log.to_json(),
        })), 200

    except Exception as e:
        logging.exception("Error in send_guest_message: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to send message.'})), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def edit_booking(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking_data = request.get_json()
        current_uid = get_current_user()

        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found in this property.'
            })), 404

        old_property_id = booking.property_id
        old_room_id = booking.room_id
        old_check_in = booking.check_in
        old_check_out = booking.check_out
        old_status_id = booking.status_id

        # ==========================================
        # NEW: VERIFY AVAILABILITY BEFORE UPDATING
        # ==========================================
        new_room_id = booking_data.get('room_id', booking.room_id)
        new_check_in_str = booking_data.get('check_in', str(booking.check_in))
        new_check_out_str = booking_data.get('check_out', str(booking.check_out))

        # Safely convert incoming strings to Date objects
        if isinstance(new_check_in_str, str):
            new_check_in = datetime.strptime(new_check_in_str[:10], '%Y-%m-%d').date()
        else:
            new_check_in = new_check_in_str

        if isinstance(new_check_out_str, str):
            new_check_out = datetime.strptime(new_check_out_str[:10], '%Y-%m-%d').date()
        else:
            new_check_out = new_check_out_str

        # Use the reusable helper to check for overlaps, excluding this specific booking ID
        is_available = check_room_availability(
            room_id=new_room_id,
            check_in=new_check_in,
            check_out=new_check_out,
            exclude_booking_id=booking.id
        )

        if not is_available:
            notify_overbooking_issue(
                property_id=property_id,
                room_id=new_room_id,
                check_in=new_check_in,
                check_out=new_check_out,
            )
            db.session.commit()
            return make_response(jsonify({
                "status": "error",
                "message": "The selected room is already booked for these dates. Please choose different dates or another room."
            })), 409
        # ==========================================

        if 'amount_paid' in booking_data:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Direct amount_paid edits are disabled. Record payments via the payments module.'
            })), 400

        # Update fields dynamically
        updateable_fields = [
            'first_name', 'last_name', 'email', 'phone', 'number_of_adults',
            'number_of_children', 'payment_status_id', 'status_id', 'note',
            'special_request', 'check_in', 'check_out', 'check_in_day',
            'check_in_month', 'check_in_year', 'check_out_day', 'check_out_month',
            'check_out_year', 'number_of_days', 'rate', 'room_id',
            'rate_plan_id', 'pricing_channel_code',
        ]

        for field in updateable_fields:
            if field in booking_data:
                setattr(booking, field, booking_data[field])

        if getattr(booking, 'rate_plan_id', None) not in (None, ''):
            booking.rate_plan_id = int(booking.rate_plan_id)
        else:
            booking.rate_plan_id = None
        booking.pricing_channel_code = booking.pricing_channel_code or DIRECT_CHANNEL_CODE

        BookingRate.query.filter_by(booking_id=booking.id).delete()
        assign_nightly_rates(booking)

        # Automatically resolve the payment status after any rate or payment changes
        booking.update_payment_status()
        sync_invoice_for_booking(booking)

        handle_same_day_checkin_housekeeping(booking)

        db.session.commit()

        cancelled_status_id = Constants.BookingStatusCoding['Cancelled']
        if old_status_id != booking.status_id and booking.status_id == cancelled_status_id:
            notify_booking_cancelled(
                property_id=booking.property_id,
                booking_id=booking.id,
                guest_name=_normalize_guest_name(booking.first_name, booking.last_name),
                booking_reference=f"#{booking.confirmation_number}" if booking.confirmation_number else None,
                actor_uid=current_uid,
            )
        else:
            notify_booking_changed(booking, actor_uid=current_uid)
        sync_arrival_issue_notification(booking)
        db.session.commit()

        queue_booking_transition_ari_sync(
            old_property_id=old_property_id,
            old_room_id=old_room_id,
            old_check_in=old_check_in,
            old_check_out=old_check_out,
            booking=booking,
            reason='booking_updated',
        )

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/bookings', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def all_bookings(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        check_in_year = request.args.get('check_in_year', type=int)
        check_in_month = request.args.get('check_in_month', type=int)
        search_query = (request.args.get('q') or '').strip()
        check_in_from_raw = request.args.get('check_in_from')
        check_out_to_raw = request.args.get('check_out_to')

        def _parse_date_arg(value):
            if not value:
                return None
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return None

        check_in_from = _parse_date_arg(check_in_from_raw)
        check_out_to = _parse_date_arg(check_out_to_raw)

        bookings_query = db.session.query(Booking).outerjoin(
            Room, Booking.room_id == Room.id
        ).outerjoin(
            Invoice, Invoice.booking_id == Booking.id
        ).filter(
            Booking.property_id == property_id
        )

        if check_in_year is not None and check_in_month is not None:
            bookings_query = bookings_query.filter(
                and_(
                    or_(Booking.check_in_year == check_in_year,
                        Booking.check_out_year == check_in_year),
                    or_(
                        and_(Booking.check_in_month == check_in_month,
                             Booking.check_out_month == check_in_month),
                        and_(Booking.check_in_month != check_in_month,
                             Booking.check_out_month == check_in_month),
                        and_(Booking.check_in_month == check_in_month,
                             Booking.check_out_month != check_in_month)
                    )
                )
            )

        if check_in_from is not None:
            bookings_query = bookings_query.filter(Booking.check_in >= check_in_from)

        if check_out_to is not None:
            bookings_query = bookings_query.filter(Booking.check_out <= check_out_to)

        if search_query:
            search_like = f"%{search_query.lower()}%"
            raw_like = f"%{search_query}%"
            full_name = func.trim(
                func.coalesce(Booking.first_name, '') + ' ' + func.coalesce(Booking.last_name, '')
            )

            bookings_query = bookings_query.filter(
                or_(
                    func.lower(func.coalesce(Booking.first_name, '')).like(search_like),
                    func.lower(func.coalesce(Booking.last_name, '')).like(search_like),
                    func.lower(full_name).like(search_like),
                    func.lower(func.coalesce(Booking.email, '')).like(search_like),
                    func.lower(func.coalesce(Booking.phone, '')).like(search_like),
                    func.lower(func.coalesce(Booking.note, '')).like(search_like),
                    func.lower(func.coalesce(Booking.special_request, '')).like(search_like),
                    cast(Booking.id, String).like(raw_like),
                    cast(Booking.confirmation_number, String).like(raw_like),
                    cast(Room.room_number, String).like(raw_like),
                    func.lower(func.coalesce(Invoice.invoice_number, '')).like(search_like),
                )
            )

        bookings = bookings_query.order_by(
            Booking.check_in_year,
            Booking.check_in_month,
            Booking.check_in_day,
            Booking.id.desc(),
        ).all()

        response_data = [booking.to_json() for booking in bookings]

        return make_response(jsonify({
            'status': 'success',
            'data': response_data
        })), 200
    except Exception as e:
        logging.exception("Error in all_bookings: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch bookings.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['DELETE', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def delete_booking(property_id, booking_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        current_uid = get_current_user()
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found or permission denied.'
            })), 404

        old_property_id = booking.property_id
        old_room_id = booking.room_id
        old_check_in = booking.check_in
        old_check_out = booking.check_out
        guest_name = _normalize_guest_name(booking.first_name, booking.last_name)
        booking_reference = f"#{booking.confirmation_number}" if booking.confirmation_number else None

        # --- ADDED THIS LINE TO PREVENT FOREIGN KEY ERROR ---
        ChannelReservationLink.query.filter_by(internal_booking_id=booking_id).delete(synchronize_session=False)

        db.session.delete(booking)
        db.session.commit()

        deleted_snapshot = SimpleNamespace(
            property_id=old_property_id,
            room_id=old_room_id,
            check_in=old_check_in,
            check_out=old_check_out,
        )

        queue_booking_ari_sync(deleted_snapshot, 'booking_deleted')

        notify_booking_cancelled(
            property_id=old_property_id,
            booking_id=booking_id,
            guest_name=guest_name,
            booking_reference=booking_reference,
            actor_uid=current_uid,
        )
        clear_notifications(
            notification_type=NotificationType.ARRIVAL_ISSUE,
            property_id=old_property_id,
            entity_type='booking',
            entity_id=booking_id,
        )
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in delete_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete booking. Please try again.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/check_in', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def check_in_booking(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        checked_in_status = db.session.query(BookingStatus).filter_by(code='CHECKED IN').first()
        if not checked_in_status:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Checked In status not configured in the system.'
            })), 500

        booking.change_status(checked_in_status.id)
        db.session.commit()

        clear_notifications(
            notification_type=NotificationType.ARRIVAL_ISSUE,
            property_id=booking.property_id,
            entity_type='booking',
            entity_id=booking.id,
        )
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking status updated to CHECKED IN.'
        })), 200

    except Exception as e:
        logging.exception("Error in check_in_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking status.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/check_out', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def check_out_booking(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        checked_out_status = db.session.query(BookingStatus).filter_by(code='CHECKED OUT').first()
        if not checked_out_status:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Checked Out status not configured in the system.'
            })), 500

        booking.change_status(checked_out_status.id)

        room = db.session.query(Room).filter_by(id=booking.room_id).first()
        if room:
            apply_room_cleaning_status(
                room,
                booking.property_id,
                Constants.RoomCleaningStatusCoding['Dirty'],
                'System Checkout',
                allow_system=True,
            )

        db.session.commit()

        clear_notifications(
            notification_type=NotificationType.ARRIVAL_ISSUE,
            property_id=booking.property_id,
            entity_type='booking',
            entity_id=booking.id,
        )
        db.session.commit()

        try:
            queue_booking_transition_ari_sync(
                old_property_id=booking.property_id,
                old_room_id=booking.room_id,
                old_check_in=booking.check_in,
                old_check_out=booking.check_out,
                booking=booking,
                reason='booking_checked_out',
            )
        except Exception as sync_err:
            logging.warning(f"Failed to sync checkout to PMS: {sync_err}")

        return make_response(jsonify({
            'status': 'success',
            'message': 'Booking status updated to CHECKED OUT.'
        })), 200

    except Exception as e:
        logging.exception("Error in check_out_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update booking status.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/check_extension', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_bookings')
def check_extension(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        room_id = data.get('room_id')
        current_check_out_str = data.get('current_check_out')
        new_check_out_str = data.get('new_check_out')

        if not all([room_id, current_check_out_str, new_check_out_str]):
            return make_response(jsonify({'status': 'fail', 'message': 'Missing required fields'})), 400

        current_check_out = datetime.strptime(current_check_out_str, '%Y-%m-%d').date()
        new_check_out = datetime.strptime(new_check_out_str, '%Y-%m-%d').date()

        if new_check_out <= current_check_out:
            return make_response(
                jsonify({'status': 'fail', 'message': 'New check-out must be after current check-out'})), 400

        # Step 1: Verify Availability
        overlapping_bookings = db.session.query(Booking).filter(
            Booking.property_id == property_id,
            Booking.room_id == room_id,
            Booking.status_id != 5,  # Exclude cancelled
            Booking.check_in < new_check_out,
            Booking.check_out > current_check_out
        ).count()

        if overlapping_bookings > 0:
            return make_response(jsonify({'status': 'success', 'available': False, 'extra_cost': 0.0})), 200

        # Step 2: Calculate exact extra cost using the booking's assigned rate plan/channel.
        booking = db.session.query(Booking).filter(
            Booking.property_id == property_id,
            Booking.room_id == room_id,
            Booking.check_out == current_check_out,
            Booking.status_id.in_(list(ACTIVE_BOOKING_STATUS_IDS)),
        ).order_by(Booking.id.desc()).first()

        extra_cost = 0.0
        curr_date = current_check_out
        stay_length = max(1, (new_check_out - booking.check_in).days) if booking else max(
            1, (new_check_out - current_check_out).days
        )
        while curr_date < new_check_out:
            if booking is not None:
                nightly_rate, _ = _resolve_booking_nightly_rate(
                    booking,
                    curr_date,
                    stay_length=stay_length,
                )
            else:
                room_online = RoomOnline.query.filter_by(room_id=room_id, date=curr_date).first()
                nightly_rate = float(room_online.price) if room_online else 0.0
            extra_cost += float(nightly_rate)
            curr_date += timedelta(days=1)

        return make_response(jsonify({
            'status': 'success',
            'available': True,
            'extra_cost': extra_cost
        })), 200

    except Exception as e:
        logging.exception("Error in check_extension: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to check extension availability.'})), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/extend', methods=['POST', 'OPTIONS'],
           strict_slashes=False)
@require_permission('manage_bookings')
def extend_booking(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        new_check_out_str = data.get('new_check_out')
        is_paid = data.get('is_paid', False)
        extra_cost = float(data.get('extra_cost', 0.0))

        if not new_check_out_str:
            return make_response(jsonify({'status': 'fail', 'message': 'New check-out date is required.'})), 400

        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()
        if not booking:
            return make_response(jsonify({'status': 'fail', 'message': 'Booking not found.'})), 404

        new_check_out = datetime.strptime(new_check_out_str, '%Y-%m-%d').date()
        old_check_out = booking.check_out

        if new_check_out <= old_check_out:
            return make_response(
                jsonify({'status': 'fail', 'message': 'New check-out must be after current check-out.'})), 400

        # Step 1: Update core booking dates and total rate
        booking.check_out = new_check_out
        booking.check_out_year = new_check_out.year
        booking.check_out_month = new_check_out.month
        booking.check_out_day = new_check_out.day
        booking.number_of_days = (new_check_out - booking.check_in).days

        # Increase the total bill by the extension cost
        booking.rate = float(booking.rate or 0.0) + extra_cost

        # Step 2: Generate new BookingRate entries for the extended days
        curr_date = old_check_out
        stay_length = max(1, (new_check_out - booking.check_in).days)
        while curr_date < new_check_out:
            nightly_rate, applied_rate_plan_id = _resolve_booking_nightly_rate(
                booking,
                curr_date,
                stay_length=stay_length,
            )

            booking.booking_rates.append(
                BookingRate(
                    booking_id=booking.id,
                    rate_date=curr_date,
                    nightly_rate=nightly_rate,
                    rate_plan_id=applied_rate_plan_id,
                )
            )
            curr_date += timedelta(days=1)

        # 👉 Step 3: THE NEW FINANCIAL LOGIC
        # If the user checked the box saying "Guest paid the extra amount now"
        if is_paid and extra_cost > 0:
            record_booking_payment(
                booking=booking,
                amount=extra_cost,
                payment_method='cash',
                source='extension',
                status='succeeded',
                reference='BOOKING_EXTENSION',
                notes='Payment captured during booking extension.',
            )
        else:
            booking.update_payment_status()
            sync_invoice_for_booking(booking)

        db.session.commit()

        # Step 4: Notify Channel Manager / PMS sync that dates have shifted
        try:
            queue_booking_transition_ari_sync(
                old_property_id=booking.property_id,
                old_room_id=booking.room_id,
                old_check_in=booking.check_in,
                old_check_out=old_check_out,
                booking=booking,
                reason='booking_extended',
            )
        except Exception as sync_err:
            logging.warning(f"Failed to sync extension to PMS: {sync_err}")

        return make_response(jsonify({'status': 'success', 'message': 'Booking extended successfully.'})), 200

    except Exception as e:
        logging.exception("Error in extend_booking: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to extend booking.'})), 500


@api.route('/properties/<int:property_id>/bookings/by_state', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def bookings_by_date_and_state(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        date_str = request.args.get('date')
        booking_type = request.args.get('booking_state', type=str)

        if not date_str or not booking_type:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Missing date or booking_state parameter.'
            })), 400

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Invalid date format. Expected YYYY-MM-DD.'
            })), 400

        booking_type = booking_type.strip().lower()

        filters = {
            'arrivals': Booking.check_in == target_date,
            'departures': Booking.check_out == target_date,
            'inhouse': and_(
                Booking.check_in <= target_date,
                Booking.check_out > target_date
            ),
        }

        selected_filter = filters.get(booking_type)
        if selected_filter is None:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Invalid booking_state. Use InHouse, Arrivals, or Departures.'
            })), 400

        bookings = (
            db.session.query(Booking)
            .filter(
                Booking.property_id == property_id,
                selected_filter
            )
            .order_by(Booking.check_in)
            .all()
        )

        return make_response(jsonify({
            'status': 'success',
            'data': [booking.to_json() for booking in bookings]
        })), 200

    except Exception as e:
        logging.exception("Error in bookings_by_date: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch bookings.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_bookings')
def get_booking_by_id(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = db.session.query(Booking).filter_by(id=booking_id, property_id=property_id).first()

        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        return make_response(jsonify({
            'status': 'success',
            'data': booking.to_json()
        })), 200

    except Exception as e:
        logging.exception("Error in get_booking_by_id: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch booking.'
        })), 500


# --- HELPER FUNCTION ---
def assign_nightly_rates(booking):
    # Ensure check_in and check_out are datetime.date objects
    if isinstance(booking.check_in, str):
        booking.check_in = datetime.strptime(booking.check_in, "%Y-%m-%dT%H:%M:%S.%f").date()
    if isinstance(booking.check_out, str):
        booking.check_out = datetime.strptime(booking.check_out, "%Y-%m-%dT%H:%M:%S.%f").date()

    current_date = booking.check_in
    total = 0.0
    stay_length = max(1, (booking.check_out - booking.check_in).days)

    while current_date < booking.check_out:
        nightly_rate, applied_rate_plan_id = _resolve_booking_nightly_rate(
            booking,
            current_date,
            stay_length=stay_length,
        )

        booking.booking_rates.append(
            BookingRate(
                booking_id=booking.id,
                rate_date=current_date,
                nightly_rate=nightly_rate,
                rate_plan_id=applied_rate_plan_id,
            )
        )

        total += nightly_rate
        current_date += timedelta(days=1)

    booking.rate = total


from app.api.models import User


def handle_same_day_checkin_housekeeping(booking):
    """
    Automatically updates room cleaning status from a stay-ready state to 'Refresh'
    if a booking is created/edited for a same-day check-in, provided
    no other booking checks out of that room today.
    """
    today = datetime.today().date()

    if booking.status_id not in ACTIVE_BOOKING_STATUS_IDS:
        return

    # 1. Check if the check-in is scheduled for today
    if booking.check_in == today:
        room = db.session.query(Room).filter_by(id=booking.room_id).first()
        if room is None:
            return

        # 2. Verify no other active booking is checking out today from this room.
        checkout_today = db.session.query(Booking).filter(
            Booking.room_id == booking.room_id,
            Booking.check_out == today,
            Booking.id != booking.id,
            Booking.status_id.in_(list(ACTIVE_BOOKING_STATUS_IDS)),
        ).first()

        if should_auto_refresh_for_arrival(
            room.cleaning_status_id,
            has_checkout_today=checkout_today is not None,
        ):
            user = db.session.query(User).filter_by(uid=booking.creator_id).first()
            user_name = user.username if user else "System Auto-Refresh"
            apply_room_cleaning_status(
                room,
                booking.property_id,
                REFRESH_STATUS_ID,
                user_name,
                allow_system=True,
            )

def check_room_availability(room_id, check_in, check_out, exclude_booking_id=None):
    """
    Checks if a room is available for the given dates.
    Returns True if available, False if there is an overlapping booking.
    """
    # Base query: same room, exclude canceled bookings (assuming status_id 5 is Canceled)
    query = db.session.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status_id != 5,
        Booking.check_in < check_out,  # New booking starts before existing ends
        Booking.check_out > check_in  # New booking ends after existing starts
    )

    # If editing an existing booking, exclude it from the overlap check
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)

    conflicting_booking = query.first()

    return conflicting_booking is None

# ==========================================
# 💬 GUEST COMMUNICATION (CHAT/TWILIO)
# ==========================================

@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/chat', methods=['GET', 'OPTIONS'])
@require_permission('view_bookings')
def get_chat_history(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    booking = Booking.query.filter_by(id=booking_id, property_id=property_id).first()
    if not booking:
        return jsonify({'status': 'fail', 'message': 'Booking not found.'}), 404

    messages = GuestMessage.query.filter_by(booking_id=booking_id, property_id=property_id).order_by(
        GuestMessage.timestamp.asc()).all()

    # Mark inbound messages as read since the staff is opening the chat
    unread_messages = [m for m in messages if m.direction == 'inbound' and not m.is_read]
    for msg in unread_messages:
        msg.is_read = True
    if unread_messages:
        db.session.commit()

    return jsonify({'status': 'success', 'data': [m.to_json() for m in messages]}), 200


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/chat', methods=['POST', 'OPTIONS'])
@require_permission('manage_bookings')
def send_chat_message(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    data = request.get_json() or {}
    message_body = (data.get('message') or '').strip()
    channel = (data.get('channel') or 'whatsapp').strip().lower()

    if not message_body:
        return jsonify({'status': 'fail', 'message': 'Message is required.'}), 400

    if channel not in {'whatsapp', 'sms'}:
        return jsonify({'status': 'fail', 'message': 'Unsupported chat channel.'}), 400

    booking = Booking.query.filter_by(id=booking_id, property_id=property_id).first()
    if not booking:
        return jsonify({'status': 'fail', 'message': 'Booking not found.'}), 404

    if not (booking.phone and _normalize_phone_number(booking.phone)):
        return jsonify({'status': 'fail', 'message': 'Guest phone number is not available.'}), 400

    chat_log = GuestMessage(
        booking_id=booking.id,
        property_id=property_id,
        direction='outbound',
        channel=channel,
        message_body=message_body,
        is_read=True,
        delivery_status='queued',
        sent_by_user_id=get_current_user(),
    )
    db.session.add(chat_log)
    db.session.commit()

    from app.api.utils.guest_communication_task import send_sms_whatsapp_task
    _queue_guest_message_delivery(
        send_sms_whatsapp_task,
        guest_message=chat_log,
        booking_id=booking.id,
        message_body=message_body,
        channel=channel,
    )

    return jsonify({
        'status': 'success',
        'message': 'Message queued.',
        'data': chat_log.to_json(),
    }), 200


@api.route('/webhooks/twilio/receive', methods=['POST'])
def twilio_webhook():
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    twilio_signature = request.headers.get('X-Twilio-Signature')
    if auth_token and twilio_signature:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(auth_token)
        if not validator.validate(request.url, request.form, twilio_signature):
            logging.warning("Rejected Twilio webhook with invalid signature.")
            return jsonify({'status': 'fail', 'message': 'Invalid signature.'}), 403

    # Twilio sends data as form-urlencoded
    from_number = request.form.get('From', '')
    body = (request.form.get('Body') or '').strip()

    if not from_number or not body:
        return jsonify({'status': 'fail', 'message': 'Missing sender or body.'}), 400

    # Clean 'WhatsApp:' prefix if present
    clean_number = from_number.replace('whatsapp:', '')
    channel = 'whatsapp' if 'whatsapp:' in from_number else 'sms'
    normalized_phone = _normalize_phone_number(clean_number)

    booking = _select_booking_for_inbound_message(normalized_phone)

    if booking:
        inbound_msg = GuestMessage(
            booking_id=booking.id,
            property_id=booking.property_id,
            direction='inbound',
            channel=channel,
            message_body=body,
            is_read=False,
            delivery_status='received',
        )
        db.session.add(inbound_msg)
        notify_guest_message_received(inbound_msg)
        db.session.commit()
    else:
        logging.warning("No booking matched inbound %s message from %s", channel, normalized_phone)

    # Twilio requires an empty TwiML response to acknowledge receipt
    from twilio.twiml.messaging_response import MessagingResponse
    return str(MessagingResponse()), 200, {'Content-Type': 'application/xml'}
