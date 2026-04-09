from app import db
from datetime import datetime, timezone


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    stripe_payment_intent_id = db.Column(db.String(128), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='usd')
    status = db.Column(db.String(50), default='pending')  # pending, succeeded, failed
    is_vcc = db.Column(db.Boolean, default=False)  # True if OTA Virtual Card
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Establish relationship to Booking model
    booking = db.relationship('Booking', backref=db.backref('transactions', lazy=True))


class BookingVCC(db.Model):
    __tablename__ = 'booking_vcc'

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)

    # Store encrypted strings!
    encrypted_card_number = db.Column(db.String(255), nullable=False)
    encrypted_cvc = db.Column(db.String(255), nullable=False)

    exp_month = db.Column(db.String(2), nullable=False)
    exp_year = db.Column(db.String(4), nullable=False)
    activation_date = db.Column(db.DateTime, nullable=True)  # VCCs often have activation dates