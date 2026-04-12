import os
import unittest

from app import create_app, db
from app.api.models import Property
from app.api.utils.property_setup import normalize_property_payload


class PropertySetupTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('VCC_ENCRYPTION_KEY', 'bXoTmBmjf-5X8XL1bSL4Pj4FbTaVy3EMDLrdD8dWb68=')
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_normalize_property_payload_validates_and_defaults_setup_fields(self):
        normalized = normalize_property_payload({
            'name': 'Hotel One',
            'address': 'Addr',
            'currency': 'gbp',
            'tax_rate': '20',
            'timezone': 'Europe/London',
            'default_check_in_time': '15:30',
            'default_check_out_time': '10:00',
            'floors': [1, '2'],
            'amenity_ids': ['1', 2, 2],
        })

        self.assertEqual(normalized['currency'], 'GBP')
        self.assertEqual(normalized['tax_rate'], 20.0)
        self.assertEqual(normalized['timezone'], 'Europe/London')
        self.assertEqual(normalized['default_check_in_time'], '15:30')
        self.assertEqual(normalized['default_check_out_time'], '10:00')
        self.assertEqual(normalized['floors'], [1, 2])
        self.assertEqual(normalized['amenity_ids'], [1, 2])

    def test_normalize_property_payload_rejects_invalid_timezone(self):
        with self.assertRaises(ValueError):
            normalize_property_payload({
                'name': 'Hotel One',
                'address': 'Addr',
                'timezone': 'Mars/Phobos',
            })

    def test_property_serialization_uses_frontend_safe_date_and_setup_fields(self):
        property_record = Property(
            name='Hotel One',
            address='Addr',
            timezone='Europe/London',
            currency='GBP',
            tax_rate=12.5,
            default_check_in_time='15:00',
            default_check_out_time='11:00',
        )
        db.session.add(property_record)
        db.session.commit()

        payload = property_record.to_json()
        self.assertRegex(payload['published_date'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertEqual(payload['timezone'], 'Europe/London')
        self.assertEqual(payload['currency'], 'GBP')
        self.assertEqual(payload['tax_rate'], 12.5)
