from app.api.channel_manager.adapters.base import BaseChannelAdapter
import uuid
from datetime import datetime, timedelta


class DummyAdapter(BaseChannelAdapter):
    """
    A fake adapter to test the PMS mapping and sync jobs without needing real OTA credentials.
    """
    channel_code = 'dummy_ota'

    def validate_connection(self, connection) -> list[str]:
        """
        Returns a list of error strings. An empty list means the connection is valid.
        """
        print(f"🧪 [MOCK OTA] Validating connection for property {connection.property_id}")
        # Always approve the credentials
        return []

    def push_ari(self, connection, ari_updates: list[dict]) -> dict:
        """
        Pretends to push Availability, Rates, and Inventory.
        """
        print(f"🧪 [MOCK OTA] ARI Push successful for property {connection.property_id}. Updates: {len(ari_updates)}")
        return {
            "status": "success",
            "processed_count": len(ari_updates)
        }

    def pull_reservations(self, connection, cursor: dict | None = None) -> dict:
        """
        Returns a mock dictionary containing a fake reservation.
        Every time this is called, it pretends a new guest just booked a room!
        """
        print(f"🧪 [MOCK OTA] Pulling reservations for property {connection.property_id}")

        # Generate a random 6-character booking reference (e.g., DUMMY-A1B2C3)
        fake_res_id = f"DUMMY-{uuid.uuid4().hex[:6].upper()}"

        # Calculate fake dates (Check-in today, Check-out in 2 days)
        check_in = datetime.now().strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

        # Mimic a standard OTA JSON payload with VCC details included
        fake_reservation = {
            "external_reservation_id": fake_res_id,
            "status": "confirmed",
            "guest": {
                "first_name": "John",
                "last_name": "Doe (VCC Test)",
                "email": "john.test@dummyota.com",
                "phone": "+15551234567"
            },
            "room_stays": [
                {
                    # IMPORTANT: This must match the ID of a room you mapped in Flutter!
                    "external_room_id": "DUMMY-RM-01",
                    "external_rate_plan_id": "DUMMY-RP-02",
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "guests": 2,
                    "price": 250.00,
                    "currency": "GBP"
                }
            ],
            "total_price": 250.00,
            "currency": "GBP",
            "booked_at": datetime.now().isoformat(),

            # 👇 NEW: The injected VCC Details
            "payment_card": {
                "card_type": "Virtual Credit Card",
                "card_holder": "Dummy OTA VCC",
                "card_number": "5555444433332222",  # Test Card
                "expiration_month": "12",
                "expiration_year": "2028",
                "cvc": "123",
                "is_virtual": True
            }
        }

        return {
            "reservations": [fake_reservation],
            "next_cursor": None  # No more pages of reservations to fetch
        }

    def acknowledge_reservation(
            self,
            connection,
            external_reservation_id: str,
            payload: dict | None = None,
    ) -> dict:
        """
        Pretends to tell the OTA that we successfully saved the reservation in our PMS.
        """
        print(f"🧪 [MOCK OTA] Acknowledged reservation: {external_reservation_id}")
        return {
            "status": "success",
            "acknowledged_id": external_reservation_id
        }

    def fetch_external_rooms(self, connection) -> list[dict]:
        """
        Returns fake OTA rooms so your Flutter UI mapping dropdowns have data to display.
        """
        return [
            {"id": "DUMMY-RM-01", "name": "Fake Standard Room"},
            {"id": "DUMMY-RM-02", "name": "Fake Deluxe Suite"},
            {"id": "DUMMY-RM-03", "name": "Fake Ocean View"}
        ]

    def fetch_external_rate_plans(self, connection) -> list[dict]:
        """
        Returns fake Rate Plans for your Flutter UI mapping dropdowns.
        """
        return [
            {"id": "DUMMY-RP-01", "name": "Non-Refundable Fake Rate"},
            {"id": "DUMMY-RP-02", "name": "Standard Fake Rate (Breakfast Inc)"}
        ]