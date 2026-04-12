from datetime import datetime, timezone, timedelta
from app.celery_app import celery
from app.api.channel_manager.models import ChannelRoomMap
from app.api.models import Room
from app.api.channel_manager.services.sync_dispatcher import SyncDispatcher
from app.api.utils.pricing_engine import get_room_sellable_type_id


@celery.task
def process_bulk_ari_push(property_id: int):
    """
    Pushes 365 days of availability for all active mapped rooms for a property.
    This should be triggered when a user completes their channel mapping setup.
    """
    # Get all actively mapped internal room IDs for this property
    active_mappings = ChannelRoomMap.query.filter_by(
        property_id=property_id,
        is_active=True
    ).all()

    if not active_mappings:
        return {"status": "skipped", "message": "No active mappings found."}

    unique_room_ids = set()
    property_rooms = Room.query.filter_by(property_id=property_id).all()
    for mapping in active_mappings:
        if mapping.internal_room_type_id:
            rooms = [
                room for room in property_rooms
                if get_room_sellable_type_id(room) == mapping.internal_room_type_id
            ]
            for room in rooms:
                unique_room_ids.add(room.id)
        elif mapping.internal_room_id:
            unique_room_ids.add(mapping.internal_room_id)

    unique_room_ids = list(unique_room_ids)

    # Generate the next 365 dates
    start_date = datetime.now(timezone.utc).date()
    dates_to_push = [start_date + timedelta(days=i) for i in range(365)]

    # We slice the dates into smaller chunks (e.g., 30 days) so we don't overload the OTA API limits
    chunk_size = 30
    for i in range(0, len(dates_to_push), chunk_size):
        date_chunk = dates_to_push[i:i + chunk_size]

        # Dispatch standard ARI Push jobs for these chunks
        SyncDispatcher.queue_ari_push(
            property_id=property_id,
            room_ids=unique_room_ids,
            dates=date_chunk,
            reason="Bulk initial sync"
        )

    return {"status": "success", "message": f"Queued bulk sync for {len(unique_room_ids)} rooms."}
