from datetime import timedelta
from types import SimpleNamespace

from app.api.models import Room
from app.api.channel_manager.services.sync_dispatcher import SyncDispatcher


def _date_range(start_date, end_date, include_end=True):
    if not start_date or not end_date:
        return []

    last = end_date if include_end else end_date - timedelta(days=1)
    if start_date > last:
        return []

    dates = []
    current = start_date
    while current <= last:
        dates.append(current)
        current += timedelta(days=1)

    return dates


def _queue_for_room(property_id, room_id, start_date, end_date, reason, include_end=True):
    if not property_id or not room_id or not start_date or not end_date:
        return

    affected_dates = _date_range(start_date, end_date, include_end=include_end)
    if not affected_dates:
        return

    SyncDispatcher.queue_ari_push(
        property_id=property_id,
        room_ids=[room_id],
        dates=affected_dates,
        reason=reason,
    )


def _queue_for_rooms(property_id, room_ids, start_date, end_date, reason, include_end=True):
    if not property_id or not room_ids or not start_date or not end_date:
        return

    affected_dates = _date_range(start_date, end_date, include_end=include_end)
    if not affected_dates:
        return

    SyncDispatcher.queue_ari_push(
        property_id=property_id,
        room_ids=room_ids,
        dates=affected_dates,
        reason=reason,
    )


def _room_ids_for_property(property_id):
    return [room.id for room in Room.query.filter_by(property_id=property_id).all()]


def _room_ids_for_property_category(property_id, category_id):
    return [
        room.id for room in Room.query.filter_by(
            property_id=property_id,
            category_id=category_id
        ).all()
    ]


def queue_booking_ari_sync(booking, reason: str):
    if not booking:
        return

    _queue_for_room(
        property_id=getattr(booking, 'property_id', None),
        room_id=getattr(booking, 'room_id', None),
        start_date=getattr(booking, 'check_in', None),
        end_date=getattr(booking, 'check_out', None),
        reason=reason,
        include_end=False,
    )


def queue_booking_transition_ari_sync(
    old_property_id,
    old_room_id,
    old_check_in,
    old_check_out,
    booking,
    reason: str,
):
    old_snapshot = SimpleNamespace(
        property_id=old_property_id,
        room_id=old_room_id,
        check_in=old_check_in,
        check_out=old_check_out,
    )

    queue_booking_ari_sync(old_snapshot, reason)
    queue_booking_ari_sync(booking, reason)


def queue_block_ari_sync(block, reason: str):
    if not block:
        return

    _queue_for_room(
        property_id=getattr(block, 'property_id', None),
        room_id=getattr(block, 'room_id', None),
        start_date=getattr(block, 'start_date', None),
        end_date=getattr(block, 'end_date', None),
        reason=reason,
        include_end=False,
    )


def queue_block_transition_ari_sync(
    old_property_id,
    old_room_id,
    old_start_date,
    old_end_date,
    block,
    reason: str,
):
    old_snapshot = SimpleNamespace(
        property_id=old_property_id,
        room_id=old_room_id,
        start_date=old_start_date,
        end_date=old_end_date,
    )

    queue_block_ari_sync(old_snapshot, reason)
    queue_block_ari_sync(block, reason)


def queue_season_ari_sync(season, reason: str):
    if not season or not getattr(season, 'property_id', None):
        return

    start_date = getattr(season, 'start_date', None)
    end_date = getattr(season, 'end_date', None)
    room_ids = _room_ids_for_property(season.property_id)

    _queue_for_rooms(
        property_id=season.property_id,
        room_ids=room_ids,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        include_end=True,
    )


def queue_season_transition_ari_sync(
    old_property_id,
    old_start_date,
    old_end_date,
    season,
    reason: str,
):
    old_snapshot = SimpleNamespace(
        property_id=old_property_id,
        start_date=old_start_date,
        end_date=old_end_date,
    )

    queue_season_ari_sync(old_snapshot, reason)
    queue_season_ari_sync(season, reason)


def queue_rate_plan_ari_sync(rate_plan, reason: str):
    if not rate_plan:
        return

    property_id = getattr(rate_plan, 'property_id', None)
    category_id = getattr(rate_plan, 'category_id', None)
    start_date = getattr(rate_plan, 'start_date', None)
    end_date = getattr(rate_plan, 'end_date', None)

    room_ids = _room_ids_for_property_category(property_id, category_id)

    _queue_for_rooms(
        property_id=property_id,
        room_ids=room_ids,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        include_end=True,
    )


def queue_rate_plan_transition_ari_sync(
    old_property_id,
    old_category_id,
    old_start_date,
    old_end_date,
    rate_plan,
    reason: str,
):
    old_snapshot = SimpleNamespace(
        property_id=old_property_id,
        category_id=old_category_id,
        start_date=old_start_date,
        end_date=old_end_date,
    )

    queue_rate_plan_ari_sync(old_snapshot, reason)
    queue_rate_plan_ari_sync(rate_plan, reason)


def queue_room_online_ari_sync(room_online, reason: str):
    if not room_online:
        return

    date_value = getattr(room_online, 'date', None)

    _queue_for_room(
        property_id=getattr(room_online, 'property_id', None),
        room_id=getattr(room_online, 'room_id', None),
        start_date=date_value,
        end_date=date_value,
        reason=reason,
        include_end=True,
    )


def queue_room_online_transition_ari_sync(
    old_property_id,
    old_room_id,
    old_date,
    room_online,
    reason: str,
):
    old_snapshot = SimpleNamespace(
        property_id=old_property_id,
        room_id=old_room_id,
        date=old_date,
    )

    queue_room_online_ari_sync(old_snapshot, reason)
    queue_room_online_ari_sync(room_online, reason)