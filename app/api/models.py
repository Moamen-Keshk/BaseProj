from datetime import datetime, timezone, date
import logging
from itsdangerous import (URLSafeTimedSerializer
                          as Serializer, BadSignature, SignatureExpired)
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

from app import db
import random
from app.api.constants import Constants
import json
import hashlib

def parse_date(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        return date(*value)
    elif isinstance(value, date):
        return value
    return None


# 1. Define PMS-Specific Permissions
class PMSPermission:
    VIEW_BOOKINGS = 'view_bookings'
    MANAGE_BOOKINGS = 'manage_bookings'
    VIEW_RATES = 'view_rates'
    MANAGE_RATES = 'manage_rates'
    MANAGE_CHANNELS = 'manage_channels'
    UPDATE_ROOM_STATUS = 'update_room_status'
    MANAGE_STAFF = 'manage_staff'
    MANAGE_PROPERTY = 'manage_property'


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    description = db.Column(db.String(128))
    # Storing permissions as a JSON list of strings
    permissions_json = db.Column(db.JSON, default=list)

    @staticmethod
    def insert_roles():
        roles = {
            'Property Admin': {
                'desc': 'Full control over a specific property',
                'perms': [
                    PMSPermission.VIEW_BOOKINGS, PMSPermission.MANAGE_BOOKINGS,
                    PMSPermission.VIEW_RATES, PMSPermission.MANAGE_RATES,
                    PMSPermission.MANAGE_CHANNELS, PMSPermission.UPDATE_ROOM_STATUS,
                    PMSPermission.MANAGE_STAFF, PMSPermission.MANAGE_PROPERTY
                ]
            },
            'Revenue Manager': {
                'desc': 'Manages rates, channels, and availability',
                'perms': [
                    PMSPermission.VIEW_BOOKINGS, PMSPermission.VIEW_RATES,
                    PMSPermission.MANAGE_RATES, PMSPermission.MANAGE_CHANNELS,
                    PMSPermission.MANAGE_STAFF  # <--- ADDED
                ]
            },
            'Front Desk': {
                'desc': 'Manages daily bookings and room statuses',
                'perms': [
                    PMSPermission.VIEW_BOOKINGS, PMSPermission.MANAGE_BOOKINGS,
                    PMSPermission.VIEW_RATES, PMSPermission.UPDATE_ROOM_STATUS,
                    PMSPermission.MANAGE_STAFF  # <--- ADDED
                ]
            },
            'Housekeeping': {
                'desc': 'Can only update room statuses',
                'perms': [PMSPermission.UPDATE_ROOM_STATUS]
            },
        }
        for role_name, role_data in roles.items():
            role = Role.query.filter_by(name=role_name).first()
            if role is None:
                role = Role(name=role_name)
            role.description = role_data['desc']
            role.permissions_json = role_data['perms']
            db.session.add(role)
        db.session.commit()

class UserPropertyAccess(db.Model):
    __tablename__ = 'user_property_access'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.uid'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    account_status_id = db.Column(db.Integer, default=1)

    # Ensure a user only has one role per property
    __table_args__ = (
        db.UniqueConstraint('user_id', 'property_id', name='uq_user_property_role'),
    )

    user = db.relationship('User', backref=db.backref('property_accesses', lazy='dynamic'))
    property = db.relationship('Property', backref=db.backref('staff_access', lazy='dynamic'))
    role = db.relationship('Role')


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    uid = db.Column(db.String(32), primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)

    # Global Super Admin (Replaces the old global role)
    is_super_admin = db.Column(db.Boolean, default=False)

    password_hash = db.Column(db.String(128))
    confirmed = db.Column(db.Boolean, default=False)
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    member_since = db.Column(db.DateTime(), default=datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime(), default=datetime.now(timezone.utc))
    avatar_hash = db.Column(db.String(32))

    orders = db.relationship('Order', backref='creator', lazy='dynamic')
    notifications = db.relationship('Notification', backref='to_user_uid', lazy='dynamic')

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        # Automatically grant Super Admin if email matches the config
        if self.email == current_app.config.get('FLASKY_ADMIN'):
            self.is_super_admin = True

        if self.email is not None and self.avatar_hash is None:
            self.avatar_hash = self.gravatar_hash()

    # Flask-Login requires a get_id method that returns a string of the primary key
    def get_id(self):
        return str(self.uid)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:1000')

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- Token Methods (Updated to use self.uid instead of self.id) ---

    def generate_confirmation_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'confirm': self.uid}).decode('utf-8')

    @staticmethod
    def verify_confirmation_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        return User.query.get(data['confirm'])

    def confirm(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except Exception as e:
            logging.exception(e)
            return False
        if data.get('confirm') != self.uid:
            return False
        self.confirmed = True
        db.session.add(self)
        return True

    def generate_reset_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'reset': self.uid}).decode('utf-8')

    @staticmethod
    def reset_password(token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except Exception as e:
            logging.exception(e)
            return False
        user = User.query.get(data.get('reset'))
        if user is None:
            return False
        user.password = new_password
        db.session.add(user)
        return True

    def generate_email_change_token(self, new_email):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'change_email': self.uid, 'new_email': new_email}).decode('utf-8')

    def change_email(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except Exception as e:
            logging.exception(e)
            return False
        if data.get('change_email') != self.uid:
            return False
        new_email = data.get('new_email')
        if new_email is None:
            return False
        if self.query.filter_by(email=new_email).first() is not None:
            return False
        self.email = new_email
        self.avatar_hash = self.gravatar_hash()
        db.session.add(self)
        return True

    def generate_auth_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'id': self.uid}).decode('utf-8')

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        return User.query.get(data['id'])

    def gravatar_hash(self):
        return hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()

    def gravatar(self, size=100, default='identicon', rating='g'):
        url = 'https://secure.gravatar.com/avatar'
        hash_str = self.avatar_hash or self.gravatar_hash()
        return f'{url}/{hash_str}?s={size}&d={default}&r={rating}'

    def to_json(self):
        return {
            'uid': self.uid,
            'email': self.email,
            'username': self.username,
            'name': self.name,
            'location': self.location,
            'about_me': self.about_me,
            # Convert datetime objects to strings so they don't break JSON
            'member_since': self.member_since.isoformat() if self.member_since else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'avatar_hash': self.avatar_hash,
            'is_super_admin': self.is_super_admin
        }

    # --- Utility Methods ---

    def ping(self):
        # 1. Update the timestamp to RIGHT NOW
        self.last_seen = datetime.now(timezone.utc)

        # 2. Add the user to the database session so it saves
        db.session.add(self)
        db.session.commit() # Add this if you want it to save to the database immediately


