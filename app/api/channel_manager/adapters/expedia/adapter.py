from app.api.channel_manager.adapters.base import BaseChannelAdapter


class ExpediaAdapter(BaseChannelAdapter):
    channel_code = 'expedia'

    def validate_connection(self, connection) -> list[str]:
        errors = []
        credentials = connection.credentials_json or {}

        if not credentials.get('property_id'):
            errors.append('Missing Expedia property_id')
        if not credentials.get('username'):
            errors.append('Missing Expedia username')
        if not credentials.get('password'):
            errors.append('Missing Expedia password')

        return errors

    def push_ari(self, connection, ari_updates: list[dict]) -> dict:
        return {
            'success': True,
            'request_body': None,
            'response_body': None,
            'http_status': 201,
            'count': len(ari_updates),
        }

    def pull_reservations(self, connection, cursor: dict | None = None) -> dict:
        return {
            'reservations': [],
            'next_cursor': None,
            'raw_body': None,
            'http_status': 201,
        }

    def acknowledge_reservation(
        self,
        connection,
        external_reservation_id: str,
        payload: dict | None = None,
    ) -> dict:
        return {
            'success': True,
            'response_body': None,
            'http_status': 201,
        }

    def fetch_external_rooms(self, connection) -> list[dict]:
        # TODO: Implement Expedia Product API call to fetch RoomTypes
        return [
            {"id": "EXP-RM-201", "name": "Standard Room", "capacity": 2},
            {"id": "EXP-RM-202", "name": "Executive Suite", "capacity": 3}
        ]

    def fetch_external_rate_plans(self, connection) -> list[dict]:
        # TODO: Implement Expedia Product API call to fetch RatePlans
        return [
            {"id": "EXP-RP-1", "name": "Standard Rate", "pricing_model": "OccupancyBased"},
            {"id": "EXP-RP-2", "name": "Bed & Breakfast", "pricing_model": "OccupancyBased"}
        ]