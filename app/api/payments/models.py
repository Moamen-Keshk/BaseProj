from app import db
from datetime import date, datetime, timezone


class Invoice(db.Model):
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(32), unique=True, nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False, unique=True)
    status = db.Column(db.String(32), default='open', nullable=False)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    issue_date = db.Column(db.Date, default=date.today, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    subtotal = db.Column(db.Float, default=0.0, nullable=False)
    tax_amount = db.Column(db.Float, default=0.0, nullable=False)
    total_amount = db.Column(db.Float, default=0.0, nullable=False)
    amount_paid = db.Column(db.Float, default=0.0, nullable=False)
    balance_due = db.Column(db.Float, default=0.0, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    booking = db.relationship(
        'Booking',
        backref=db.backref('invoice', uselist=False, cascade='all, delete-orphan', single_parent=True),
    )
    property = db.relationship(
        'Property',
        backref=db.backref('invoices', lazy=True, cascade='all, delete-orphan'),
    )
    line_items = db.relationship(
        'InvoiceLineItem',
        back_populates='invoice',
        cascade='all, delete-orphan',
        order_by='InvoiceLineItem.line_date.asc(), InvoiceLineItem.id.asc()',
    )
    payments = db.relationship(
        'Transaction',
        back_populates='invoice',
        cascade='all, delete-orphan',
        order_by='Transaction.created_at.desc(), Transaction.id.desc()',
    )

    def to_json(self, include_line_items=True, include_payments=True):
        payload = {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'property_id': self.property_id,
            'booking_id': self.booking_id,
            'guest_name': ' '.join(filter(None, [
                getattr(self.booking, 'first_name', None),
                getattr(self.booking, 'last_name', None),
            ])).strip(),
            'status': self.status,
            'currency': self.currency,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'subtotal': float(self.subtotal or 0.0),
            'tax_amount': float(self.tax_amount or 0.0),
            'total_amount': float(self.total_amount or 0.0),
            'amount_paid': float(self.amount_paid or 0.0),
            'balance_due': float(self.balance_due or 0.0),
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_line_items:
            payload['line_items'] = [line_item.to_json() for line_item in self.line_items]
        if include_payments:
            payload['payments'] = [payment.to_json() for payment in self.payments]
        return payload


class InvoiceLineItem(db.Model):
    __tablename__ = 'invoice_line_items'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    line_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, default=1.0, nullable=False)
    unit_price = db.Column(db.Float, default=0.0, nullable=False)
    amount = db.Column(db.Float, default=0.0, nullable=False)

    invoice = db.relationship('Invoice', back_populates='line_items')

    def to_json(self):
        return {
            'id': self.id,
            'invoice_id': self.invoice_id,
            'line_date': self.line_date.isoformat() if self.line_date else None,
            'description': self.description,
            'quantity': float(self.quantity or 0.0),
            'unit_price': float(self.unit_price or 0.0),
            'amount': float(self.amount or 0.0),
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)
    stripe_payment_intent_id = db.Column(db.String(128), unique=True, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='usd')
    status = db.Column(db.String(50), default='pending')  # pending, succeeded, failed
    payment_method = db.Column(db.String(32), default='card')
    source = db.Column(db.String(32), default='manual')
    reference = db.Column(db.String(128), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recorded_by = db.Column(db.String(32), nullable=True)
    is_vcc = db.Column(db.Boolean, default=False)  # True if OTA Virtual Card
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Establish relationship to Booking model
    booking = db.relationship('Booking', backref=db.backref('transactions', lazy=True))
    invoice = db.relationship('Invoice', back_populates='payments')

    def to_json(self):
        return {
            'id': self.id,
            'booking_id': self.booking_id,
            'invoice_id': self.invoice_id,
            'stripe_payment_intent_id': self.stripe_payment_intent_id,
            'amount': float(self.amount or 0.0),
            'currency': self.currency,
            'status': self.status,
            'payment_method': self.payment_method,
            'source': self.source,
            'reference': self.reference,
            'notes': self.notes,
            'recorded_by': self.recorded_by,
            'is_vcc': self.is_vcc,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


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