class AnonymousUser(AnonymousUserMixin):
    @staticmethod
    def can():
        return False

    @staticmethod
    def is_administrator():
        return False


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text)
    title = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)
    has_action = db.Column(db.Boolean, default=False)
    to_user = db.Column(db.String(32), db.ForeignKey('users.uid'))
    routing = db.Column(db.String(32))

    def to_json(self):
        json_notification = {
            'id': self.id,
            'body': self.body,
            'title': self.title,
            'is_read': self.is_read,
            'has_action': self.has_action,
            'to_user': self.to_user,
            'fire_date': self.timestamp,
            'routing': self.routing
        }
        return json_notification


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.Integer, unique=True)
    fullname = db.Column(db.String(64))
    payment = db.Column(db.String(64), default='Unpaid')
    status_id = db.Column(db.Integer, db.ForeignKey('order_status.id'), default=1)
    note = db.Column(db.Text())
    working_days = db.Column(db.Integer)
    due_date = db.Column(db.Date())
    completion_date = db.Column(db.Date())
    sending_date = db.Column(db.Date())
    fee = db.Column(db.Integer)
    order_date = db.Column(db.Date(), default=datetime.today().date())
    creator_id = db.Column(db.String(32), db.ForeignKey('users.uid'))

    def __init__(self, **kwargs):
        super(Order, self).__init__(**kwargs)
        self.barcode = random.randint(000000, 999999)
        self.due_date = self.date_by_adding_business_days(datetime.today().date(), self.working_days)

    @staticmethod
    def date_by_adding_business_days(from_date, add_days):
        business_days_to_add = add_days
        current_date = from_date
        while business_days_to_add > 0:
            current_date += timedelta(days=1)
            weekday = current_date.weekday()
            if weekday >= 5:  # sunday = 6
                continue
            business_days_to_add -= 1
        return current_date

    def to_json(self):
        json_order = {
            'id': self.id,
            'fullname': self.fullname,
            'status': Constants.OrderStatusCoding[self.status_id],
            'working_days': self.working_days,
            'due_date': self.due_date.strftime("%d-%m-%y"),
            'completion_date': self.completion_date.strftime("%d-%m-%y") if self.completion_date is not None else '…',
            'sending_date': self.sending_date.strftime("%d-%m-%y") if self.sending_date is not None else '…',
            'fee': self.fee,
            'order_date': self.order_date.strftime("%d-%m-%y"),
            'creator': User.query.filter_by(id=self.creator_id).with_entities(User.username).first()[0],
            'barcode': self.barcode,
            'payment': self.payment,
            'note': self.note,
        }
        return json_order

    @staticmethod
    def from_json(json_order):
        fullname = json_order.get('fullname')
        return Order(fullname=fullname)

    def change_status(self, status_id):
        self.status_id = status_id


