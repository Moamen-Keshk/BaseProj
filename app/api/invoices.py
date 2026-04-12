import logging
from datetime import date

from flask import jsonify, make_response, request
from sqlalchemy import or_

from . import api
from .. import db
from app.api.decorators import require_permission
from app.api.models import Booking
from app.api.payments.models import BookingVCC, Invoice, Transaction
from app.api.payments.services import (
    create_payment_intent_for_booking,
    record_booking_payment,
    refund_booking_payment,
    sync_invoice_for_booking,
)
from app.api.payments.utils import decrypt_data
from app.auth.utils import get_current_user


def _parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def _get_booking(property_id, booking_id):
    return Booking.query.filter_by(id=booking_id, property_id=property_id).first()


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


@api.route('/properties/<int:property_id>/invoices', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_finance')
def list_invoices(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        query = Invoice.query.filter_by(property_id=property_id)

        booking_id = request.args.get('booking_id', type=int)
        status = request.args.get('status', type=str)
        guest = request.args.get('guest', type=str)

        if booking_id:
            query = query.filter(Invoice.booking_id == booking_id)
        if status:
            query = query.filter(Invoice.status == status.strip().lower())
        if guest:
            guest_term = f"%{guest.strip()}%"
            query = query.join(Booking).filter(
                or_(
                    Booking.first_name.ilike(guest_term),
                    Booking.last_name.ilike(guest_term),
                    Booking.email.ilike(guest_term),
                )
            )

        invoices = query.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all()

        return make_response(jsonify({
            'status': 'success',
            'data': [invoice.to_json(include_line_items=False, include_payments=False) for invoice in invoices]
        })), 200
    except Exception as exc:
        logging.exception("Error in list_invoices: %s", exc)
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch invoices.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/invoice', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_finance')
def get_booking_invoice(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        invoice = getattr(booking, 'invoice', None)
        if invoice is None:
            invoice = sync_invoice_for_booking(booking)
            db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'data': invoice.to_json()
        })), 200
    except Exception as exc:
        logging.exception("Error in get_booking_invoice: %s", exc)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch invoice.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/invoice/sync', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_finance')
def sync_booking_invoice_route(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        payload = request.get_json(silent=True) or {}
        invoice = sync_invoice_for_booking(
            booking,
            due_date=_parse_date(payload.get('due_date')),
            tax_amount=payload.get('tax_amount'),
            notes=payload.get('notes'),
        )
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Invoice synchronized successfully.',
            'data': invoice.to_json()
        })), 200
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception("Error in sync_booking_invoice_route: %s", exc)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to synchronize invoice.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/payments', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_finance')
def list_booking_payments(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        transactions = (
            Transaction.query
            .filter_by(booking_id=booking.id)
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .all()
        )

        return make_response(jsonify({
            'status': 'success',
            'data': [transaction.to_json() for transaction in transactions]
        })), 200
    except Exception as exc:
        logging.exception("Error in list_booking_payments: %s", exc)
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch payments.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/payments', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_finance')
def add_booking_payment(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        payload = request.get_json(silent=True) or {}
        transaction, invoice = record_booking_payment(
            booking=booking,
            amount=payload.get('amount'),
            payment_method=payload.get('payment_method', 'cash'),
            source=payload.get('source', 'manual'),
            status=payload.get('status', 'succeeded'),
            reference=payload.get('reference'),
            notes=payload.get('notes'),
            currency=payload.get('currency', 'usd'),
            recorded_by=get_current_user(),
            is_vcc=_parse_bool(payload.get('is_vcc')) or payload.get('payment_method') == 'ota_vcc',
            external_channel=payload.get('external_channel'),
            processor_reference=payload.get('processor_reference'),
            processor_status=payload.get('processor_status'),
            effective_date=_parse_date(payload.get('effective_date')),
            settlement_date=_parse_date(payload.get('settlement_date')),
        )
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Payment recorded successfully.',
            'data': {
                'payment': transaction.to_json(),
                'invoice': invoice.to_json()
            }
        })), 201
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception("Error in add_booking_payment: %s", exc)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to record payment.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/payments/<int:transaction_id>/refund', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_finance')
def refund_booking_payment_route(property_id, booking_id, transaction_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        transaction = Transaction.query.filter_by(
            id=transaction_id,
            booking_id=booking.id,
        ).first()
        if not transaction:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Payment not found.'
            })), 404

        payload = request.get_json(silent=True) or {}
        refund_txn, invoice = refund_booking_payment(
            booking=booking,
            transaction=transaction,
            amount=payload.get('amount'),
            reason=payload.get('reason'),
            recorded_by=get_current_user(),
            settlement_date=_parse_date(payload.get('settlement_date')),
        )
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Refund recorded successfully.',
            'data': {
                'payment': refund_txn.to_json(),
                'invoice': invoice.to_json(),
            }
        })), 201
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except Exception as exc:
        logging.exception("Error in refund_booking_payment_route: %s", exc)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to record refund.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/payments/create-intent', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_finance')
def create_booking_payment_intent(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        payload = request.get_json(silent=True) or {}
        intent, transaction, invoice = create_payment_intent_for_booking(
            booking=booking,
            amount=payload.get('amount') or booking.balance_due,
            currency=payload.get('currency', 'usd'),
            is_vcc=bool(payload.get('is_vcc', False)),
        )

        return make_response(jsonify({
            'status': 'success',
            'data': {
                'clientSecret': intent.client_secret,
                'paymentIntentId': intent.id,
                'payment': transaction.to_json(),
                'invoice': invoice.to_json(include_payments=False)
            }
        })), 201
    except ValueError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 400
    except RuntimeError as exc:
        db.session.rollback()
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 503
    except Exception as exc:
        logging.exception("Error in create_booking_payment_intent: %s", exc)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to create payment intent.'
        })), 500


@api.route('/properties/<int:property_id>/bookings/<int:booking_id>/vcc', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('view_finance')
def get_booking_vcc(property_id, booking_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        booking = _get_booking(property_id, booking_id)
        if not booking:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found.'
            })), 404

        vcc_record = BookingVCC.query.filter_by(booking_id=booking.id).first()
        if not vcc_record:
            return make_response(jsonify({'status': 'success', 'data': {'has_vcc': False}})), 200

        return make_response(jsonify({
            'status': 'success',
            'data': {
                'has_vcc': True,
                'card_number': decrypt_data(vcc_record.encrypted_card_number),
                'exp_month': vcc_record.exp_month,
                'exp_year': vcc_record.exp_year,
                'cvc': decrypt_data(vcc_record.encrypted_cvc),
                'can_charge_now': (
                    vcc_record.activation_date is None
                    or vcc_record.activation_date.date() <= date.today()
                ),
                'activation_date': (
                    vcc_record.activation_date.isoformat()
                    if vcc_record.activation_date else None
                )
            }
        })), 200
    except RuntimeError as exc:
        return make_response(jsonify({'status': 'fail', 'message': str(exc)})), 503
    except Exception as exc:
        logging.exception("Error in get_booking_vcc: %s", exc)
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to fetch VCC details.'
        })), 500
