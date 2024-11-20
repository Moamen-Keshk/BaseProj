from flask import request, make_response, jsonify, current_app
from werkzeug.utils import secure_filename
from . import api
import logging
import random
from .constants import Constants
from .models import User, Room, Floor, Property
from .. import db
from app.auth.views import get_current_user
from datetime import datetime, timedelta, timezone
import os

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    confirmation_number = db.Column(db.Integer, unique=True)
    first_name = db.Column(db.String(32))
    last_name = db.Column(db.String(32))
    number_of_adults = db.Column(db.Integer)
    number_of_children = db.Column(db.Integer)
    payment_status_id = db.Column(db.Integer, db.ForeignKey('payment_status.id'), default=1)
    status_id = db.Column(db.Integer, db.ForeignKey('booking_status.id'), default=1)
    note = db.Column(db.Text())
    special_request = db.Column(db.Text())
    booking_date = db.Column(db.Date(), default=datetime.today().date())
    check_in = db.Column(db.Date())
    check_out = db.Column(db.Date())
    number_of_days = db.Column(db.Integer)
    rate = db.Column(db.Double)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    creator_id = db.Column(db.String(32), db.ForeignKey('users.uid'))

    def __init__(self, **kwargs):
        super(Booking, self).__init__(**kwargs)
        self.confirmation_number = random.randint(000000, 999999)

    def to_json(self):
        json_order = {
            'id': self.id,
            'confirmation_number': self.confirmation_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'number_of_adults': self.number_of_adults,
            'number_of_children': self.number_of_children,
            'payment_status': Constants.PaymentStatusCoding[self.payment_status_id],
            'status': Constants.BookingStatusCoding[self.status_id],
            'note': self.note,
            'special_request': self.special_request,
            'booking_date': self.booking_date,
            'check_in': self.check_in,
            'check_out': self.check_out,
            'number_of_days': self.number_of_days,
            'rate': self.rate,
            'creator': User.query.filter_by(id=self.creator_id).with_entities(User.username).first()[0]
        }
        return json_order

    @staticmethod
    def from_json(json_booking):
        first_name = json_booking.get('firstName')
        last_name = json_booking.get('lastName')
        number_of_adults = json_booking.get('numberOfAdults')
        number_of_children = json_booking.get('NumberOfChildren')
        payment_status_id = json_booking.get('paymentStatusID')
        note = json_booking.get('note')
        special_request = json_booking.get('specialRequest')
        booking_date = json_booking.get('bookingDate')
        check_in = json_booking.get('checkIn')
        check_out = json_booking.get('checkOut')
        number_of_days = json_booking.get('numberOfDays')
        rate = json_booking.get('rate')
        property_id = json_booking.get('propertyID')
        room_id = json_booking.get('roomID')
        return Booking(first_name=first_name, last_name=last_name, number_of_adults=number_of_adults,
                       number_of_children=number_of_children, payment_status_id=payment_status_id,
                       note=note, special_request=special_request, booking_date=booking_date,
                       check_in=check_in, check_out=check_out, number_of_days=number_of_days,
                       rate=rate, property_id=property_id, room_id=room_id)

    def change_status(self, status_id):
        self.status_id = status_id


class BookingStatus(db.Model):
    __tablename__ = 'booking_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True)
    name = db.Column(db.String(32), unique=True)
    color = db.Column(db.String(32), unique=True)

    @staticmethod
    def insert_status():
        status = {
            'Confirmed': ['CONFIRMED', 'Green'],
            'Completed': ['COMPLETED', 'Red'],
            'Cancelled': ['CANCELLED', 'Blue'],
            'No show': ['NO SHOW', 'purple']
        }
        for s in status:
            stat = BookingStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = BookingStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()

@api.route('/bookings', methods=['POST'])
def new_booking():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            booking = Booking.from_json(dict(request.json))
            booking.creator_id = resp
            db.session.add(booking)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Booking submitted.'
            }
            return make_response(jsonify(responseObject)), 201
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'expired',
        'message': 'Session expired, log in required!'
    }
    return make_response(jsonify(responseObject)), 202
