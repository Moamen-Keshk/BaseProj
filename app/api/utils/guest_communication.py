from app.api.email import send_email
from app.celery_app import celery
from app.api.models import Booking, Property

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