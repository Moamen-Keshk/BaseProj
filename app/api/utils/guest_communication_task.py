from app.api.email import send_email
from app.celery_app import celery
from app.api.models import Booking, Property
import os
from twilio.rest import Client

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
def send_guest_message(email, subject, message_body, property_id, first_name, last_name):
    # The background worker does the heavy lifting and DB querying
    property_obj = Property.query.get(property_id)

    send_email(
        to=email,
        subject=subject,
        template="mail/guest_custom_message",
        property=property_obj,
        first_name=first_name,
        last_name=last_name,
        message_body=message_body
    )


@celery.task
def send_sms_whatsapp_task(booking_id, message_body, channel='whatsapp'):
    booking = Booking.query.get(booking_id)
    if not booking or not booking.phone:
        return "No phone number available"

    account_sid = os.environ['TWILIO_ACCOUNT_SID']
    auth_token = os.environ['TWILIO_AUTH_TOKEN']
    client = Client(account_sid, auth_token)

    prefix = "whatsapp:" if channel == 'whatsapp' else ""
    from_number = os.environ['TWILIO_WHATSAPP_NUMBER'] if channel == 'whatsapp' else os.environ['TWILIO_SMS_NUMBER']
    to_number = f"{prefix}{booking.phone}"

    # ONLY handle the Twilio delivery here. The DB write was already handled!
    message = client.messages.create(
        body=message_body,
        from_=f"{prefix}{from_number}",
        to=to_number
    )

    return message.sid