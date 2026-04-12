import stripe
from flask import request, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.api.decorators import require_auth
from app.api.models import Booking
from app.api.payments.models import BookingVCC, Transaction
from app.api.payments.services import (
    create_payment_intent_for_booking,
    mark_transaction_authorized,
    mark_transaction_failed,
    mark_transaction_succeeded,
)
from . import payments_bp
from .utils import decrypt_data


@payments_bp.route('/create-payment-intent', methods=['POST'])
@require_auth
def create_payment_intent():
    data = request.json

    booking_id = data.get('booking_id')
    amount = data.get('amount')
    is_ota_vcc = data.get('is_vcc', False)

    booking = Booking.query.get_or_404(booking_id)

    try:
        intent, txn, _invoice = create_payment_intent_for_booking(
            booking=booking,
            amount=amount,
            currency=data.get('currency', 'usd'),
            is_vcc=is_ota_vcc,
        )

        return jsonify({
            'clientSecret': intent.client_secret,
            'paymentIntentId': intent.id
        })
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except stripe.error.StripeError as exc:
        return jsonify(error=str(exc)), 403
    except SQLAlchemyError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 500


@payments_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    endpoint_secret = current_app.config['STRIPE_WEBHOOK_SECRET']

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify(success=False), 400

    # Handle the event
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']

        # Update DB
        txn = Transaction.query.filter_by(stripe_payment_intent_id=payment_intent['id']).first()
        if txn:
            txn.processor_reference = payment_intent.get('latest_charge')
            txn.processor_status = payment_intent.get('status')
            mark_transaction_succeeded(txn)
            db.session.commit()

    elif event['type'] == 'payment_intent.amount_capturable_updated':
        payment_intent = event['data']['object']
        txn = Transaction.query.filter_by(stripe_payment_intent_id=payment_intent['id']).first()
        if txn:
            txn.processor_reference = payment_intent.get('latest_charge')
            txn.processor_status = payment_intent.get('status')
            mark_transaction_authorized(txn)
            db.session.commit()

    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        txn = Transaction.query.filter_by(stripe_payment_intent_id=payment_intent['id']).first()
        if txn:
            txn.processor_reference = payment_intent.get('latest_charge')
            txn.processor_status = payment_intent.get('status')
            mark_transaction_failed(txn)
            db.session.commit()

    return jsonify(success=True), 200


@payments_bp.route('/vcc/<int:booking_id>', methods=['GET'])
@require_auth
def get_vcc_details(booking_id):
    vcc_record = BookingVCC.query.filter_by(booking_id=booking_id).first()

    if not vcc_record:
        return jsonify({"has_vcc": False}), 200

    try:
        return jsonify({
            "has_vcc": True,
            "card_number": decrypt_data(vcc_record.encrypted_card_number),
            "exp_month": vcc_record.exp_month,
            "exp_year": vcc_record.exp_year,
            "cvc": decrypt_data(vcc_record.encrypted_cvc)
        }), 200
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