class OrderStatus(db.Model):
    __tablename__ = 'order_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_status():
        status = {
            'Draft': ['DRAFT', 'gray'],
            'Received': ['RECEIVED', 'yellow'],
            'Solicitor': ['SOLICITOR', 'brown'],
            'FCDO': ['FCDO', 'purple'],
            'Consulate': ['CONSULATE', 'blue'],
            'RFS': ['RFS', 'orange'],
            'Completed': ['COMPLETED', 'green'],
            'Cancelled': ['CANCELLED', 'red']
        }
        for s in status:
            stat = OrderStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = OrderStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()

# Association table for the many-to-many relationship
property_amenities = db.Table('property_amenities',
    db.Column('property_id', db.Integer, db.ForeignKey('properties.id'), primary_key=True),
    db.Column('amenity_id', db.Integer, db.ForeignKey('amenities.id'), primary_key=True)
)

class Property(db.Model):
    __tablename__ = 'properties'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32))
    address = db.Column(db.String(64))
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(120))
    status_id = db.Column(db.Integer, db.ForeignKey('property_status.id'), default=1)
    published_date = db.Column(db.Date(), default=datetime.today().date())

    # 👉 1. Many-to-Many: Safe to leave as is. SQLAlchemy automatically cleans up the association table.
    amenities = db.relationship('Amenity', secondary=property_amenities, lazy='subquery',
                                backref=db.backref('properties', lazy=True))

    # 👉 2. ONE-TO-MANY CASCADES: Add these to force deletion of child rows when Property is deleted.
    # Note: If you already have `backref='property'` defined inside the Floor/Room models,
    # you can use `overlaps="property"` to prevent SQLAlchemy warnings.
    floors = db.relationship('Floor', backref='property_ref', lazy=True, cascade="all, delete-orphan")
    rooms = db.relationship('Room', backref='property_ref', lazy=True, cascade="all, delete-orphan")
    bookings = db.relationship('Booking', backref='property_ref', lazy=True, cascade="all, delete-orphan")
    rate_plans = db.relationship('RatePlan', backref='property_ref', lazy=True, cascade="all, delete-orphan")
    seasons = db.relationship('Season', backref='property_ref', lazy=True, cascade="all, delete-orphan")
    access_roles = db.relationship('UserPropertyAccess', backref='property_ref', lazy=True, cascade="all, delete-orphan")


    def __init__(self, **kwargs):
        super(Property, self).__init__(**kwargs)

    def to_json(self):
        json_property = {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'phone_number': self.phone_number,
            'email': self.email,
            'status': Constants.PropertyStatusCoding[self.status_id],
            'published_date': self.published_date.strftime("%d-%m-%y"),
            'amenities': [a.to_json() for a in self.amenities]
        }
        return json_property

    @staticmethod
    def from_json(json_property):
        name = json_property.get('name')
        address = json_property.get('address')
        phone_number = json_property.get('phone_number')
        email = json_property.get('email')

        return Property(
            name=name,
            address=address,
            phone_number=phone_number,
            email=email
        )

