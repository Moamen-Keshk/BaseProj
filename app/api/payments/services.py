from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date

import stripe
from flask import current_app

from app import db
from app.api.models import Booking
from app.api.payments.models import BookingVCC, Invoice, InvoiceLineItem, Transaction


TWOPLACES = Decimal('0.01')
SETTLED_PAYMENT_STATUSES = {'succeeded', 'captured', 'settled'}
NON_SETTLED_PAYMENT_STATUSES = {'pending', 'authorized', 'processing', 'requires_capture'}
REFUNDABLE_PAYMENT_STATUSES = SETTLED_PAYMENT_STATUSES


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


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


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


def _transaction_signed_amount(transaction):
    amount = Decimal(str(transaction.amount or 0.0))
    if transaction.transaction_type == 'refund':
        return amount * Decimal('-1')
    return amount


def _settled_transaction_total(booking):
    total = Decimal('0.00')
    for transaction in getattr(booking, 'transactions', []):
        if transaction.status not in SETTLED_PAYMENT_STATUSES:
            continue
        total += _transaction_signed_amount(transaction)
    return total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _pending_transaction_total(booking):
    total = Decimal('0.00')
    for transaction in getattr(booking, 'transactions', []):
        if transaction.status in NON_SETTLED_PAYMENT_STATUSES:
            total += Decimal(str(transaction.amount or 0.0))
    return total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _refunded_total_for_transaction(transaction):
    refunded = Decimal('0.00')
    for child_transaction in getattr(transaction, 'child_transactions', []):
        if (
            child_transaction.transaction_type == 'refund'
            and child_transaction.status in SETTLED_PAYMENT_STATUSES
        ):
            refunded += Decimal(str(child_transaction.amount or 0.0))
    return refunded.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _can_charge_vcc(booking):
    vcc_record = BookingVCC.query.filter_by(booking_id=booking.id).first()
    if not vcc_record:
        return False, 'No OTA virtual card is available for this booking.'
    if vcc_record.activation_date and vcc_record.activation_date.date() > date.today():
        return False, 'The OTA virtual card is not active yet.'
    return True, None


def recalculate_booking_financials(booking):
    settled_total = _settled_transaction_total(booking)
    booking.amount_paid = _as_float(max(settled_total, Decimal('0.00')))
    booking.update_payment_status()
    return booking.amount_paid


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

    settled_total = _settled_transaction_total(booking)
    invoice.subtotal = _as_float(subtotal)
    invoice.tax_amount = _as_float(invoice.tax_amount or 0.0)
    invoice.total_amount = _as_float(invoice.subtotal + invoice.tax_amount)
    invoice.amount_paid = _as_float(max(settled_total, Decimal('0.00')))
    invoice.balance_due = _as_float(max(0.0, invoice.total_amount - invoice.amount_paid))
    invoice.status = _invoice_status(invoice.total_amount, invoice.amount_paid)
    booking.amount_paid = invoice.amount_paid

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
    transaction_type='payment',
    external_channel=None,
    processor_reference=None,
    processor_status=None,
    effective_date=None,
    settlement_date=None,
):
    amount_value = _normalize_amount(amount)
    invoice = sync_invoice_for_booking(booking)

    if transaction_type == 'refund':
        raise ValueError('Use refund_booking_payment for refunds.')

    if is_vcc or payment_method == 'ota_vcc':
        can_charge_vcc, error_message = _can_charge_vcc(booking)
        if not can_charge_vcc:
            raise ValueError(error_message)

    if status in SETTLED_PAYMENT_STATUSES and amount_value > Decimal(str(invoice.balance_due or 0.0)) + TWOPLACES:
        raise ValueError('Payment amount cannot exceed the outstanding balance.')

    transaction = Transaction(
        booking=booking,
        booking_id=booking.id,
        invoice_id=invoice.id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        amount=_as_float(amount_value),
        currency=(currency or 'usd').lower(),
        status=status,
        transaction_type=transaction_type,
        payment_method=payment_method,
        source=source,
        external_channel=external_channel,
        reference=reference,
        processor_reference=processor_reference,
        processor_status=processor_status or status,
        notes=notes,
        recorded_by=recorded_by,
        is_vcc=is_vcc,
        effective_date=_parse_date(effective_date) or date.today(),
        settlement_date=_parse_date(settlement_date) if settlement_date else (
            date.today() if status in SETTLED_PAYMENT_STATUSES else None
        ),
    )
    db.session.add(transaction)
    db.session.flush()

    invoice = sync_invoice_for_booking(booking)
    recalculate_booking_financials(booking)
    invoice = sync_invoice_for_booking(booking)

    return transaction, invoice


