from app.api.channel_manager.adapters.base import BaseChannelAdapter
from app.api.channel_manager.adapters.booking_com.client import BookingComClient
from app.api.channel_manager.adapters.booking_com.mapper import BookingComMapper
from app.api.channel_manager.adapters.booking_com.parser import BookingComParser
from app.api.exceptions import ChannelIntegrationError
import logging

logger = logging.getLogger(__name__)


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
        """
        Fetches the list of rooms configured on Booking.com for this property connection.

        :param connection: ChannelConnection instance containing credentials and hotel config.
        :return: A list of dicts with 'external_id' and 'external_name'.
        """
        logger.info(f"[Booking.com] Fetching external rooms for connection {connection.id}")

        try:
            client = BookingComClient(connection)

            # 1. Build the XML/JSON request payload using the mapper
            request_payload = BookingComMapper.build_room_request(connection)

            # 2. Send the request via the client (e.g., to OTA_HotelDescriptiveInfo or B.XML endpoint)
            response_content = client.send_request(
                endpoint="hotels/xml/rooms",  # Update to actual endpoint path
                payload=request_payload
            )

            # 3. Parse the response
            external_rooms = BookingComParser.parse_rooms_response(response_content)

            logger.info(
                f"[Booking.com] Successfully fetched {len(external_rooms)} rooms for connection {connection.id}")
            return external_rooms

        except Exception as e:
            logger.error(
                f"[Booking.com] Failed to fetch external rooms for connection {connection.id}. Error: {str(e)}",
                exc_info=True
            )
            raise ChannelIntegrationError(f"Failed to retrieve rooms from Booking.com: {str(e)}") from e

    def fetch_external_rate_plans(self, connection) -> list[dict]:
        """
        Fetches the list of rate plans configured on Booking.com for this property connection.

        :param connection: ChannelConnection instance.
        :return: A list of dicts with 'external_id' and 'external_name'.
        """
        logger.info(f"[Booking.com] Fetching external rate plans for connection {connection.id}")

        try:
            client = BookingComClient(connection)

            # 1. Build the payload
            request_payload = BookingComMapper.build_rate_plan_request(connection)

            # 2. Send the request
            response_content = client.send_request(
                endpoint="hotels/xml/rateplans",  # Update to actual endpoint path
                payload=request_payload
            )

            # 3. Parse the response
            external_rate_plans = BookingComParser.parse_rate_plans_response(response_content)

            logger.info(
                f"[Booking.com] Successfully fetched {len(external_rate_plans)} rate plans for connection {connection.id}")
            return external_rate_plans

        except Exception as e:
            logger.error(
                f"[Booking.com] Failed to fetch external rate plans for connection {connection.id}. Error: {str(e)}",
                exc_info=True
            )
            raise ChannelIntegrationError(f"Failed to retrieve rate plans from Booking.com: {str(e)}") from e