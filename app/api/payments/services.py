from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date

import stripe
from flask import current_app

from app import db
from app.api.models import Booking
from app.api.payments.models import Invoice, InvoiceLineItem, Transaction


TWOPLACES = Decimal('0.01')


def _normalize_amount(value):
    try:
        amount = Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('A valid amount is required.')

    if amount <= 0:
        raise ValueError('Amount must be greater than zero.')

    return amount


def _as_float(value):
    return float(Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP))


def _generate_invoice_number():
    invoice = Invoice.query.order_by(Invoice.id.desc()).first()
    next_number = (invoice.id + 1) if invoice else 1
    return f"INV-{date.today().strftime('%Y%m%d')}-{next_number:05d}"


def _invoice_status(total_amount, amount_paid):
    total_amount = Decimal(str(total_amount or 0.0))
    amount_paid = Decimal(str(amount_paid or 0.0))
    balance_due = total_amount - amount_paid

    if total_amount <= 0:
        return 'draft'
    if balance_due <= 0:
        return 'paid'
    if amount_paid > 0:
        return 'partially_paid'
    return 'open'


def _line_items_for_booking(booking):
    booking_rates = sorted(booking.booking_rates, key=lambda rate: (rate.rate_date, rate.id or 0))
    if booking_rates:
        items = []
        for booking_rate in booking_rates:
            nightly_rate = _as_float(booking_rate.nightly_rate or 0.0)
            items.append({
                'line_date': booking_rate.rate_date,
                'description': f'Accommodation for {booking_rate.rate_date.isoformat()}',
                'quantity': 1.0,
                'unit_price': nightly_rate,
                'amount': nightly_rate,
            })
        return items

    total_amount = _as_float(booking.rate or 0.0)
    quantity = float(booking.number_of_days or 1)
    unit_price = _as_float(total_amount / quantity) if quantity else total_amount
    stay_window = 'Accommodation'
    if booking.check_in and booking.check_out:
        stay_window = (
            f'Accommodation from {booking.check_in.isoformat()} '
            f'to {booking.check_out.isoformat()}'
        )
    return [{
        'line_date': booking.check_in,
        'description': stay_window,
        'quantity': quantity,
        'unit_price': unit_price,
        'amount': total_amount,
    }]


def sync_invoice_for_booking(booking, due_date=None, tax_amount=None, notes=None):
    if booking.id is None:
        db.session.flush()

    invoice = getattr(booking, 'invoice', None)
    if invoice is None and booking.id is not None:
        invoice = Invoice.query.filter_by(booking_id=booking.id).first()
    if invoice is None:
        invoice = Invoice(
            booking=booking,
            property_id=booking.property_id,
            invoice_number=_generate_invoice_number(),
            currency='USD',
            issue_date=date.today(),
        )
        db.session.add(invoice)
        db.session.flush()

    invoice.property_id = booking.property_id
    invoice.due_date = due_date or invoice.due_date or booking.check_in or date.today()
    if notes is not None:
        invoice.notes = notes
    if tax_amount is not None:
        invoice.tax_amount = _as_float(tax_amount)

    invoice.line_items.clear()
    subtotal = 0.0
    for line_item in _line_items_for_booking(booking):
        subtotal += float(line_item['amount'])
        invoice.line_items.append(InvoiceLineItem(**line_item))

    invoice.subtotal = _as_float(subtotal)
    invoice.tax_amount = _as_float(invoice.tax_amount or 0.0)
    invoice.total_amount = _as_float(invoice.subtotal + invoice.tax_amount)
    invoice.amount_paid = _as_float(booking.amount_paid or 0.0)
    invoice.balance_due = _as_float(max(0.0, invoice.total_amount - invoice.amount_paid))
    invoice.status = _invoice_status(invoice.total_amount, invoice.amount_paid)

    return invoice


def record_booking_payment(
    booking,
    amount,
    payment_method='cash',
    source='manual',
    status='succeeded',
    reference=None,
    notes=None,
    currency='usd',
    recorded_by=None,
    stripe_payment_intent_id=None,
    is_vcc=False,
):
    amount_value = _normalize_amount(amount)
    invoice = sync_invoice_for_booking(booking)

    if status == 'succeeded' and amount_value > Decimal(str(invoice.balance_due or 0.0)) + TWOPLACES:
        raise ValueError('Payment amount cannot exceed the outstanding balance.')

    transaction = Transaction(
        booking_id=booking.id,
        invoice_id=invoice.id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        amount=_as_float(amount_value),
        currency=(currency or 'usd').lower(),
        status=status,
        payment_method=payment_method,
        source=source,
        reference=reference,
        notes=notes,
        recorded_by=recorded_by,
        is_vcc=is_vcc,
    )
    db.session.add(transaction)

    if status == 'succeeded':
        booking.amount_paid = _as_float(Decimal(str(booking.amount_paid or 0.0)) + amount_value)
        booking.update_payment_status()
        invoice = sync_invoice_for_booking(booking)

    return transaction, invoice


def create_payment_intent_for_booking(booking, amount, currency='usd', is_vcc=False):
    stripe_secret = current_app.config.get('STRIPE_SECRET_KEY')
    if not stripe_secret:
        raise RuntimeError('Stripe is not configured in this environment.')

    amount_value = _normalize_amount(amount)
    invoice = sync_invoice_for_booking(booking)
    if amount_value > Decimal(str(invoice.balance_due or 0.0)) + TWOPLACES:
        raise ValueError('Payment amount cannot exceed the outstanding balance.')

    stripe.api_key = stripe_secret
    amount_in_cents = int(amount_value * 100)

    intent = stripe.PaymentIntent.create(
        amount=amount_in_cents,
        currency=(currency or 'usd').lower(),
        metadata={
            'booking_id': booking.id,
            'invoice_id': invoice.id,
            'property_id': booking.property_id,
            'is_vcc': str(bool(is_vcc)).lower(),
        },
        setup_future_usage='off_session' if is_vcc else None,
    )

    transaction = Transaction(
        booking_id=booking.id,
        invoice_id=invoice.id,
        stripe_payment_intent_id=intent.id,
        amount=_as_float(amount_value),
        currency=(currency or 'usd').lower(),
        status='pending',
        payment_method='card',
        source='stripe',
        is_vcc=is_vcc,
    )
    db.session.add(transaction)
    db.session.commit()

    return intent, transaction, invoice


def mark_transaction_succeeded(transaction):
    if transaction.status == 'succeeded':
        return transaction

    booking = transaction.booking
    booking.amount_paid = _as_float(
        Decimal(str(booking.amount_paid or 0.0)) + Decimal(str(transaction.amount or 0.0))
    )
    transaction.status = 'succeeded'
    booking.update_payment_status()
    sync_invoice_for_booking(booking)
    return transaction


def mark_transaction_failed(transaction):
    transaction.status = 'failed'
    return transaction
