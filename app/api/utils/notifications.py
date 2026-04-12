from datetime import date, datetime, timezone

from app import db
from app.api.constants import Constants
from app.api.models import Notification, User, UserPropertyAccess, Room


class NotificationType:
    BOOKING_NEW = 'booking_new'
    BOOKING_CHANGED = 'booking_changed'
    ARRIVAL_ISSUE = 'arrival_issue'
    GUEST_MESSAGE = 'guest_message'
    GUEST_MESSAGE_FAILED = 'guest_message_failed'
    PAYMENT_FAILED = 'payment_failed'
    OPERATIONS_ISSUE = 'operations_issue'


def _collect_recipient_ids(property_id, required_permissions=None):
    required_permissions = set(required_permissions or [])
    active_status_id = Constants.AccountStatusCoding['Active']
    recipient_ids = set()

    accesses = (
        UserPropertyAccess.query
        .filter_by(property_id=property_id, account_status_id=active_status_id)
        .all()
    )
    for access in accesses:
        permissions = set(access.role.permissions_json or [])
        if not required_permissions or permissions.intersection(required_permissions):
            recipient_ids.add(access.user_id)

    for user in User.query.filter_by(is_super_admin=True).all():
        recipient_ids.add(user.uid)

    return recipient_ids


def upsert_notifications_for_users(
    *,
    user_ids,
    notification_type,
    title,
    body,
    routing,
    property_id=None,
    entity_type=None,
    entity_id=None,
    has_action=True,
    exclude_user_ids=None,
):
    exclude_user_ids = set(exclude_user_ids or [])
    normalized_entity_id = str(entity_id) if entity_id is not None else None

    for user_id in set(user_ids):
        if not user_id or user_id in exclude_user_ids:
            continue

        existing = Notification.query.filter_by(
            to_user=user_id,
            notification_type=notification_type,
            property_id=property_id,
            entity_type=entity_type,
            entity_id=normalized_entity_id,
            is_read=False,
        ).first()

        if existing:
            existing.title = title
            existing.body = body
            existing.routing = routing
            existing.has_action = has_action
            existing.timestamp = datetime.now(timezone.utc)
            continue

        db.session.add(Notification(
            title=title,
            body=body,
            is_read=False,
            has_action=has_action,
            to_user=user_id,
            routing=routing,
            notification_type=notification_type,
            property_id=property_id,
            entity_type=entity_type,
            entity_id=normalized_entity_id,
        ))


def notify_property_staff(
    *,
    property_id,
    required_permissions,
    notification_type,
    title,
    body,
    routing,
    entity_type=None,
    entity_id=None,
    has_action=True,
    exclude_user_ids=None,
):
    recipients = _collect_recipient_ids(property_id, required_permissions)
    upsert_notifications_for_users(
        user_ids=recipients,
        notification_type=notification_type,
        title=title,
        body=body,
        routing=routing,
        property_id=property_id,
        entity_type=entity_type,
        entity_id=entity_id,
        has_action=has_action,
        exclude_user_ids=exclude_user_ids,
    )


def clear_notifications(*, notification_type, property_id=None, entity_type=None, entity_id=None, user_ids=None):
    query = Notification.query.filter_by(
        notification_type=notification_type,
        property_id=property_id,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    )
    if user_ids:
        query = query.filter(Notification.to_user.in_(list(set(user_ids))))
    query.delete(synchronize_session=False)


def _booking_display_name(booking):
    first_name = (booking.first_name or '').strip()
    last_name = (booking.last_name or '').strip()
    full_name = ' '.join(part for part in [first_name, last_name] if part)
    return full_name or f'Booking #{booking.id}'


def _booking_reference(booking):
    confirmation_number = getattr(booking, 'confirmation_number', None)
    return f'#{confirmation_number}' if confirmation_number else f'#{booking.id}'


def notify_new_booking(booking, *, actor_uid=None, source_label=None):
    source_fragment = f" via {source_label}" if source_label else ''
    notify_property_staff(
        property_id=booking.property_id,
        required_permissions={'view_bookings'},
        notification_type=NotificationType.BOOKING_NEW,
        title='New booking received',
        body=f"{_booking_display_name(booking)} {_booking_reference(booking)} was added{source_fragment}.",
        routing='booking',
        entity_type='booking',
        entity_id=booking.id,
        exclude_user_ids={actor_uid} if actor_uid else None,
    )


def notify_booking_changed(booking, *, actor_uid=None, change_label='updated'):
    notify_property_staff(
        property_id=booking.property_id,
        required_permissions={'view_bookings'},
        notification_type=NotificationType.BOOKING_CHANGED,
        title='Booking changed',
        body=f"{_booking_display_name(booking)} {_booking_reference(booking)} was {change_label}.",
        routing='booking',
        entity_type='booking',
        entity_id=booking.id,
        exclude_user_ids={actor_uid} if actor_uid else None,
    )


