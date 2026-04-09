from decimal import InvalidOperation

import stripe
from flask import request, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError
from app.api.models import db, Booking
from app.api.decorators import require_auth
from app.api.payments.models import Transaction
from . import payments_bp

@payments_bp.route('/create-payment-intent', methods=['POST'])
@require_auth
def create_payment_intent():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    data = request.json

    booking_id = data.get('booking_id')
    amount = data.get('amount')  # Ensure this is passed securely or calculated from DB
    is_ota_vcc = data.get('is_vcc', False)

    booking = Booking.query.get_or_404(booking_id)

    try:
        # Stripe requires amount in cents (e.g., $50.00 = 5000)
        amount_in_cents = int(float(amount) * 100)

        # Create a PaymentIntent with the order amount and currency
        intent = stripe.PaymentIntent.create(
            amount=amount_in_cents,
            currency='usd',
            metadata={'booking_id': booking.id, 'is_vcc': is_ota_vcc},
            # If it's a VCC, you might want to save the card details to charge later
            # based on the OTA activation date (e.g., setup_future_usage)
            setup_future_usage='off_session' if is_ota_vcc else None
        )

        # Log to database
        txn = Transaction(
            booking_id=booking.id,
            stripe_payment_intent_id=intent.id,
            amount=amount,
            is_vcc=is_ota_vcc
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({
            'clientSecret': intent.client_secret,
            'paymentIntentId': intent.id
        })
    except (TypeError, ValueError, InvalidOperation) as exc:
        return jsonify(error=str(exc)), 400
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
            txn.status = 'succeeded'
            # Here you would also update the overall Booking payment status to 'paid'
            db.session.commit()

    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        txn = Transaction.query.filter_by(stripe_payment_intent_id=payment_intent['id']).first()
        if txn:
            txn.status = 'failed'
            db.session.commit()

    return jsonify(success=True), 200
