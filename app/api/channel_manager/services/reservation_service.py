from app.api.channel_manager.models import OTARoomMapping
from datetime import datetime, timedelta
from app.api.models import RoomOnline, Booking
from app import db

class ReservationService:

    @staticmethod
    def create_from_ota(booking: dict, ota_name: str):
        ota_room_id = booking["ota_room_id"]
        checkin = datetime.strptime(booking["checkin"], "%Y-%m-%d").date()
        checkout = datetime.strptime(booking["checkout"], "%Y-%m-%d").date()

        # 1. Map OTA room to local room
        mapping = OTARoomMapping.query.filter_by(
            ota_name=ota_name,
            ota_room_id=ota_room_id,
            active=True
        ).first()
        if not mapping:
            raise Exception(f"Room mapping not found for OTA room {ota_room_id}")

        local_room_id = mapping.local_room_id

        # 2. Prevent duplicates (idempotent)
        existing = Booking.query.filter_by(
            external_id=booking["booking_id"],
            source=ota_name
        ).first()
        if existing:
            return existing  # Already exists

        # 3. Create or find guest
    #    guest = Guest.query.filter_by(name=booking["guest_name"]).first()
    #    if not guest:
    #        guest = Guest(name=booking["guest_name"])
    #        db.session.add(guest)
    #        db.session.flush()  # get guest.id

        # 4. Create reservation
        reservation = Booking(
        #    guest_id=guest.id,
            room_id=local_room_id,
            checkin_date=checkin,
            checkout_date=checkout,
            total_price=booking["total_price"],
            currency=booking["currency"],
            source=ota_name,
            external_id=booking["booking_id"]
        )
        db.session.add(reservation)

        # 5. Block RoomOnline dates
        current = checkin
        while current < checkout:
            ro = RoomOnline.query.filter_by(room_id=local_room_id, date=current).first()
            if ro:
                ro.status_id = 2  # 2 = Booked or Reserved
                ro.booking_id = reservation.id
            else:
                ro = RoomOnline(
                    room_id=local_room_id,
                    date=current,
                    status_id=2,
                    booking_id=reservation.id
                )
                db.session.add(ro)
            current += timedelta(days=1)

        db.session.commit()
        return reservation
