from decimal import Decimal

from app.api.channel_manager.models import ChannelRatePlanMap
from app.api.models import RatePlan, Room, RoomOnline
from app.api.utils.pricing_engine import (
    calculate_nightly_rate,
    get_applicable_rate_plan_for_room,
    get_effective_restrictions,
    get_rate_plan_room_type_id,
    get_room_sellable_type_id,
)
from app.api.utils.revenue_management import (
    BASE_CHANNEL_CODE,
    compute_sellable_inventory,
    get_daily_rate_state,
    normalize_channel_code,
    resolve_dynamic_nightly_rate,
    resolve_external_room_id,
)


class ARIService:
    @staticmethod
    def get_sellable_inventory(property_id: int, room_id: int, stay_date, channel_code: str | None = None):
        room = Room.query.filter_by(id=room_id, property_id=property_id).first()
        if room is None:
            return 0
        sellable_type_id = get_room_sellable_type_id(room)
        if sellable_type_id is None:
            return 0
        return compute_sellable_inventory(property_id, sellable_type_id, stay_date)

    @staticmethod
    def get_rate(
        property_id: int,
        room_id: int,
        stay_date,
        channel_code: str | None = None,
        rate_plan_id: int | None = None,
    ):
        normalized_channel = normalize_channel_code(channel_code, default=BASE_CHANNEL_CODE)
        room = Room.query.filter_by(id=room_id, property_id=property_id).first()
        if room is None:
            return None

        if rate_plan_id is not None:
            rate_plan = RatePlan.query.filter_by(id=rate_plan_id, property_id=property_id, is_active=True).first()
            if rate_plan is None:
                return None
            rate_value = resolve_dynamic_nightly_rate(
                rate_plan=rate_plan,
                stay_date=stay_date,
                stay_length=1,
                adults=rate_plan.included_occupancy or 2,
                children=0,
                channel_code=normalized_channel,
                room_id=room_id,
            )
            return Decimal(str(rate_value))

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
    def get_restrictions(
        property_id: int,
        room_id: int,
        stay_date,
        channel_code: str | None = None,
        rate_plan_id: int | None = None,
    ):
        normalized_channel = normalize_channel_code(channel_code, default=BASE_CHANNEL_CODE)

        if rate_plan_id is not None:
            room = Room.query.filter_by(id=room_id, property_id=property_id).first()
            if room is None:
                return {
                    'rate_plan_id': None,
                    'min_los': None,
                    'max_los': None,
                    'closed': False,
                    'closed_to_arrival': False,
                    'closed_to_departure': False,
                }
            sellable_type_id = get_room_sellable_type_id(room)
            state = get_daily_rate_state(
                property_id=property_id,
                rate_plan_id=rate_plan_id,
                stay_date=stay_date,
                channel_code=normalized_channel,
                sellable_type_id=sellable_type_id,
            )
            if state is None:
                return {
                    'rate_plan_id': rate_plan_id,
                    'min_los': None,
                    'max_los': None,
                    'closed': False,
                    'closed_to_arrival': False,
                    'closed_to_departure': False,
                }
            return {
                'rate_plan_id': rate_plan_id,
                'min_los': getattr(state, 'min_los', None),
                'max_los': getattr(state, 'max_los', None),
                'closed': bool(getattr(state, 'closed', False)),
                'closed_to_arrival': bool(getattr(state, 'closed_to_arrival', False)),
                'closed_to_departure': bool(getattr(state, 'closed_to_departure', False)),
            }

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
    def build_updates_for_room_dates(
        property_id: int,
        room_ids: list[int],
        dates: list,
        channel_code: str | None = None,
    ):
        if not channel_code:
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

        normalized_channel = normalize_channel_code(channel_code)
        updates = []
        seen_keys = set()
        rooms = Room.query.filter(Room.property_id == property_id, Room.id.in_(room_ids)).all()
        rate_maps = ChannelRatePlanMap.query.filter_by(
            property_id=property_id,
            channel_code=normalized_channel,
            is_active=True,
        ).all()

        for room in rooms:
            sellable_type_id = get_room_sellable_type_id(room)
            if sellable_type_id is None:
                continue

            external_room_id = resolve_external_room_id(property_id, normalized_channel, room)
            if not external_room_id:
                continue

            applicable_rate_maps = []
            for rate_map in rate_maps:
                rate_plan = RatePlan.query.filter_by(
                    id=rate_map.internal_rate_plan_id,
                    property_id=property_id,
                    is_active=True,
                ).first()
                if rate_plan is None:
                    continue
                if get_rate_plan_room_type_id(rate_plan) != sellable_type_id:
                    continue
                applicable_rate_maps.append((rate_map, rate_plan))

            for stay_date in dates:
                availability = ARIService.get_sellable_inventory(property_id, room.id, stay_date, normalized_channel)

                if not applicable_rate_maps:
                    key = (external_room_id, None, stay_date)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    updates.append({
                        'property_id': property_id,
                        'room_id': external_room_id,
                        'internal_room_id': room.id,
                        'rate_plan_id': None,
                        'stay_date': stay_date.isoformat(),
                        'availability': availability,
                        'amount': None,
                        'min_los': None,
                        'max_los': None,
                        'closed': False,
                        'closed_to_arrival': False,
                        'closed_to_departure': False,
                    })
                    continue

                for rate_map, rate_plan in applicable_rate_maps:
                    if rate_plan.start_date > stay_date or rate_plan.end_date < stay_date:
                        continue
                    key = (external_room_id, rate_map.external_rate_plan_id, stay_date)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    rate_value = ARIService.get_rate(
                        property_id=property_id,
                        room_id=room.id,
                        stay_date=stay_date,
                        channel_code=normalized_channel,
                        rate_plan_id=rate_plan.id,
                    )
                    restrictions = ARIService.get_restrictions(
                        property_id=property_id,
                        room_id=room.id,
                        stay_date=stay_date,
                        channel_code=normalized_channel,
                        rate_plan_id=rate_plan.id,
                    )

                    updates.append({
                        'property_id': property_id,
                        'room_id': external_room_id,
                        'internal_room_id': room.id,
                        'rate_plan_id': rate_map.external_rate_plan_id,
                        'internal_rate_plan_id': rate_plan.id,
                        'stay_date': stay_date.isoformat(),
                        'availability': availability,
                        'amount': str(rate_value) if rate_value is not None else None,
                        'min_los': restrictions.get('min_los'),
                        'max_los': restrictions.get('max_los'),
                        'closed': restrictions.get('closed'),
                        'closed_to_arrival': restrictions.get('closed_to_arrival'),
                        'closed_to_departure': restrictions.get('closed_to_departure'),
                    })

        return updates
