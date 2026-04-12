from decimal import Decimal
from app.api.models import RoomOnline
from app.api.utils.pricing_engine import (
    calculate_nightly_rate,
    get_applicable_rate_plan_for_room,
    get_effective_restrictions,
)


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
        room_online = RoomOnline.query.filter_by(
            property_id=property_id,
            room_id=room_id,
            date=stay_date,
        ).first()

        if room_online and room_online.rate_plan_id is None:
            return Decimal(str(room_online.price))

        rate_plan = get_applicable_rate_plan_for_room(property_id, room_id, stay_date)
        if rate_plan is None:
            if room_online:
                return Decimal(str(room_online.price))
            return None

        rate_value = calculate_nightly_rate(
            rate_plan=rate_plan,
            target_date=stay_date,
            stay_length=1,
            adults=rate_plan.included_occupancy or 2,
            children=0,
        )
        return Decimal(str(rate_value))

    @staticmethod
    def get_restrictions(property_id: int, room_id: int, stay_date):
        rate_plan = get_applicable_rate_plan_for_room(property_id, room_id, stay_date)
        if rate_plan is None:
            return {
                'rate_plan_id': None,
                'min_los': None,
                'max_los': None,
                'closed': False,
                'closed_to_arrival': False,
                'closed_to_departure': False,
            }

        return get_effective_restrictions(rate_plan)

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
