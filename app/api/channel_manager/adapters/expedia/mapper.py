from typing import Any


class ExpediaMapper:
    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'true', '1', 'yes', 'y'}
        return bool(value)

    @staticmethod
    def build_room_request(_connection) -> dict:
        """
        Builds the query parameters for requesting configured rooms for the hotel.
        For Expedia, the property ID is passed in the URL (handled by the client),
        so we only return URL query params here.
        """
        params = {
            'status': 'Active',
        }
        return params

    @staticmethod
    def build_rate_plan_request(_connection) -> dict:
        """
        Builds the query parameters for requesting configured rate plans for the hotel.
        """
        params = {
            'status': 'Active',
        }
        return params

    @staticmethod
    def build_ari_json(_connection, ari_updates: list[dict]) -> list[dict[str, Any]]:
        """
        Builds the JSON payload to push Availability, Rates, and Inventory (ARI) to Expedia.
        Expedia's Availability and Rates API expects a JSON array of update objects.

        :param _connection: ChannelConnection instance. Unused for Expedia payload construction.
        :param ari_updates: Generic list of dicts from the PMS channel manager engine.
        :return: JSON serializable list of dictionaries.
        """
        payload: list[dict[str, Any]] = []

        for update in ari_updates:
            item: dict[str, Any] = {
                "roomTypeId": str(update['room_id']),
                "dates": [str(update['stay_date'])],
            }

            rate_plan_id = update.get('rate_plan_id')
            if rate_plan_id is not None:
                item["ratePlanId"] = str(rate_plan_id)

            if update.get('availability') is not None:
                item["inventory"] = int(update['availability'])

            if update.get('amount') is not None:
                item["rates"] = [
                    {
                        "amount": float(update['amount'])
                    }
                ]

            restrictions: dict[str, Any] = {}
            if update.get('min_los') is not None:
                restrictions["minLOS"] = int(update['min_los'])
            if update.get('max_los') is not None:
                restrictions["maxLOS"] = int(update['max_los'])
            if update.get('closed_to_arrival') is not None:
                restrictions["closedToArrival"] = ExpediaMapper._to_bool(update['closed_to_arrival'])
            if update.get('closed_to_departure') is not None:
                restrictions["closedToDeparture"] = ExpediaMapper._to_bool(update['closed_to_departure'])
            if restrictions:
                item["restrictions"] = restrictions

            if update.get('closed') is not None:
                item["status"] = "Closed" if ExpediaMapper._to_bool(update['closed']) else "Open"

            payload.append(item)

        return payload