class PropertyStatus(db.Model):
    __tablename__ = 'property_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_status():
        status = {
            'Open': ['OPEN', 'Green'],
            'Pre-Open': ['PRE-OPEN', 'yellow'],
            'Hold': ['HOLD', 'blue'],
            'Closed': ['CLOSED', 'red'],
            'Maintain': ['MAINTAIN', 'brown']
        }
        for s in status:
            stat = PropertyStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = PropertyStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32))
    capacity = db.Column(db.Integer)
    description = db.Column(db.String(64))

    def __init__(self, **kwargs):
        super(Category, self).__init__(**kwargs)

    def to_json(self):
        json_category = {
            'id': self.id,
            'name': self.name,
            'capacity': self.capacity,
            'description': self.description
        }
        return json_category

    @staticmethod
    def from_json(json_category):
        name = json_category.get('name')
        capacity = json_category.get('capacity')
        description = json_category.get('description')
        return Category(name=name, capacity=capacity, description=description)

    @staticmethod
    def insert_categories():
        cat = {
            'Single': [1, ''],
            'Double': [2, ''],
            'Twin': [2, ''],
            'Triple': [3, '']
        }
        for c in cat:
            categ = Category.query.filter_by(name=c).first()
            if categ is None:
                categ = Category(name=c, capacity=cat[c][0], description=cat[c][1])
            db.session.add(categ)
        db.session.commit()

class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.Integer)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id'))
    status_id = db.Column(db.Integer, db.ForeignKey('room_status.id'), default=1)

    def __init__(self, **kwargs):
        super(Room, self).__init__(**kwargs)

    def to_json(self):
        json_room = {
            'id': self.id,
            'room_number': self.room_number,
            'property_id': self.property_id,
            'category_id': self.category_id,
            'floor_id': self.floor_id,
            'status_id': self.status_id
        }
        return json_room

    @staticmethod
    def from_json(json_room):
        room_number = json_room.get('room_number')
        property_id = json_room.get('property_id')
        category_id = json_room.get('category_id')
        floor_id = json_room.get('floor_id')
        status_id = json_room.get('status_id')
        return Room(room_number=room_number, property_id=property_id, category_id=category_id, floor_id=floor_id, status_id=status_id)


class RoomStatus(db.Model):
    __tablename__ = 'room_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_status():
        status = {
            'Available': ['AVAILABLE', 'blue'],
            'Booked': ['BOOKED', 'green'],
            'Blocked': ['BLOCKED', 'red']
        }
        for s in status:
            stat = RoomStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = RoomStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()

class Floor(db.Model):
    __tablename__ = 'floors'
    id = db.Column(db.Integer, primary_key=True)
    floor_number = db.Column(db.Integer)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'))
    rooms = db.relationship('Room', backref='floor', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Floor, self).__init__(**kwargs)

    def to_json(self):
        json_floor = {
            'id': self.id,
            'floor_number': self.floor_number,
            'property_id': self.property_id,
            'rooms': [room.to_json() for room in self.rooms]
        }
        return json_floor

    @staticmethod
    def from_json(json_floor):
        floor_number = json_floor.get('floor_number')
        property_id = json_floor.get('property_id')
        rooms = json_floor.get('rooms')
        rooms_list = []
        for room in rooms:
            rooms_list.append(Room.from_json(json.loads(room)))
        return Floor(floor_number=floor_number, property_id=property_id, rooms=rooms_list)

