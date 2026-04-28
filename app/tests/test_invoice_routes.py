import os
import unittest
from unittest.mock import patch

from app import create_app, db
from app.api.models import Booking, BookingStatus, GuestMessage, PaymentStatus, Property, Role, User


class InvoiceRouteTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('VCC_ENCRYPTION_KEY', 'bXoTmBmjf-5X8XL1bSL4Pj4FbTaVy3EMDLrdD8dWb68=')
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        Role.insert_roles()
        PaymentStatus.insert_status()
        BookingStatus.insert_status()

        self.admin = User(
            uid='admin-user',
            email='admin@example.com',
            username='admin',
            confirmed=True,
            is_super_admin=True,
        )
        self.property = Property(
            name='Hotel One',
            address='1 Main Street',
            phone_number='123456789',
            email='hotel@example.com',
            currency='GBP',
        )
        db.session.add_all([self.admin, self.property])
        db.session.commit()

        self.booking = Booking(
            first_name='Ada',
            last_name='Lovelace',
            email='ada@example.com',
            phone='123456789',
            number_of_adults=2,
            number_of_children=0,
            property_id=self.property.id,
            check_in_year=2026,
            check_in_month=4,
            check_in_day=15,
            check_out_year=2026,
            check_out_month=4,
            check_out_day=17,
            number_of_days=2,
            rate=300.0,
            amount_paid=0.0,
        )
        db.session.add(self.booking)
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

    def test_print_invoice_returns_html_document(self):
        with patch('app.api.decorators.get_current_user', return_value='admin-user'):
            response = self.client.get(
                f'/api/v1/properties/{self.property.id}/bookings/{self.booking.id}/invoice/print',
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.content_type)

        body = response.get_data(as_text=True)
        refreshed_booking = Booking.query.get(self.booking.id)
        self.assertIsNotNone(refreshed_booking.invoice)
        self.assertIn(refreshed_booking.invoice.invoice_number, body)
        self.assertIn('Ada Lovelace', body)

    def test_email_invoice_defaults_to_booking_email(self):
        with patch('app.api.decorators.get_current_user', return_value='admin-user'), \
                patch('app.api.invoices.get_current_user', return_value='admin-user'), \
                patch('app.api.utils.guest_communication_task.send_invoice_email_task.delay') as delay_mock:
            response = self.client.post(
                f'/api/v1/properties/{self.property.id}/bookings/{self.booking.id}/invoice/email',
                headers=self.headers,
                json={
                    'subject': 'Your stay invoice',
                    'message': 'Thanks for staying with us.',
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['data']['recipient_email'], 'ada@example.com')

        email_log = GuestMessage.query.one()
        self.assertEqual(email_log.subject, 'Your stay invoice')
        self.assertEqual(email_log.message_body, 'Thanks for staying with us.')
        self.assertEqual(email_log.delivery_status, 'queued')

        delay_mock.assert_called_once()
        task_kwargs = delay_mock.call_args.kwargs
        self.assertEqual(task_kwargs['booking_id'], self.booking.id)
        self.assertEqual(task_kwargs['property_id'], self.property.id)
        self.assertEqual(task_kwargs['recipient_email'], 'ada@example.com')
        self.assertEqual(task_kwargs['subject'], 'Your stay invoice DO NOT REPLY')
