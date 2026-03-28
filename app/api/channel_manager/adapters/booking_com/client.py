import requests


class BookingComClient:
    def __init__(self, connection):
        self.connection = connection
        self.credentials = connection.credentials_json or {}
        self.settings = connection.settings_json or {}

        self.base_url = (self.settings.get('base_url') or '').rstrip('/')
        self.username = self.credentials.get('username')
        self.password = self.credentials.get('password')
        self.hotel_id = self.credentials.get('hotel_id')

    @staticmethod
    def _xml_headers():
        return {
            'Content-Type': 'application/xml',
        }

    def send_ari(self, xml_payload: str) -> dict:
        url = f'{self.base_url}/ari'

        response = requests.post(
            url,
            data=xml_payload,
            headers=self._xml_headers(),
            auth=(self.username, self.password),
            timeout=60,
        )

        return {
            'success': response.ok,
            'status_code': response.status_code,
            'body': response.text,
        }

    def fetch_reservations(self, cursor: dict | None = None) -> dict:
        url = f'{self.base_url}/reservations'
        params = cursor or {}

        response = requests.get(
            url,
            params=params,
            auth=(self.username, self.password),
            timeout=60,
        )

        return {
            'success': response.ok,
            'status_code': response.status_code,
            'body': response.text,
            'next_cursor': None,
        }

    def acknowledge_reservation(self, external_reservation_id: str, payload: dict | None = None) -> dict:
        url = f'{self.base_url}/reservations/{external_reservation_id}/ack'

        response = requests.post(
            url,
            json=payload or {},
            auth=(self.username, self.password),
            timeout=60,
        )

        return {
            'success': response.ok,
            'status_code': response.status_code,
            'body': response.text,
        }