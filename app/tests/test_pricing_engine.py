import os
import unittest
from datetime import date

from app import create_app, db
from app.api.channel_manager.services.ari_service import ARIService
from app.api.models import (
    Category,
    Floor,
    Property,
    RatePlan,
    Room,
    RoomCleaningStatus,
    RoomStatus,
    Season,
)
from app.api.utils.pricing_engine import calculate_nightly_rate, calculate_quote
from app.api.utils.room_online_generator import generate_or_update_room_online_for_rate_plan


class PricingEngineTestCase(unittest.TestCase):
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

    def _create_rate_plan(self, **overrides):
        payload = {
            'name': 'BAR',
            'base_rate': 100.0,
            'property_id': self.property.id,
            'category_id': self.category.id,
            'start_date': date(2026, 5, 1),
            'end_date': date(2026, 5, 31),
            'weekend_rate': 130.0,
            'seasonal_multiplier': None,
            'pricing_type': 'standard',
            'los_pricing': [],
            'is_active': True,
        }
        payload.update(overrides)
        rate_plan = RatePlan(**payload)
        db.session.add(rate_plan)
        db.session.commit()
        return rate_plan

    def test_standard_rate_uses_weekend_and_season_multiplier(self):
        season = Season(
            property_id=self.property.id,
            start_date=date(2026, 5, 2),
            end_date=date(2026, 5, 4),
            label='Peak',
        )
        db.session.add(season)
        db.session.commit()

        rate_plan = self._create_rate_plan(seasonal_multiplier=1.5)
        nightly_rate = calculate_nightly_rate(rate_plan, date(2026, 5, 2))

        self.assertEqual(nightly_rate, 195.0)

    def test_derived_rate_uses_parent_adjustment(self):
        parent = self._create_rate_plan(name='BAR Parent', base_rate=120.0)
        child = self._create_rate_plan(
            name='NRF',
            pricing_type='derived',
            parent_rate_plan_id=parent.id,
            derived_adjustment_type='percent',
            derived_adjustment_value=90.0,
        )

        nightly_rate = calculate_nightly_rate(child, date(2026, 5, 5))
        self.assertEqual(nightly_rate, 108.0)

    def test_occupancy_rate_adds_guest_surcharges(self):
        rate_plan = self._create_rate_plan(
            pricing_type='occupancy',
            included_occupancy=2,
            single_occupancy_rate=80.0,
            extra_adult_rate=20.0,
            extra_child_rate=10.0,
        )

        single_rate = calculate_nightly_rate(rate_plan, date(2026, 5, 5), adults=1, children=0)
        family_rate = calculate_nightly_rate(rate_plan, date(2026, 5, 5), adults=2, children=1)

        self.assertEqual(single_rate, 80.0)
        self.assertEqual(family_rate, 110.0)

    def test_los_quote_uses_length_of_stay_override_and_restrictions(self):
        rate_plan = self._create_rate_plan(
            pricing_type='los',
            min_los=2,
            max_los=5,
            los_pricing=[{'stay_length': 3, 'nightly_rate': 85.0}],
        )

        quote = calculate_quote(
            rate_plan=rate_plan,
            check_in=date(2026, 5, 10),
            check_out=date(2026, 5, 13),
            adults=2,
            children=0,
        )

        self.assertEqual(quote['total_amount'], 255.0)
        self.assertEqual(quote['nightly_rates'][0]['rate'], 85.0)

        with self.assertRaises(ValueError):
            calculate_quote(
                rate_plan=rate_plan,
                check_in=date(2026, 5, 10),
                check_out=date(2026, 5, 11),
            )

    def test_ari_service_reads_engine_rate_and_restrictions(self):
        rate_plan = self._create_rate_plan(
            min_los=2,
            max_los=4,
            closed_to_arrival=True,
        )
        generate_or_update_room_online_for_rate_plan(rate_plan)

        amount = ARIService.get_rate(self.property.id, self.room.id, date(2026, 5, 5))
        restrictions = ARIService.get_restrictions(self.property.id, self.room.id, date(2026, 5, 5))

        self.assertEqual(str(amount), '100.0')
        self.assertEqual(restrictions['rate_plan_id'], rate_plan.id)
        self.assertEqual(restrictions['min_los'], 2)
        self.assertEqual(restrictions['max_los'], 4)
        self.assertTrue(restrictions['closed_to_arrival'])
