from celery import shared_task
from adapters.booking_com_adapter import BookingComAdapter
from app.api.models import RoomOnline

from datetime import datetime, timedelta
from utils import log_sync_status

from services.reservation_service import ReservationService


def log_sync(param, status, msg):
    pass


def get_ota_rate_id(rate_plan_id):
    return 1


@shared_task
def sync_rates_to_booking_com():
    adapter = BookingComAdapter(hotel_id='12345', username='user', password='pass')

    for rate in RoomOnline.query.filter_by(channel_sync=True):
        ota_rate_id = get_ota_rate_id(rate.rate_plan_id)
        status, msg = adapter.push_rate(ota_rate_id, rate.date.isoformat(), rate.amount)
        log_sync('rate', status, msg)

@shared_task
def fetch_bookings_from_booking_com():
    try:
        # Use your own method of retrieving last_sync_time per property
        last_sync_time = datetime.utcnow() - timedelta(hours=1)

        adapter = BookingComAdapter(
            hotel_id="123456",
            username="your_user",
            password="your_password"
        )

        bookings = adapter.fetch_bookings(last_sync_time)

        for booking in bookings:
            try:
                ReservationService.create_from_ota(booking, "booking.com")
            except Exception as e:
                # Log per-booking error
                print(f"[Booking Sync Error] {booking['booking_id']}: {e}")

        # (Optional) Update last_sync_time in DB
        # db.session.commit()

        # Log successful sync
        log_sync_status("booking.com", "booking", "success")

    except Exception as e:
        log_sync_status("booking.com", "booking", "error", str(e))
