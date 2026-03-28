from decimal import Decimal


class ARIService:
    @staticmethod
    def get_sellable_inventory(property_id: int, room_id: int, stay_date):
        # TODO:
        # Replace with real logic using:
        # - bookings
        # - blocks
        # - room_online
        # - out of order / maintenance states
        return 1

    @staticmethod
    def get_rate(property_id: int, room_id: int, stay_date):
        # TODO:
        # Replace with:
        # - room override rate if exists
        # - else published/default rate
        return Decimal('100.00')

    @staticmethod
    def get_restrictions(property_id: int, room_id: int, stay_date):
        # TODO:
        # Replace with:
        # - min_los
        # - max_los
        # - closed
        # - cta
        # - ctd
        # - mapped rate plan
        return {
            'rate_plan_id': None,
            'min_los': None,
            'max_los': None,
            'closed': False,
            'closed_to_arrival': False,
            'closed_to_departure': False,
        }

    @staticmethod
    def build_updates_for_room_dates(property_id: int, room_ids: list[int], dates: list):
        updates = []

        for room_id in room_ids:
            for stay_date in dates:
                sellable_inventory = ARIService.get_sellable_inventory(property_id, room_id, stay_date)
                rate_value = ARIService.get_rate(property_id, room_id, stay_date)
                restrictions = ARIService.get_restrictions(property_id, room_id, stay_date)

                updates.append({
                    'property_id': property_id,
                    'room_id': room_id,
                    'rate_plan_id': restrictions.get('rate_plan_id'),
                    'stay_date': stay_date.isoformat(),
                    'availability': sellable_inventory,
                    'amount': str(rate_value) if rate_value is not None else None,
                    'min_los': restrictions.get('min_los'),
                    'max_los': restrictions.get('max_los'),
                    'closed': restrictions.get('closed'),
                    'closed_to_arrival': restrictions.get('closed_to_arrival'),
                    'closed_to_departure': restrictions.get('closed_to_departure'),
                })

        return updates