def notify_booking_cancelled(*, property_id, booking_id, guest_name, booking_reference=None, actor_uid=None):
    notify_property_staff(
        property_id=property_id,
        required_permissions={'view_bookings'},
        notification_type=NotificationType.BOOKING_CHANGED,
        title='Booking cancelled',
        body=f"{guest_name or f'Booking #{booking_id}'} {booking_reference or f'#{booking_id}'} was cancelled.",
        routing='booking',
        entity_type='booking',
        entity_id=booking_id,
        exclude_user_ids={actor_uid} if actor_uid else None,
    )


def sync_arrival_issue_notification(booking):
    today = date.today()
    active_statuses = {
        Constants.BookingStatusCoding['Confirmed'],
    }
    booking_status = getattr(booking, 'status_id', None)
    if (
        booking.check_in != today
        or booking_status not in active_statuses
    ):
        clear_notifications(
            notification_type=NotificationType.ARRIVAL_ISSUE,
            property_id=booking.property_id,
            entity_type='booking',
            entity_id=booking.id,
        )
        return

    issues = []
    if float(booking.balance_due or 0.0) > 0.009:
        issues.append('balance still due')

    if not getattr(booking, 'room_id', None):
        issues.append('room not assigned')
    else:
        room = Room.query.filter_by(id=booking.room_id, property_id=booking.property_id).first()
        ready_ids = {
            Constants.RoomCleaningStatusCoding['Ready'],
            Constants.RoomCleaningStatusCoding['Clean'],
        }
        if room and room.cleaning_status_id not in ready_ids:
            issues.append(f"room {room.room_number} is not ready")

    if not issues:
        clear_notifications(
            notification_type=NotificationType.ARRIVAL_ISSUE,
            property_id=booking.property_id,
            entity_type='booking',
            entity_id=booking.id,
        )
        return

    notify_property_staff(
        property_id=booking.property_id,
        required_permissions={'manage_bookings'},
        notification_type=NotificationType.ARRIVAL_ISSUE,
        title='Arrival issue today',
        body=f"{_booking_display_name(booking)} {_booking_reference(booking)}: {', '.join(issues)}.",
        routing='booking',
        entity_type='booking',
        entity_id=booking.id,
    )


def notify_guest_message_received(message):
    guest_name = _booking_display_name(message.booking) if message.booking else f'Booking #{message.booking_id}'
    notify_property_staff(
        property_id=message.property_id,
        required_permissions={'manage_bookings'},
        notification_type=NotificationType.GUEST_MESSAGE,
        title='New guest message',
        body=f"{guest_name} sent a new {message.channel} message.",
        routing='booking',
        entity_type='booking',
        entity_id=message.booking_id,
    )


def notify_guest_message_failed(message):
    guest_name = _booking_display_name(message.booking) if message.booking else f'Booking #{message.booking_id}'
    notify_property_staff(
        property_id=message.property_id,
        required_permissions={'manage_bookings'},
        notification_type=NotificationType.GUEST_MESSAGE_FAILED,
        title='Guest message delivery failed',
        body=f"Could not deliver the {message.channel} message for {guest_name}.",
        routing='booking',
        entity_type='guest_message',
        entity_id=message.id,
    )


def notify_payment_failed(booking, transaction):
    amount = f"{float(transaction.amount or 0.0):.2f}"
    notify_property_staff(
        property_id=booking.property_id,
        required_permissions={'view_finance'},
        notification_type=NotificationType.PAYMENT_FAILED,
        title='Payment failed',
        body=f"Payment of {amount} {transaction.currency.upper()} failed for {_booking_display_name(booking)} {_booking_reference(booking)}.",
        routing='invoices',
        entity_type='transaction',
        entity_id=transaction.id,
    )


def notify_operations_issue(
    *,
    property_id,
    title,
    body,
    routing,
    entity_type,
    entity_id,
    required_permissions,
):
    notify_property_staff(
        property_id=property_id,
        required_permissions=required_permissions,
        notification_type=NotificationType.OPERATIONS_ISSUE,
        title=title,
        body=body,
        routing=routing,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def notify_overbooking_issue(*, property_id, room_id, check_in, check_out):
    entity_id = f"{room_id}:{check_in}:{check_out}"
    notify_operations_issue(
        property_id=property_id,
        title='Inventory conflict detected',
        body=f"Room {room_id} is already booked between {check_in} and {check_out}.",
        routing='booking',
        entity_type='inventory_conflict',
        entity_id=entity_id,
        required_permissions={'manage_bookings'},
    )


def notify_channel_sync_issue(job, error_message):
    title = 'Channel sync issue'
    body = f"{job.channel_code} {job.job_type} failed: {error_message or 'Unknown error'}."
    notify_operations_issue(
        property_id=job.property_id,
        title=title,
        body=body,
        routing='channel_manager',
        entity_type='channel_job',
        entity_id=job.id,
        required_permissions={'manage_channels'},
    )
