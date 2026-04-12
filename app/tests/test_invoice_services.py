import os
import unittest

from app import create_app, db
from app.api.models import Booking, BookingStatus, PaymentStatus, Property, Role
from app.api.payments.services import record_booking_payment, sync_invoice_for_booking


class InvoiceServiceTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('VCC_ENCRYPTION_KEY', 'bXoTmBmjf-5X8XL1bSL4Pj4FbTaVy3EMDLrdD8dWb68=')
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        Role.insert_roles()
        PaymentStatus.insert_status()
        BookingStatus.insert_status()

        self.property = Property(name='Hotel One', address='Addr', phone_number='123', email='hotel@example.com')
        db.session.add(self.property)
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

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_sync_invoice_creates_folio(self):
        invoice = sync_invoice_for_booking(self.booking)
        db.session.commit()

        self.assertIsNotNone(invoice.id)
        self.assertEqual(invoice.booking_id, self.booking.id)
        self.assertEqual(invoice.total_amount, 300.0)
        self.assertEqual(invoice.amount_paid, 0.0)
        self.assertEqual(invoice.balance_due, 300.0)
        self.assertEqual(invoice.status, 'open')

    def test_record_payment_updates_booking_and_invoice(self):
        sync_invoice_for_booking(self.booking)
        transaction, invoice = record_booking_payment(
            booking=self.booking,
            amount=100.0,
            payment_method='cash',
            source='front_desk',
            status='succeeded',
            reference='FD-100',
        )
        db.session.commit()

        self.assertIsNotNone(transaction.id)
        self.assertEqual(self.booking.amount_paid, 100.0)
        self.assertEqual(invoice.amount_paid, 100.0)
        self.assertEqual(invoice.balance_due, 200.0)
        self.assertEqual(invoice.status, 'partially_paid')

    def test_overpayment_is_rejected(self):
        sync_invoice_for_booking(self.booking)

        with self.assertRaises(ValueError):
            record_booking_payment(
                booking=self.booking,
                amount=350.0,
                payment_method='cash',
                source='front_desk',
                status='succeeded',
            )
