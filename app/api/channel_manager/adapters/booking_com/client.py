import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BookingComClient:
    def __init__(self, connection):
        self.connection = connection
        self.credentials = connection.credentials_json or {}
        self.settings = connection.settings_json or {}

        self.base_url = (self.settings.get('base_url') or '').rstrip('/')
        self.username = self.credentials.get('username')
        self.password = self.credentials.get('password')
        self.hotel_id = self.credentials.get('hotel_id')

        # Setup a resilient session with automatic retries for transient failures
        self.session = self._build_resilient_session()

    def _build_resilient_session(self) -> requests.Session:
        session = requests.Session()
        # Retry on 500, 502, 503, 504 errors up to 3 times with backoff
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        # Inject standard auth and headers
        session.auth = (self.username, self.password)
        session.headers.update(self._xml_headers())
        return session

    @staticmethod
    def _xml_headers():
        return {
            'Content-Type': 'application/xml',
            'Accept': 'application/xml',
        }

    def send_request(self, endpoint: str, payload: str, method: str = 'POST') -> str:
        """
        Generic resilient request sender used for fetching configurations (Rooms/Rates).
        """
        url = f'{self.base_url}/{endpoint.lstrip("/")}'

        try:
            response = self.session.request(
                method=method,
                url=url,
                data=payload,
                timeout=(5.0, 15.0)  # 5s connect timeout, 15s read timeout
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"[Booking.com] API Request failed for {url}: {str(e)}", exc_info=True)
            raise

    # --- Existing Methods Updated to use Resilient Session ---

    def send_ari(self, xml_payload: str) -> dict:
        url = f'{self.base_url}/ari'
        try:
            response = self.session.post(url, data=xml_payload, timeout=(5.0, 25.0))
            return {
                'success': response.ok,
                'status_code': response.status_code,
                'body': response.text,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[Booking.com] ARI push failed: {str(e)}")
            return {'success': False, 'status_code': 500, 'body': str(e)}

    def fetch_reservations(self, cursor: dict | None = None) -> dict:
        url = f'{self.base_url}/reservations'
        params = cursor or {}
        try:
            response = self.session.get(url, params=params, timeout=(5.0, 25.0))
            return {
                'success': response.ok,
                'status_code': response.status_code,
                'body': response.text,
                'next_cursor': None,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[Booking.com] Fetch reservations failed: {str(e)}")
            return {'success': False, 'status_code': 500, 'body': str(e), 'next_cursor': None}

    def acknowledge_reservation(self, external_reservation_id: str, payload: dict | None = None) -> dict:
        url = f'{self.base_url}/reservations/{external_reservation_id}/ack'
        try:
            # Note: Overriding content-type specifically for this JSON request if needed
            response = self.session.post(
                url,
                json=payload or {},
                headers={'Content-Type': 'application/json'},
                timeout=(5.0, 15.0)
            )
            return {
                'success': response.ok,
                'status_code': response.status_code,
                'body': response.text,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[Booking.com] ACK reservation failed: {str(e)}")
            return {'success': False, 'status_code': 500, 'body': str(e)}