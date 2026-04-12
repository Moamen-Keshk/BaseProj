import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ExpediaClient:
    def __init__(self, connection):
        self.connection = connection
        self.credentials = connection.credentials_json or {}
        self.settings = connection.settings_json or {}

        # Defaulting to Expedia's generic EPS/EQC base URL if not provided in settings
        self.base_url = (self.settings.get('base_url') or 'https://services.expediapartnercentral.com').rstrip('/')
        self.username = self.credentials.get('username')
        self.password = self.credentials.get('password')
        self.property_id = self.credentials.get('property_id')

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

        # Inject standard auth and JSON headers
        session.auth = (self.username, self.password)
        session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        return session

    def send_request(self, endpoint: str, method: str = 'GET', payload: dict | None = None,
                     params: dict | None = None) -> dict | list:
        """
        Generic resilient request sender used for fetching configurations (Rooms/Rates) from Expedia.
        Expects and returns JSON.
        """
        url = f'{self.base_url}/{endpoint.lstrip("/")}'

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=payload,
                params=params,
                timeout=(5.0, 15.0)  # 5s connect timeout, 15s read timeout
            )
            response.raise_for_status()

            # Expedia returns 204 No Content for some successful updates (like ARI)
            if response.status_code == 204:
                return {}

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"[Expedia] API Request failed for {url}: {str(e)}", exc_info=True)
            raise