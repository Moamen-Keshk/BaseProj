import os
import unittest
from datetime import date
from unittest.mock import patch

from app import create_app, db
from app.api.channel_manager.models import (
    ChannelConnection,
    ChannelRatePlanMap,
    ChannelRoomMap,
    ChannelSyncJob,
    SupportedChannel,
)
from app.api.channel_manager.services.ari_service import ARIService
from app.api.models import (
    Category,
    Floor,
    Property,
    RatePlan,
    Room,
    RoomCleaningStatus,
    RoomStatus,
    User,
)
from app.api.utils.revenue_management import (
    build_dynamic_quote,
    materialize_daily_rates_for_rate_plan,
    set_manual_override,
)
from app.api.revenue import _queue_revenue_ari_sync


class RevenueOptimizationTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('VCC_ENCRYPTION_KEY', 'bXoTmBmjf-5X8XL1bSL4Pj4FbTaVy3EMDLrdD8dWb68=')
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        RoomStatus.insert_status()
        RoomCleaningStatus.insert_status()
        SupportedChannel.insert_channels()

        self.admin = User(
            uid='admin-user',
            email='admin@example.com',
            username='admin',
            confirmed=True,
            is_super_admin=True,
        )
        self.property = Property(
            name='Hotel Revenue',
            address='1 Main Street',
            phone_number='123456789',
            email='hotel@example.com',
            currency='GBP',
        )
        self.category = Category(name='Double', capacity=2, description='Double room')
        db.session.add_all([self.admin, self.property, self.category])
        db.session.commit()

        self.floor = Floor(floor_number=1, property_id=self.property.id)
        db.session.add(self.floor)
        db.session.commit()

        self.room = Room(
            room_number=101,
            property_id=self.property.id,
            category_id=self.category.id,
            floor_id=self.floor.id,
            status_id=1,
            cleaning_status_id=3,
        )
        db.session.add(self.room)
        db.session.commit()

        self.client = self.app.test_client()
        self.headers = {
            'Authorization': 'Bearer test-token',
            'Content-Type': 'application/json',
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_rate_plan(self, **overrides):
        payload = {
            'name': 'BAR',
            'base_rate': 100.0,
            'property_id': self.property.id,
            'category_id': self.category.id,
            'start_date': date(2026, 5, 1),
            'end_date': date(2026, 5, 31),
            'pricing_type': 'standard',
            'is_active': True,
        }
        payload.update(overrides)
        rate_plan = RatePlan(**payload)
        db.session.add(rate_plan)
        db.session.commit()
        materialize_daily_rates_for_rate_plan(rate_plan)
        db.session.commit()
        return rate_plan

    def test_dynamic_quote_uses_direct_override(self):
        rate_plan = self._create_rate_plan()
        stay_date = date(2026, 5, 10)

        set_manual_override(
            property_id=self.property.id,
            rate_plan_id=rate_plan.id,
            stay_date=stay_date,
            amount=135.0,
            channel_code='direct',
            sellable_type_id=self.category.id,
            lock=True,
            note='High demand direct premium',
            updated_by='admin-user',
        )
        db.session.commit()

        quote = build_dynamic_quote(
            rate_plan=rate_plan,
            check_in=stay_date,
            check_out=date(2026, 5, 11),
            adults=2,
            children=0,
            channel_code='direct',
            sellable_type_id=self.category.id,
        )

        self.assertEqual(quote['total_amount'], 135.0)
        self.assertEqual(quote['nightly_rates'][0]['rate'], 135.0)

    def test_ari_service_builds_external_room_and_rate_plan_updates(self):
        rate_plan = self._create_rate_plan()
        stay_date = date(2026, 5, 12)

        set_manual_override(
            property_id=self.property.id,
            rate_plan_id=rate_plan.id,
            stay_date=stay_date,
            amount=142.0,
            channel_code='booking_com',
            sellable_type_id=self.category.id,
            lock=False,
            updated_by='admin-user',
        )
        db.session.commit()

        db.session.add(
            ChannelRoomMap(
                property_id=self.property.id,
                channel_code='booking_com',
                internal_room_id=self.room.id,
                internal_room_type_id=None,
                external_room_id='BKG-ROOM-101',
                external_room_name='Booking.com Double',
                is_active=True,
            )
        )
        db.session.add(
            ChannelRatePlanMap(
                property_id=self.property.id,
                channel_code='booking_com',
                internal_rate_plan_id=rate_plan.id,
                external_rate_plan_id='BKG-RATE-BAR',
                external_rate_plan_name='BAR',
                is_active=True,
            )
        )
        db.session.commit()

        updates = ARIService.build_updates_for_room_dates(
            property_id=self.property.id,
            room_ids=[self.room.id],
            dates=[stay_date],
            channel_code='booking_com',
        )

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]['room_id'], 'BKG-ROOM-101')
        self.assertEqual(updates[0]['rate_plan_id'], 'BKG-RATE-BAR')
        self.assertEqual(updates[0]['amount'], '142.0')

    def test_recommendation_route_recomputes_and_applies_direct_recommendation(self):
        rate_plan = self._create_rate_plan()

        with patch('app.api.decorators.get_current_user', return_value='admin-user'):
            recompute_response = self.client.post(
                f'/api/v1/properties/{self.property.id}/revenue/recommendations',
                headers=self.headers,
                json={
                    'start_date': '2026-05-15',
                    'end_date': '2026-05-15',
                    'sellable_type_id': self.category.id,
                    'rate_plan_id': rate_plan.id,
                    'channel_code': 'direct',
                },
            )

        self.assertEqual(recompute_response.status_code, 200)
        recommendations = recompute_response.get_json()['data']
        self.assertEqual(len(recommendations), 1)
        recommendation_id = recommendations[0]['id']

        with patch('app.api.decorators.get_current_user', return_value='admin-user'), \
                patch('app.api.revenue.get_current_user', return_value='admin-user'):
            apply_response = self.client.post(
                f'/api/v1/properties/{self.property.id}/revenue/recommendations/{recommendation_id}/apply',
                headers=self.headers,
                json={'lock': True},
            )

        self.assertEqual(apply_response.status_code, 200)
        payload = apply_response.get_json()['data']
        self.assertEqual(payload['channel_code'], 'direct')
        self.assertEqual(payload['source_type'], 'recommendation')
        self.assertTrue(payload['is_locked'])

    def test_channel_specific_sync_only_queues_target_channel(self):
        db.session.add_all([
            ChannelConnection(
                property_id=self.property.id,
                channel_code='booking_com',
                status='active',
                credentials_json={},
            ),
            ChannelConnection(
                property_id=self.property.id,
                channel_code='expedia',
                status='active',
                credentials_json={},
            ),
        ])
        db.session.commit()

        _queue_revenue_ari_sync(
            self.property.id,
            self.category.id,
            [date(2026, 5, 10)],
            'revenue_manual_override',
            'booking_com',
        )

        jobs = ChannelSyncJob.query.order_by(ChannelSyncJob.channel_code).all()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].channel_code, 'booking_com')

    def test_direct_sync_does_not_queue_external_jobs(self):
        db.session.add(
            ChannelConnection(
                property_id=self.property.id,
                channel_code='booking_com',
                status='active',
                credentials_json={},
            )
        )
        db.session.commit()

        _queue_revenue_ari_sync(
            self.property.id,
            self.category.id,
            [date(2026, 5, 10)],
            'revenue_manual_override',
            'direct',
        )

        self.assertEqual(ChannelSyncJob.query.count(), 0)
