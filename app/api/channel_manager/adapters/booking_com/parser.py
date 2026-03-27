from datetime import datetime
from decimal import Decimal


class BookingComParser:
    @staticmethod
    def parse_reservations(property_id: int, raw_response: str) -> list[dict]:
        # Replace this stub with real XML parsing once endpoint structure is finalized.
        # Returning an empty list keeps the pipeline stable while you build the transport layer.
        return []

    @staticmethod
    def build_reservation_payload(
        property_id: int,
        external_reservation_id: str,
        checkin_date: str,
        checkout_date: str,
        guest_name: str | None = None,
        guest_email: str | None = None,
        total_amount: str | None = None,
        currency: str | None = None,
        external_room_id: str | None = None,
        external_rate_plan_id: str | None = None,
        status: str = "new",
        external_version: str | None = None,
        raw_payload: dict | str | None = None,
    ) -> dict:
        return {
            "channel_code": "booking_com",
            "external_reservation_id": external_reservation_id,
            "external_version": external_version,
            "property_id": property_id,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "checkin_date": datetime.fromisoformat(checkin_date).date(),
            "checkout_date": datetime.fromisoformat(checkout_date).date(),
            "total_amount": Decimal(total_amount) if total_amount is not None else None,
            "currency": currency,
            "external_room_id": external_room_id,
            "external_rate_plan_id": external_rate_plan_id,
            "status": status,
            "raw_payload": raw_payload or {},
        }