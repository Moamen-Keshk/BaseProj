from app.api.email import send_email
from app.celery_app import celery
from app import db
from app.api.models import Booking, Property, GuestMessage
from app.api.invoice_rendering import build_invoice_template_context
from app.api.payments.services import sync_invoice_for_booking
from app.api.utils.notifications import notify_guest_message_failed
import os
from twilio.rest import Client


def _update_message_status(message_id, status, error=None, external_message_id=None):
    message_log = GuestMessage.query.get(message_id)
    if not message_log:
        return

    message_log.delivery_status = status
    message_log.delivery_error = error
    if external_message_id:
        message_log.external_message_id = external_message_id
    if status == 'failed':
        notify_guest_message_failed(message_log)
    db.session.commit()


@celery.task
def send_booking_email_task(booking_id, property_id):
    # The background worker does the heavy lifting and DB querying
    booking = Booking.query.get(booking_id)
    property_obj = Property.query.get(property_id)

    send_email(
        to=booking.email,
        subject=f"Booking Confirmation - #{booking.confirmation_number} DO NOT REPLY",
        template="mail/guest_confirmation",
        booking=booking,
        property=property_obj
    )

@celery.task
def send_guest_message(message_id, email, subject, message_body, property_id, first_name, last_name):
    # The background worker does the heavy lifting and DB querying
    property_obj = Property.query.get(property_id)

    try:
        send_email(
            to=email,
            subject=subject,
            template="mail/guest_custom_message",
            property=property_obj,
            first_name=first_name,
            last_name=last_name,
            message_body=message_body
        )
        _update_message_status(message_id, 'sent')
    except Exception as exc:
        _update_message_status(message_id, 'failed', str(exc))
        raise


@celery.task
def send_invoice_email_task(message_id, booking_id, property_id, recipient_email, subject, custom_message=None):
    booking = Booking.query.get(booking_id)
    property_obj = Property.query.get(property_id)

    if not booking or not recipient_email:
        _update_message_status(message_id, 'failed', 'Booking or recipient email not found.')
        return "Booking or recipient email not found."

    invoice = getattr(booking, 'invoice', None)
    if invoice is None:
        invoice = sync_invoice_for_booking(booking)
        db.session.commit()

    try:
        send_email(
            to=recipient_email,
            subject=subject,
            template="mail/invoice_email",
            **build_invoice_template_context(
                booking,
                invoice,
                property_obj=property_obj,
                custom_message=custom_message,
            ),
        )
        _update_message_status(message_id, 'sent')
    except Exception as exc:
        _update_message_status(message_id, 'failed', str(exc))
        raise


@celery.task
def send_sms_whatsapp_task(message_id, booking_id, message_body, channel='whatsapp'):
    booking = Booking.query.get(booking_id)
    if not booking or not booking.phone:
        _update_message_status(message_id, 'failed', 'No phone number available')
        return "No phone number available"

    if channel not in {'whatsapp', 'sms'}:
        _update_message_status(message_id, 'failed', f'Unsupported channel: {channel}')
        return "Unsupported channel"

    account_sid = os.environ['TWILIO_ACCOUNT_SID']
    auth_token = os.environ['TWILIO_AUTH_TOKEN']
    client = Client(account_sid, auth_token)

    prefix = "whatsapp:" if channel == 'whatsapp' else ""
    from_number = os.environ['TWILIO_WHATSAPP_NUMBER'] if channel == 'whatsapp' else os.environ['TWILIO_SMS_NUMBER']
    to_number = f"{prefix}{booking.phone}"

    try:
        message = client.messages.create(
            body=message_body,
            from_=f"{prefix}{from_number}",
            to=to_number
        )
    except Exception as exc:
        _update_message_status(message_id, 'failed', str(exc))
        raise

    _update_message_status(message_id, 'sent', external_message_id=message.sid)
    return message.sid
