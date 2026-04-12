import os
import unittest

from app import create_app, db
from app.api.constants import Constants
from app.api.models import (
    Floor,
    Property,
    Room,
    RoomCleaningLog,
    RoomCleaningStatus,
    RoomStatus,
)
from app.api.utils.housekeeping_logic import (
    apply_room_cleaning_status,
    is_manual_cleaning_status_allowed,
    resolve_housekeeping_display_status,
)


class HousekeepingLogicTestCase(unittest.TestCase):
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
        db.session.add(self.property)
        db.session.commit()

        self.floor = Floor(floor_number=1, property_id=self.property.id)
        db.session.add(self.floor)
        db.session.commit()

        self.room = Room(
            room_number=101,
            property_id=self.property.id,
            floor_id=self.floor.id,
            status_id=Constants.RoomStatusCoding['Available'],
            cleaning_status_id=Constants.RoomCleaningStatusCoding['Clean'],
        )
        db.session.add(self.room)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_system_only_status_rejected_for_manual_update(self):
        waiting_status_id = Constants.RoomCleaningStatusCoding['Waiting']

        self.assertFalse(is_manual_cleaning_status_allowed(waiting_status_id))
        with self.assertRaises(ValueError):
            apply_room_cleaning_status(
                self.room,
                self.property.id,
                waiting_status_id,
                'Housekeeping User',
            )

    def test_occupied_display_status_only_overrides_clean_ready_or_none(self):
        occupied_status_id = Constants.RoomCleaningStatusCoding['Occupied']

        self.assertEqual(
            resolve_housekeeping_display_status(
                Constants.RoomCleaningStatusCoding['Clean'],
                True,
            ),
            occupied_status_id,
        )
        self.assertEqual(
            resolve_housekeeping_display_status(
                Constants.RoomCleaningStatusCoding['Ready'],
                True,
            ),
            occupied_status_id,
        )
        self.assertEqual(
            resolve_housekeeping_display_status(
                Constants.RoomCleaningStatusCoding['Service'],
                True,
            ),
            Constants.RoomCleaningStatusCoding['Service'],
        )

    def test_status_update_creates_cleaning_log(self):
        changed = apply_room_cleaning_status(
            self.room,
            self.property.id,
            Constants.RoomCleaningStatusCoding['Dirty'],
            'Housekeeping User',
        )
        db.session.commit()

        self.assertTrue(changed)
        self.assertEqual(self.room.cleaning_status_id, Constants.RoomCleaningStatusCoding['Dirty'])
        logs = RoomCleaningLog.query.filter_by(room_id=self.room.id).all()
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log.old_status_id, Constants.RoomCleaningStatusCoding['Clean'])
        self.assertEqual(log.new_status_id, Constants.RoomCleaningStatusCoding['Dirty'])
        self.assertEqual(log.user_name, 'Housekeeping User')
