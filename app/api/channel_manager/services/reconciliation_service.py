import logging
from datetime import datetime, timezone
from typing import Any

from app import db
from app.api.channel_manager.models import (
    ChannelConnection,
    ChannelMessageLog,
    ChannelRatePlanMap,
    ChannelReservationLink,
    ChannelRoomMap,
    ChannelSyncJob,
)
from app.api.channel_manager.services.pms_sync import queue_booking_ari_sync
from app.api.channel_manager.services.reservation_import_service import ReservationImportService
from app.api.channel_manager.services.sync_dispatcher import SyncDispatcher
from app.api.models import Booking, BookingStatus
from app.api.utils.notifications import notify_booking_cancelled

logger = logging.getLogger(__name__)


class ReconciliationService:
    """
    Utilities for reconciling OTA-facing state with PMS state.

    In this codebase the main reconciliation concerns are:
    - connection health and mapping completeness for a channel connection
    - reservation drift between OTA snapshots and imported PMS bookings
    """

    @staticmethod
    def _utcnow():
        return datetime.now(timezone.utc)

    @staticmethod
    def _extract_external_room_id(reservation_payload: dict[str, Any]) -> str | None:
        room_stays = reservation_payload.get('room_stays', [])
        first_room = room_stays[0] if room_stays else {}
        external_room_id = first_room.get('external_room_id')
        return str(external_room_id) if external_room_id not in (None, '') else None

    @staticmethod
    def _extract_external_rate_plan_id(reservation_payload: dict[str, Any]) -> str | None:
        room_stays = reservation_payload.get('room_stays', [])
        first_room = room_stays[0] if room_stays else {}
        external_rate_plan_id = first_room.get('external_rate_plan_id')
        return str(external_rate_plan_id) if external_rate_plan_id not in (None, '') else None

    @staticmethod
    def _get_cancelled_status_id() -> int:
        cancelled_status = (
            BookingStatus.query.filter(
                (BookingStatus.code == 'CANCELLED') | (BookingStatus.name == 'Cancelled')
            ).first()
        )
        return cancelled_status.id if cancelled_status else 5

    @staticmethod
    def build_connection_summary(connection: ChannelConnection) -> dict[str, Any]:
        room_maps = ChannelRoomMap.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
        )
        rate_maps = ChannelRatePlanMap.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
        )
        jobs = ChannelSyncJob.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
        )
        reservation_links = ChannelReservationLink.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
        )
        message_logs = ChannelMessageLog.query.filter_by(
            property_id=connection.property_id,
            channel_code=connection.channel_code,
        )

        return {
            'connection': connection.to_json(),
            'room_maps': {
                'total': room_maps.count(),
                'active': room_maps.filter_by(is_active=True).count(),
            },
            'rate_plan_maps': {
                'total': rate_maps.count(),
                'active': rate_maps.filter_by(is_active=True).count(),
            },
            'jobs': {
                'pending': jobs.filter(ChannelSyncJob.status.in_(['pending', 'queued', 'retrying'])).count(),
                'processing': jobs.filter_by(status='processing').count(),
                'failed': jobs.filter_by(status='failed').count(),
                'success': jobs.filter_by(status='success').count(),
            },
            'reservation_links': {
                'total': reservation_links.count(),
                'imported': reservation_links.filter_by(status='imported').count(),
                'modified': reservation_links.filter_by(status='modified').count(),
                'cancelled': reservation_links.filter_by(status='cancelled').count(),
                'missing': reservation_links.filter_by(status='missing').count(),
            },
            'message_logs': {
                'total': message_logs.count(),
                'failed': message_logs.filter_by(success=False).count(),
            },
        }

    @staticmethod
    def summarize_property(property_id: int, channel_code: str | None = None) -> list[dict[str, Any]]:
        query = ChannelConnection.query.filter_by(property_id=property_id)
        if channel_code:
            query = query.filter_by(channel_code=channel_code)

        connections = query.order_by(ChannelConnection.id.asc()).all()
        return [ReconciliationService.build_connection_summary(connection) for connection in connections]

    @staticmethod
    def reconcile_reservations(
        connection: ChannelConnection,
        reservations: list[dict[str, Any]],
        *,
        snapshot_complete: bool = False,
        queue_acknowledgements: bool = False,
        mark_missing_as_cancelled: bool = False,
    ) -> dict[str, Any]:
        """
        Reconciles OTA reservation payloads against imported PMS bookings.

        `snapshot_complete=True` means the provided reservation list is treated as the
        authoritative full snapshot for the connection. Existing imported links that do
        not appear in the snapshot are marked as `missing`, or `canceled` when
        `mark_missing_as_canceled=True`.
        """
        now = ReconciliationService._utcnow()
        cancelled_status_id = ReconciliationService._get_cancelled_status_id()
        seen_external_ids: set[str] = set()

        summary = {
            'property_id': connection.property_id,
            'channel_code': connection.channel_code,
            'processed': 0,
            'imported': 0,
            'modified': 0,
            'cancelled': 0,
            'skipped': 0,
            'missing': 0,
            'missing_cancelled': 0,
            'ack_queued': 0,
            'errors': [],
            'unmapped_room_reservations': [],
            'unmapped_rate_plan_reservations': [],
        }

        for reservation in reservations or []:
            external_reservation_id = reservation.get('external_reservation_id')
            if not external_reservation_id:
                summary['errors'].append('Skipped reservation without external_reservation_id.')
                continue

            external_reservation_id = str(external_reservation_id)
            if external_reservation_id in seen_external_ids:
                summary['skipped'] += 1
                continue

            seen_external_ids.add(external_reservation_id)
            summary['processed'] += 1

            existing_link = ChannelReservationLink.query.filter_by(
                property_id=connection.property_id,
                channel_code=connection.channel_code,
                external_reservation_id=external_reservation_id,
            ).first()

            incoming_status = str(reservation.get('status', 'new')).lower()
            incoming_version = reservation.get('external_version')

            external_room_id = ReconciliationService._extract_external_room_id(reservation)
            if external_room_id:
                room_map = ChannelRoomMap.query.filter_by(
                    property_id=connection.property_id,
                    channel_code=connection.channel_code,
                    external_room_id=external_room_id,
                    is_active=True,
                ).first()
                if not room_map:
                    summary['unmapped_room_reservations'].append(external_reservation_id)

            external_rate_plan_id = ReconciliationService._extract_external_rate_plan_id(reservation)
            if external_rate_plan_id:
                rate_plan_map = ChannelRatePlanMap.query.filter_by(
                    property_id=connection.property_id,
                    channel_code=connection.channel_code,
                    external_rate_plan_id=external_rate_plan_id,
                    is_active=True,
                ).first()
                if not rate_plan_map:
                    summary['unmapped_rate_plan_reservations'].append(external_reservation_id)

            try:
                booking = ReservationImportService.import_one(connection, reservation)
            except Exception as exc:
                logger.exception(
                    "Failed reconciling reservation %s for property=%s channel=%s",
                    external_reservation_id,
                    connection.property_id,
                    connection.channel_code,
                )
                summary['errors'].append(f'{external_reservation_id}: {str(exc)}')
                continue

            link = ChannelReservationLink.query.filter_by(
                property_id=connection.property_id,
                channel_code=connection.channel_code,
                external_reservation_id=external_reservation_id,
            ).first()

            if link:
                link.last_seen_at = now
                if incoming_version not in (None, ''):
                    link.external_version = str(incoming_version)

                if incoming_status == 'cancelled':
                    link.status = 'cancelled'
                    summary['cancelled'] += 1
                elif existing_link:
                    link.status = 'modified'
                    summary['modified'] += 1
                else:
                    link.status = 'imported'
                    summary['imported'] += 1

                db.session.commit()
            elif booking is None and incoming_status == 'cancelled':
                summary['cancelled'] += 1

            if queue_acknowledgements:
                SyncDispatcher.queue_reservation_ack(
                    property_id=connection.property_id,
                    channel_code=connection.channel_code,
                    external_reservation_id=external_reservation_id,
                )
                summary['ack_queued'] += 1

        if snapshot_complete:
            active_links = ChannelReservationLink.query.filter_by(
                property_id=connection.property_id,
                channel_code=connection.channel_code,
            ).filter(ChannelReservationLink.status.in_(['imported', 'modified'])).all()

            for link in active_links:
                if link.external_reservation_id in seen_external_ids:
                    continue

                booking = Booking.query.get(link.internal_booking_id)

                if mark_missing_as_cancelled:
                    link.status = 'cancelled'
                    if booking and booking.status_id != cancelled_status_id:
                        booking.status_id = cancelled_status_id
                        db.session.flush()
                        notify_booking_cancelled(
                            property_id=booking.property_id,
                            booking_id=booking.id,
                            guest_name=' '.join(
                                part for part in [booking.first_name, booking.last_name] if part
                            ).strip() or 'Guest',
                            booking_reference=f"#{booking.confirmation_number}" if booking.confirmation_number else None,
                        )
                        queue_booking_ari_sync(
                            booking,
                            reason=f"Channel reconciliation cancellation: {connection.channel_code}",
                        )
                    summary['missing_cancelled'] += 1
                else:
                    link.status = 'missing'
                    summary['missing'] += 1

                link.last_seen_at = now

            db.session.commit()

        summary['unmapped_room_reservations'] = sorted(set(summary['unmapped_room_reservations']))
        summary['unmapped_rate_plan_reservations'] = sorted(set(summary['unmapped_rate_plan_reservations']))
        summary['summary_generated_at'] = now.isoformat()
        return summary
