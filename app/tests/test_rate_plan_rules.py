import os
import unittest
from datetime import date

from app import create_app, db
from app.api.models import (
    Category,
    Floor,
    Property,
    RatePlan,
    Room,
    RoomCleaningStatus,
    RoomOnline,
    RoomStatus,
    Season,
)
from app.api.utils.rate_plan_rules import (
    get_overlapping_rate_plans,
    get_overlapping_seasons,
)
from app.api.utils.room_online_generator import generate_or_update_room_online_for_rate_plan


class RatePlanRulesTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('VCC_ENCRYPTION_KEY', 'bXoTmBmjf-5X8XL1bSL4Pj4FbTaVy3EMDLrdD8dWb68=')
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        RoomStatus.insert_status()
        RoomCleaningStatus.insert_status()

        self.property = Property(
            name='Hotel One',
            address='Addr',
            phone_number='123',
            email='hotel@example.com',
        )
        self.category = Category(name='Double', capacity=2, description='Double room')
        db.session.add_all([self.property, self.category])
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

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _build_rate_plan(self, **overrides):
        payload = {
            'name': 'BAR',
            'base_rate': 100.0,
            'property_id': self.property.id,
            'category_id': self.category.id,
            'start_date': date(2026, 5, 1),
            'end_date': date(2026, 5, 5),
            'weekend_rate': 120.0,
            'seasonal_multiplier': None,
            'is_active': True,
        }
        payload.update(overrides)
        rate_plan = RatePlan(**payload)
        db.session.add(rate_plan)
        db.session.commit()
        return rate_plan

    def test_generated_room_online_tracks_rate_plan_id(self):
        rate_plan = self._build_rate_plan()

        generate_or_update_room_online_for_rate_plan(rate_plan)

        generated = RoomOnline.query.filter_by(
            room_id=self.room.id,
            date=date(2026, 5, 1),
        ).first()
        self.assertIsNotNone(generated)
        self.assertEqual(generated.rate_plan_id, rate_plan.id)

    def test_manual_override_survives_rate_plan_regeneration(self):
        rate_plan = self._build_rate_plan()
        generate_or_update_room_online_for_rate_plan(rate_plan)

        generated = RoomOnline.query.filter_by(
            room_id=self.room.id,
            date=date(2026, 5, 2),
        ).first()
        generated.price = 175.0
        generated.rate_plan_id = None
        db.session.commit()

        rate_plan.base_rate = 140.0
        db.session.commit()
        generate_or_update_room_online_for_rate_plan(rate_plan)

        manual_override = RoomOnline.query.filter_by(
            room_id=self.room.id,
            date=date(2026, 5, 2),
        ).first()
        self.assertEqual(manual_override.price, 175.0)
        self.assertIsNone(manual_override.rate_plan_id)

    def test_inactive_rate_plan_removes_generated_rows(self):
        rate_plan = self._build_rate_plan()
        generate_or_update_room_online_for_rate_plan(rate_plan)

        rate_plan.is_active = False
        db.session.commit()
        generate_or_update_room_online_for_rate_plan(rate_plan)

        generated_rows = RoomOnline.query.filter_by(rate_plan_id=rate_plan.id).all()
        self.assertEqual(generated_rows, [])

    def test_overlapping_rate_plan_lookup_returns_conflicts(self):
        first_plan = self._build_rate_plan()
        self._build_rate_plan(
            name='Promo',
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 12),
        )

        conflicts = get_overlapping_rate_plans(
            property_id=self.property.id,
            category_id=self.category.id,
            start_date=date(2026, 5, 4),
            end_date=date(2026, 5, 8),
        )

        self.assertEqual([plan.id for plan in conflicts], [first_plan.id])

    def test_overlapping_season_lookup_returns_conflicts(self):
        season = Season(
            property_id=self.property.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 15),
            label='Summer',
        )
        db.session.add(season)
        db.session.commit()

        conflicts = get_overlapping_seasons(
            property_id=self.property.id,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 20),
        )

        self.assertEqual([item.id for item in conflicts], [season.id])