class PaymentStatus(db.Model):
    __tablename__ = 'payment_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True)
    name = db.Column(db.String(32), unique=True)
    color = db.Column(db.String(32), unique=True)

    @staticmethod
    def insert_status():
        status = {
            'Paid': ['PAID', 'Green'],
            'Unpaid': ['UNPAID', 'Red'],
            'POA': ['POA', 'Yellow'],
            'Suspended': ['SUSPENDED', 'Purple']
        }
        for s in status:
            stat = PaymentStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = PaymentStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()

    def to_json(self):
        json_status = {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'color': self.color
        }
        return json_status

    @staticmethod
    def from_json(json_status):
        code = json_status.get('code')
        name = json_status.get('name')
        color = json_status.get('color')
        return PaymentStatus(code=code, name=name, color=color)


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    confirmation_number = db.Column(db.Integer, unique=True)
    first_name = db.Column(db.String(32))
    last_name = db.Column(db.String(32))
    email = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    number_of_adults = db.Column(db.Integer)
    number_of_children = db.Column(db.Integer)
    payment_status_id = db.Column(db.Integer, db.ForeignKey('payment_status.id'), default=1)
    status_id = db.Column(db.Integer, db.ForeignKey('booking_status.id'), default=1)
    note = db.Column(db.Text())
    special_request = db.Column(db.Text())
    booking_date = db.Column(db.Date(), default=func.current_date())
    check_in = db.Column(db.Date())
    check_out = db.Column(db.Date())
    check_in_day = db.Column(db.Integer)
    check_in_month = db.Column(db.Integer)
    check_in_year = db.Column(db.Integer)
    check_out_day = db.Column(db.Integer)
    check_out_month = db.Column(db.Integer)
    check_out_year = db.Column(db.Integer)
    number_of_days = db.Column(db.Integer)
    rate = db.Column(db.Float)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    creator_id = db.Column(db.String(32))

    booking_rates = db.relationship(
        'BookingRate',
        cascade='all, delete-orphan',
        back_populates='booking'
    )

    def __init__(self, **kwargs):
        super(Booking, self).__init__(**kwargs)
        self.confirmation_number = self.generate_confirmation_number()

    @staticmethod
    def generate_confirmation_number():
        while True:
            number = random.randint(100000, 999999)
            if not Booking.query.filter_by(confirmation_number=number).first():
                return number

    def to_json(self):
        return {
            'id': self.id,
            'confirmation_number': self.confirmation_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'number_of_adults': self.number_of_adults,
            'number_of_children': self.number_of_children,
            'payment_status_id': self.payment_status_id,
            'status_id': self.status_id,
            'note': self.note,
            'special_request': self.special_request,
            'booking_date': self.booking_date.isoformat() if self.booking_date else None,
            'check_in': self.check_in.isoformat() if self.check_in else None,
            'check_out': self.check_out.isoformat() if self.check_out else None,
            'check_in_day': self.check_in_day,
            'check_in_month': self.check_in_month,
            'check_in_year': self.check_in_year,
            'check_out_day': self.check_out_day,
            'check_out_month': self.check_out_month,
            'check_out_year': self.check_out_year,
            'number_of_days': self.number_of_days,
            'rate': self.rate,
            'property_id': self.property_id,
            'room_id': self.room_id,
            'creator_id': self.creator_id,
            'booking_rates': [br.to_json() for br in self.booking_rates]
        }

    @staticmethod
    def from_json(json_booking):
        from werkzeug.http import parse_date

        def parse_dates(key):
            val = json_booking.get(key)
            if not val:
                raise ValueError(f"Missing date for field {key}")
            try:
                return datetime.strptime(val, "%Y-%m-%d").date()
            except ValueError:
                parsed = parse_date(val)
                if not parsed:
                    raise ValueError(f"Invalid date format for field {key}: {val}")
                return parsed.date()

        return Booking(
            first_name=json_booking.get('first_name'),
            last_name=json_booking.get('last_name'),
            email=json_booking.get('email'),
            phone=json_booking.get('phone'),
            number_of_adults=json_booking.get('number_of_adults'),
            number_of_children=json_booking.get('number_of_children'),
            payment_status_id=json_booking.get('payment_status_id'),
            status_id=json_booking.get('status_id'),
            note=json_booking.get('note'),
            special_request=json_booking.get('special_request'),
            check_in=parse_dates('check_in'),
            check_out=parse_dates('check_out'),
            check_in_day=json_booking.get('check_in_day'),
            check_in_month=json_booking.get('check_in_month'),
            check_in_year=json_booking.get('check_in_year'),
            check_out_day=json_booking.get('check_out_day'),
            check_out_month=json_booking.get('check_out_month'),
            check_out_year=json_booking.get('check_out_year'),
            number_of_days=json_booking.get('number_of_days'),
            rate=json_booking.get('rate'),
            property_id=json_booking.get('property_id'),
            room_id=json_booking.get('room_id'),
            creator_id=json_booking.get('creator_id'),
        )

    def change_status(self, status_input):
        if isinstance(status_input, str):
            status_id = Constants.BookingStatusCoding.get(status_input)
            if not status_id:
                raise ValueError(f"Unknown status name: {status_input}")
            self.status_id = status_id
        elif isinstance(status_input, int):
            if status_input not in Constants.BookingStatusCoding:
                raise ValueError(f"Unknown status ID: {status_input}")
            self.status_id = status_input
        else:
            raise TypeError("status_input must be str or int")



