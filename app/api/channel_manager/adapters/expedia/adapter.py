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
            'http_status': 200,
            'count': len(ari_updates),
        }

    def pull_reservations(self, connection, cursor: dict | None = None) -> dict:
        return {
            'reservations': [],
            'next_cursor': None,
            'raw_body': None,
            'http_status': 200,
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
            'http_status': 200,
        }