def refund_booking_payment(
    booking,
    transaction,
    amount=None,
    reason=None,
    recorded_by=None,
    settlement_date=None,
):
    if transaction.booking_id != booking.id:
        raise ValueError('The selected payment does not belong to this booking.')
    if transaction.transaction_type != 'payment':
        raise ValueError('Only payment transactions can be refunded.')
    if transaction.status not in REFUNDABLE_PAYMENT_STATUSES:
        raise ValueError('Only settled payments can be refunded.')

    refundable_amount = (
        Decimal(str(transaction.amount or 0.0)) - _refunded_total_for_transaction(transaction)
    ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    refund_amount = _normalize_amount(amount or refundable_amount)
    if refund_amount > refundable_amount + TWOPLACES:
        raise ValueError('Refund amount exceeds the refundable balance for this payment.')

    invoice = sync_invoice_for_booking(booking)
    refund_transaction = Transaction(
        booking=booking,
        booking_id=booking.id,
        invoice_id=invoice.id,
        amount=_as_float(refund_amount),
        currency=(transaction.currency or 'usd').lower(),
        status='succeeded',
        transaction_type='refund',
        parent_transaction_id=transaction.id,
        payment_method=transaction.payment_method,
        source='refund',
        external_channel=transaction.external_channel,
        reference=transaction.reference,
        processor_reference=transaction.processor_reference,
        processor_status='refunded',
        notes=reason,
        recorded_by=recorded_by,
        is_vcc=transaction.is_vcc,
        effective_date=date.today(),
        settlement_date=_parse_date(settlement_date) or date.today(),
    )
    db.session.add(refund_transaction)
    db.session.flush()

    recalculate_booking_financials(booking)
    invoice = sync_invoice_for_booking(booking)
    return refund_transaction, invoice


def create_payment_intent_for_booking(booking, amount, currency='usd', is_vcc=False):
    stripe_secret = current_app.config.get('STRIPE_SECRET_KEY')
    if not stripe_secret:
        raise RuntimeError('Stripe is not configured in this environment.')

    amount_value = _normalize_amount(amount)
    invoice = sync_invoice_for_booking(booking)
    if is_vcc:
        can_charge_vcc, error_message = _can_charge_vcc(booking)
        if not can_charge_vcc:
            raise ValueError(error_message)
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
        booking=booking,
        booking_id=booking.id,
        invoice_id=invoice.id,
        stripe_payment_intent_id=intent.id,
        amount=_as_float(amount_value),
        currency=(currency or 'usd').lower(),
        status='pending',
        transaction_type='payment',
        payment_method='card',
        source='stripe',
        is_vcc=is_vcc,
        processor_status=intent.status,
        effective_date=date.today(),
    )
    db.session.add(transaction)
    db.session.commit()

    return intent, transaction, invoice


def mark_transaction_succeeded(transaction):
    if transaction.status == 'succeeded':
        return transaction

    booking = transaction.booking
    transaction.status = 'succeeded'
    transaction.processor_status = 'succeeded'
    transaction.settlement_date = transaction.settlement_date or date.today()
    recalculate_booking_financials(booking)
    sync_invoice_for_booking(booking)
    return transaction


def mark_transaction_failed(transaction):
    transaction.status = 'failed'
    transaction.processor_status = 'failed'
    recalculate_booking_financials(transaction.booking)
    sync_invoice_for_booking(transaction.booking)
    return transaction


def mark_transaction_authorized(transaction):
    transaction.status = 'authorized'
    transaction.processor_status = 'authorized'
    recalculate_booking_financials(transaction.booking)
    sync_invoice_for_booking(transaction.booking)
    return transaction