class BookingRate(db.Model):
    __tablename__ = 'booking_rates'

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    rate_date = db.Column(db.Date, nullable=False)
    nightly_rate = db.Column(db.Float, nullable=False)

    booking = db.relationship('Booking', back_populates='booking_rates')

    def __init__(self, **kwargs):
        super(BookingRate, self).__init__(**kwargs)

    def to_json(self):
        return {
            'id': self.id,
            'booking_id': self.booking_id,
            'rate_date': self.rate_date.isoformat() if self.rate_date else None,
            'nightly_rate': self.nightly_rate
        }

    @staticmethod
    def from_json(json_data):
        from werkzeug.http import parse_date
        rate_date_str = json_data.get('rate_date')
        rate_date = parse_date(rate_date_str).date() if rate_date_str else None
        return BookingRate(
            booking_id=json_data.get('booking_id'),
            rate_date=rate_date,
            nightly_rate=json_data.get('nightly_rate')
        )

class BookingStatus(db.Model):
    __tablename__ = 'booking_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True)
    name = db.Column(db.String(32), unique=True)
    color = db.Column(db.String(32), unique=True)

    @staticmethod
    def insert_status():
        status = {
            'Confirmed': ['CONFIRMED', 'Blue'],
            'Checked In': ['CHECKED IN', 'Green'],
            'Checked Out': ['CHECKED OUT', 'Brown'],
            'Completed': ['COMPLETED', 'Orange'],
            'Cancelled': ['CANCELLED', 'Red'],
            'No Show': ['NO SHOW', 'Purple']
        }
        for s in status:
            stat = BookingStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = BookingStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()


class RatePlan(db.Model):
    __tablename__ = 'rate_plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    base_rate = db.Column(db.Float, nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    weekend_rate = db.Column(db.Float, nullable=True)
    seasonal_multiplier = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    def __init__(self, **kwargs):
        super(RatePlan, self).__init__(**kwargs)

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'base_rate': self.base_rate,
            'property_id': self.property_id,
            'category_id': self.category_id,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'weekend_rate': self.weekend_rate,
            'seasonal_multiplier': self.seasonal_multiplier,
            'is_active': self.is_active,
        }

    @staticmethod
    def from_json(json_data):
        name = json_data.get('name')
        base_rate = json_data.get('base_rate')
        property_id = json_data.get('property_id')
        category_id = json_data.get('category_id')
        start_date = datetime.fromisoformat(json_data.get('start_date')).date()
        end_date = datetime.fromisoformat(json_data.get('end_date')).date()
        weekend_rate = json_data.get('weekend_rate')
        seasonal_multiplier = json_data.get('seasonal_multiplier')
        is_active = json_data.get('is_active', True)

        return RatePlan(
            name=name,
            base_rate=base_rate,
            category_id=category_id,
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            weekend_rate=weekend_rate,
            seasonal_multiplier=seasonal_multiplier,
            is_active=is_active
        )

class Season(db.Model):
    __tablename__ = 'seasons'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    label = db.Column(db.String(64), nullable=True)

    def __init__(self, **kwargs):
        super(Season, self).__init__(**kwargs)

    def to_json(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'label': self.label
        }

    @staticmethod
    def from_json(json_data):
        property_id = json_data.get('property_id')
        start_date = datetime.fromisoformat(json_data.get('start_date')).date()
        end_date = datetime.fromisoformat(json_data.get('end_date')).date()
        label = json_data.get('label')

        return Season(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            label=label
        )

class RoomOnline(db.Model):
    __tablename__ = 'room_online'
    __table_args__ = (
        db.UniqueConstraint('room_id', 'date', name='unique_room_online_per_day'),
    )

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    price = db.Column(db.Float, nullable=False)
    room_status_id = db.Column(db.Integer, db.ForeignKey('room_status.id'), nullable=False, default=1)

    def __init__(self, **kwargs):
        super(RoomOnline, self).__init__(**kwargs)

    def to_json(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'property_id': self.property_id,
            'category_id': self.category_id,  # ✅ Include in output
            'date': self.date.isoformat(),
            'price': self.price,
            'room_status_id': self.room_status_id
        }

    @staticmethod
    def from_json(json_data):
        return RoomOnline(
            room_id=json_data.get('room_id'),
            property_id=json_data.get('property_id'),
            category_id=json_data.get('category_id'),  # ✅ Parse input
            date=datetime.fromisoformat(json_data.get('date')).date(),
            price=json_data.get('price')
        )

