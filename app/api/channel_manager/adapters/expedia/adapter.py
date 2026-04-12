import logging
from app.api.channel_manager.adapters.base import BaseChannelAdapter
from app.api.channel_manager.adapters.expedia.client import ExpediaClient
from app.api.channel_manager.adapters.expedia.mapper import ExpediaMapper
from app.api.channel_manager.adapters.expedia.parser import ExpediaParser
from app.api.exceptions import ChannelIntegrationError

logger = logging.getLogger(__name__)


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
        """
        Fetches the list of room types configured on Expedia for this property.

        :param connection: ChannelConnection instance.
        :return: A list of dicts with 'external_id' and 'external_name'.
        """
        logger.info(f"[Expedia] Fetching external rooms for connection {connection.id}")

        try:
            client = ExpediaClient(connection)

            # Expedia's Product API typically uses GET requests, mapper can handle query params/headers
            request_params = ExpediaMapper.build_room_request(connection)

            # Send the request
            response_content = client.send_request(
                endpoint=f"products/properties/{client.property_id}/roomTypes",
                method='GET',
                params=request_params
            )

            # Parse the JSON response
            external_rooms = ExpediaParser.parse_rooms_response(response_content)

            logger.info(f"[Expedia] Successfully fetched {len(external_rooms)} rooms for connection {connection.id}")
            return external_rooms

        except Exception as e:
            logger.error(
                f"[Expedia] Failed to fetch external rooms for connection {connection.id}. Error: {str(e)}",
                exc_info=True
            )
            raise ChannelIntegrationError(f"Failed to retrieve rooms from Expedia: {str(e)}") from e

    def fetch_external_rate_plans(self, connection) -> list[dict]:
        """
        Fetches the list of rate plans configured on Expedia for this property.

        :param connection: ChannelConnection instance.
        :return: A list of dicts with 'external_id' and 'external_name'.
        """
        logger.info(f"[Expedia] Fetching external rate plans for connection {connection.id}")

        try:
            client = ExpediaClient(connection)

            request_params = ExpediaMapper.build_rate_plan_request(connection)

            # Send the request
            response_content = client.send_request(
                endpoint=f"products/properties/{client.property_id}/ratePlans",
                method='GET',
                params=request_params
            )

            # Parse the JSON response
            external_rate_plans = ExpediaParser.parse_rate_plans_response(response_content)

            logger.info(
                f"[Expedia] Successfully fetched {len(external_rate_plans)} rate plans for connection {connection.id}")
            return external_rate_plans

        except Exception as e:
            logger.error(
                f"[Expedia] Failed to fetch external rate plans for connection {connection.id}. Error: {str(e)}",
                exc_info=True
            )
            raise ChannelIntegrationError(f"Failed to retrieve rate plans from Expedia: {str(e)}") from e