import logging
from app.api.exceptions import ChannelIntegrationError

logger = logging.getLogger(__name__)


class ExpediaParser:
    @staticmethod
    def _check_for_faults(json_data: dict | list):
        """Helper to catch Expedia JSON error payloads."""
        if isinstance(json_data, dict) and 'errors' in json_data:
            error_details = ", ".join([err.get('message', 'Unknown Error') for err in json_data.get('errors', [])])
            raise ChannelIntegrationError(f"Expedia API returned an error: {error_details}")

    @staticmethod
    def parse_rooms_response(json_data: dict | list) -> list[dict]:
        """
        Parses the JSON response to extract room external IDs and names.
        Expected generic return format: [{'external_id': 'EXP-RM-1', 'external_name': 'Double Room'}, ...]
        """
        ExpediaParser._check_for_faults(json_data)

        external_rooms = []
        try:
            # Expedia API often wraps entities in a list or an 'entity' key
            rooms_list = json_data.get('entity', []) if isinstance(json_data, dict) else json_data

            for room in rooms_list:
                # Adjust keys ('resourceId', 'id', 'roomTypeId') based on exact Expedia API version
                room_id = room.get('resourceId') or room.get('id') or room.get('roomTypeId')
                room_name = room.get('name') or room.get('roomTypeName') or f"Room {room_id}"

                if room_id:
                    external_rooms.append({
                        'external_id': str(room_id).strip(),
                        'external_name': str(room_name).strip()
                    })

            return external_rooms

        except Exception as e:
            logger.error(f"[Expedia] Failed to parse Rooms JSON: {str(e)}\nPayload: {json_data}")
            raise ChannelIntegrationError("Invalid JSON response received from Expedia when fetching rooms.") from e

    @staticmethod
    def parse_rate_plans_response(json_data: dict | list) -> list[dict]:
        """
        Parses the JSON response to extract rate plan external IDs and names.
        Expected generic return format: [{'external_id': 'EXP-RP-1', 'external_name': 'Standard Rate'}, ...]
        """
        ExpediaParser._check_for_faults(json_data)

        external_rate_plans = []
        try:
            # Expedia API often wraps entities in a list or an 'entity' key
            rp_list = json_data.get('entity', []) if isinstance(json_data, dict) else json_data

            for rp in rp_list:
                # Adjust keys based on exact Expedia API version
                rp_id = rp.get('resourceId') or rp.get('id') or rp.get('ratePlanId')
                rp_name = rp.get('name') or rp.get('ratePlanName') or f"RatePlan {rp_id}"

                if rp_id:
                    external_rate_plans.append({
                        'external_id': str(rp_id).strip(),
                        'external_name': str(rp_name).strip()
                    })

            return external_rate_plans

        except Exception as e:
            logger.error(f"[Expedia] Failed to parse Rate Plans JSON: {str(e)}\nPayload: {json_data}")
            raise ChannelIntegrationError(
                "Invalid JSON response received from Expedia when fetching rate plans.") from e