class Block(db.Model):
    __tablename__ = 'blocks'
    id = db.Column(db.Integer, primary_key=True)
    note = db.Column(db.Text())
    block_date = db.Column(db.Date(), default=datetime.today().date())

    start_date = db.Column(db.Date(), nullable=False)
    end_date = db.Column(db.Date(), nullable=False)
    start_day = db.Column(db.Integer)
    start_month = db.Column(db.Integer)
    start_year = db.Column(db.Integer)
    end_day = db.Column(db.Integer)
    end_month = db.Column(db.Integer)
    end_year = db.Column(db.Integer)
    number_of_days = db.Column(db.Integer)

    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)

    @validates('start_date', 'end_date')
    def validate_dates(self, key, value):
        if key == 'end_date' and self.start_date and value <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return value

    def calculate_fields(self):
        """Call this after setting start_date and end_date"""
        if self.start_date and self.end_date:
            self.number_of_days = (self.end_date - self.start_date).days
            self.start_day = self.start_date.day
            self.start_month = self.start_date.month
            self.start_year = self.start_date.year
            self.end_day = self.end_date.day
            self.end_month = self.end_date.month
            self.end_year = self.end_date.year

    def overlaps_existing_block_or_booking(self):
        """Check for overlap with other blocks or bookings for the same room"""
        overlapping_blocks = Block.query.filter(
            Block.room_id == self.room_id,
            Block.id != self.id,
            Block.start_date < self.end_date,
            Block.end_date > self.start_date
        ).first()

        overlapping_bookings = Booking.query.filter(
            Booking.room_id == self.room_id,
            Booking.check_in < self.end_date,
            Booking.check_out > self.start_date
        ).first()

        return overlapping_blocks or overlapping_bookings

    def to_json(self):
        return {
            'id': self.id,
            'note': self.note,
            'block_date': self.block_date,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'start_day': self.start_day,
            'start_month': self.start_month,
            'start_year': self.start_year,
            'end_day': self.end_day,
            'end_month': self.end_month,
            'end_year': self.end_year,
            'number_of_days': self.number_of_days,
            'property_id': self.property_id,
            'room_id': self.room_id,
        }

    @staticmethod
    def from_json(json_block):
        start_date = parse_date(json_block.get('start_date'))
        end_date = parse_date(json_block.get('end_date'))
        block_date = parse_date(json_block.get('block_date'))

        block = Block(
            note=json_block.get('note'),
            block_date=block_date,
            start_date=start_date,
            end_date=end_date,
            property_id=json_block.get('property_id'),
            room_id=json_block.get('room_id'),
        )
        block.calculate_fields()
        if block.overlaps_existing_block_or_booking():
            raise ValueError("Block overlaps with an existing block or booking.")
        return block


import secrets
from datetime import datetime, timedelta


class PropertyInvite(db.Model):
    __tablename__ = 'property_invites'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    invite_code = db.Column(db.String(32), unique=True, nullable=False, default=lambda: secrets.token_hex(8))
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    property = db.relationship('Property')
    role = db.relationship('Role')


class GuestMessage(db.Model):
    __tablename__ = 'guest_messages'

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)

    # 'outbound' (Hotel -> Guest) or 'inbound' (Guest -> Hotel)
    direction = db.Column(db.String(16), nullable=False)

    # 'WhatsApp' or 'sms'
    channel = db.Column(db.String(16), nullable=False, default='whatsapp')

    message_body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)  # To show unread badges to staff

    # Establish relationship to Booking
    booking = db.relationship('Booking',
                              backref=db.backref('chat_history', lazy='dynamic', cascade='all, delete-orphan'))

    def to_json(self):
        return {
            'id': self.id,
            'booking_id': self.booking_id,
            'property_id': self.property_id,
            'direction': self.direction,
            'channel': self.channel,
            'message_body': self.message_body,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'is_read': self.is_read
        }

class Amenity(db.Model):
    __tablename__ = 'amenities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    icon = db.Column(db.String(64), nullable=True) # Useful for Flutter frontend icons

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon
        }

    @staticmethod
    def insert_default_amenities():
        defaults = ['Free WiFi', 'Swimming Pool', 'Gym', 'Parking', 'Room Service', 'Spa']
        for name in defaults:
            if not Amenity.query.filter_by(name=name).first():
                db.session.add(Amenity(name=name))
        db.session.commit()