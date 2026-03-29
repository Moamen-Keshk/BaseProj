from app.api.channel_manager.adapters.base import BaseChannelAdapter
from app.api.channel_manager.adapters.booking_com.client import BookingComClient
from app.api.channel_manager.adapters.booking_com.mapper import BookingComMapper
from app.api.channel_manager.adapters.booking_com.parser import BookingComParser


class BookingComAdapter(BaseChannelAdapter):
    channel_code = 'booking_com'

    def validate_connection(self, connection) -> list[str]:
        errors = []
        credentials = connection.credentials_json or {}

        if not credentials.get('hotel_id'):
            errors.append('Missing Booking.com hotel_id')
        if not credentials.get('username'):
            errors.append('Missing Booking.com username')
        if not credentials.get('password'):
            errors.append('Missing Booking.com password')

        return errors

    def push_ari(self, connection, ari_updates: list[dict]) -> dict:
        xml_payload = BookingComMapper.build_ari_xml(connection, ari_updates)
        client = BookingComClient(connection)
        response = client.send_ari(xml_payload)

        return {
            'success': response.get('success', False),
            'request_body': xml_payload,
            'response_body': response.get('body'),
            'http_status': response.get('status_code'),
            'count': len(ari_updates),
        }

    def pull_reservations(self, connection, cursor: dict | None = None) -> dict:
        client = BookingComClient(connection)
        raw_response = client.fetch_reservations(cursor=cursor)

        reservations = BookingComParser.parse_reservation(
            xml_string=raw_response.get('body') or '',
            property_id=connection.property_id
        )

        return {
            'reservations': reservations,
            'next_cursor': raw_response.get('next_cursor'),
            'raw_body': raw_response.get('body'),
            'http_status': raw_response.get('status_code'),
        }

    def acknowledge_reservation(
        self,
        connection,
        external_reservation_id: str,
        payload: dict | None = None,
    ) -> dict:
        client = BookingComClient(connection)
        response = client.acknowledge_reservation(
            external_reservation_id=external_reservation_id,
            payload=payload,
        )

        return {
            'success': response.get('success', False),
            'response_body': response.get('body'),
            'http_status': response.get('status_code'),
        }

    def fetch_external_rooms(self, connection) -> list[dict]:
        # TODO: Implement actual Booking.com API call (e.g., RoomList request)
        # Mocking the response for your frontend UI mapping dropdowns
        return [
            {"id": "1001", "name": "Standard Double Room", "capacity": 2},
            {"id": "1002", "name": "Deluxe King Suite", "capacity": 2},
            {"id": "1003", "name": "Family Room with Sea View", "capacity": 4}
        ]

    def fetch_external_rate_plans(self, connection) -> list[dict]:
        # TODO: Implement actual Booking.com API call (e.g., RatePlanList request)
        return [
            {"id": "BAR", "name": "Best Available Rate", "pricing_model": "PerDay"},
            {"id": "NRF", "name": "Non-Refundable Rate", "pricing_model": "PerDay"}
        ]