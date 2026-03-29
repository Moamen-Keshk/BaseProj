# app/api/channel_manager/adapters/dummy_adapter.py
from app.api.channel_manager.adapters.base import BaseChannelAdapter

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
        Returns a mock dictionary of reservations.
        We return an empty list to ensure your background pull jobs run successfully without crashing.
        """
        print(f"🧪 [MOCK OTA] Pulling reservations for property {connection.property_id}. Cursor: {cursor}")
        return {
            "reservations": [],
            "next_cursor": None
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