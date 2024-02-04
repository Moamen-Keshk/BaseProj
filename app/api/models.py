from datetime import datetime, timedelta
import hashlib
from itsdangerous import (URLSafeTimedSerializer
                          as Serializer, BadSignature, SignatureExpired)
from werkzeug.security import generate_password_hash, check_password_hash
from markdown import markdown
import bleach
from flask import current_app, url_for
from flask_login import UserMixin, AnonymousUserMixin

from .exceptions import ValidationError
from .. import db, login_manager
import random
from .constants import Constants


class Permission:
    FOLLOW = 1
    COMMENT = 2
    WRITE = 4
    MODERATE = 8
    ADMIN = 16


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    users = db.relationship('User', backref='role', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    @staticmethod
    def insert_roles():
        roles = {
            'User': [Permission.FOLLOW, Permission.COMMENT, Permission.WRITE],
            'Moderator': [Permission.FOLLOW, Permission.COMMENT,
                          Permission.WRITE, Permission.MODERATE],
            'Administrator': [Permission.FOLLOW, Permission.COMMENT,
                              Permission.WRITE, Permission.MODERATE,
                              Permission.ADMIN],
        }
        default_role = 'User'
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            db.session.add(role)
        db.session.commit()

    def add_permission(self, perm):
        if not self.has_permission(perm):
            self.permissions += perm

    def remove_permission(self, perm):
        if self.has_permission(perm):
            self.permissions -= perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    def __repr__(self):
        return '<Role %r>' % self.name


class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    password_hash = db.Column(db.String(128))
    confirmed = db.Column(db.Boolean, default=False)
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)
    last_seen = db.Column(db.DateTime(), default=datetime.utcnow)
    avatar_hash = db.Column(db.String(32))
    vendor_id = db.Column(db.Integer, db.ForeignKey('agents.id'))
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    orders = db.relationship('Order', backref='creator', lazy='dynamic')
    followed = db.relationship('Follow',
                               foreign_keys=[Follow.follower_id],
                               backref=db.backref('follower', lazy='joined'),
                               lazy='dynamic',
                               cascade='all, delete-orphan')
    followers = db.relationship('Follow',
                                foreign_keys=[Follow.followed_id],
                                backref=db.backref('followed', lazy='joined'),
                                lazy='dynamic',
                                cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic')

    @staticmethod
    def add_self_follows():
        for user in User.query.all():
            if not user.is_following(user):
                user.follow(user)
                db.session.add(user)
                db.session.commit()

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email == current_app.config['FLASKY_ADMIN']:
                self.role = Role.query.filter_by(name='Administrator').first()
            if self.role is None:
                self.role = Role.query.filter_by(default=True).first()
        if self.email is not None and self.avatar_hash is None:
            self.avatar_hash = self.gravatar_hash()
        self.follow(self)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_confirmation_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'confirm': self.id}).decode('utf-8')

    @staticmethod
    def verify_confirmation_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None  # valid token, but expired
        except BadSignature:
            return None  # invalid token
        user = User.query.get(data['confirm'])
        return user

    @staticmethod
    def verify_change_email_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None  # valid token, but expired
        except BadSignature:
            return None  # invalid token
        user = User.query.get(data['change_email'])
        return user

    def confirm(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        if data.get('confirm') != self.id:
            return False
        self.confirmed = True
        db.session.add(self)
        return True

    def generate_reset_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'reset': self.id}).decode('utf-8')

    @staticmethod
    def reset_password(token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        user = User.query.get(data.get('reset'))
        if user is None:
            return False
        user.password = new_password
        db.session.add(user)
        return True

    def generate_email_change_token(self, new_email, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps(
            {'change_email': self.id, 'new_email': new_email}).decode('utf-8')

    def change_email(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        if data.get('change_email') != self.id:
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

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    def is_administrator(self):
        return self.can(Permission.ADMIN)

    def ping(self):
        self.last_seen = datetime.utcnow()
        db.session.add(self)

    def gravatar_hash(self):
        return hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()

    def gravatar(self, size=100, default='identicon', rating='g'):
        url = 'https://secure.gravatar.com/avatar'
        hash = self.avatar_hash or self.gravatar_hash()
        return '{url}/{hash}?s={size}&d={default}&r={rating}'.format(
            url=url, hash=hash, size=size, default=default, rating=rating)

    def follow(self, user):
        if not self.is_following(user):
            f = Follow(follower=self, followed=user)
            db.session.add(f)

    def unfollow(self, user):
        f = self.followed.filter_by(followed_id=user.id).first()
        if f:
            db.session.delete(f)

    def is_following(self, user):
        if user.id is None:
            return False
        return self.followed.filter_by(
            followed_id=user.id).first() is not None

    def is_followed_by(self, user):
        if user.id is None:
            return False
        return self.followers.filter_by(
            follower_id=user.id).first() is not None

    @property
    def followed_posts(self):
        return Post.query.join(Follow, Follow.followed_id == Post.author_id)\
            .filter(Follow.follower_id == self.id)

    def to_json(self):
        json_user = {
            'username': self.username,
            'email': self.email,
            'member_since': self.member_since,
            'posts_url': url_for('api.get_user_posts', id=self.id),
            'post_count': self.posts.count(),
            'profile_avatar': self.gravatar(256),
            'name': self.name,
            'location': self.location,
            'about_me': self.about_me
        }
        return json_user

    def generate_auth_token(self, expiration):
        s = Serializer(current_app.config['SECRET_KEY'],
                       expires_in=expiration)
        return s.dumps({'id': self.id}).decode('utf-8')

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None  # valid token, but expired
        except BadSignature:
            return None  # invalid token
        user = User.query.get(data['id'])
        return user

    def __repr__(self):
        return '<User %r>' % self.username

    # @staticmethod
    # def encode_auth_token(user_id):
    #     """
    #     Generates the Auth Token
    #     :return: string
    #     """
    #     try:
    #         payload = {
    #             'exp': datetime.utcnow() + timedelta(days=0, seconds=3600),
    #             'iat': datetime.utcnow(),
    #             'sub': user_id
    #         }
    #         return jwt.encode(
    #             payload,
    #             current_app.config['SECRET_KEY'],
    #             algorithm='HS256'
    #         )
    #     except Exception as e:
    #         return e
    #
    # @staticmethod
    # def decode_auth_token(auth_token):
    #     """
    #     Validates the auth token
    #     :param auth_token:
    #     :return: integer|string
    #     """
    #     try:
    #         payload = jwt.decode(auth_token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    #         is_blacklisted_token = BlacklistToken.check_blacklist(auth_token)
    #         if is_blacklisted_token:
    #             return 'Token blacklisted. Please log in again.'
    #         else:
    #             return payload['sub']
    #     except jwt.ExpiredSignatureError:
    #         return 'Signature expired. Please log in again.'
    #     except jwt.InvalidTokenError:
    #         return 'Invalid token. Please log in again.'


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    def is_administrator(self):
        return False


login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# @login_manager.request_loader
# def load_user_from_request(request):
#     token = request.headers.get('Authorization')
#     if token:
#         token = token.replace('Bearer ', '', 1)
#         return User.verify_auth_token(token)
#
#     # finally, return None if both methods did not login the user
#     return None


class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text)
    body_html = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comments = db.relationship('Comment', backref='post', lazy='dynamic')

    @staticmethod
    def on_changed_body(target, value, oldvalue, initiator):
        allowed_tags = ['a', 'abbr', 'acronym', 'b', 'blockquote', 'code',
                        'em', 'i', 'li', 'ol', 'pre', 'strong', 'ul',
                        'h1', 'h2', 'h3', 'p']
        target.body_html = bleach.linkify(bleach.clean(
            markdown(value, output_format='html'),
            tags=allowed_tags, strip=True))

    def to_json(self):
        json_post = {
            'url': url_for('api.get_post', id=self.id),
            'body': self.body,
            'body_html': self.body_html,
            'timestamp': self.timestamp,
            'author_url': url_for('api.get_user', id=self.author_id),
            'comments_url': url_for('api.get_post_comments', id=self.id),
            'comment_count': self.comments.count()
        }
        return json_post

    @staticmethod
    def from_json(json_post):
        body = json_post.get('body')
        if body is None or body == '':
            raise ValidationError('post does not have a body')
        return Post(body=body)


db.event.listen(Post.body, 'set', Post.on_changed_body)


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text)
    body_html = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    disabled = db.Column(db.Boolean)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'))

    @staticmethod
    def on_changed_body(target, value, oldvalue, initiator):
        allowed_tags = ['a', 'abbr', 'acronym', 'b', 'code', 'em', 'i',
                        'strong']
        target.body_html = bleach.linkify(bleach.clean(
            markdown(value, output_format='html'),
            tags=allowed_tags, strip=True))

    def to_json(self):
        json_comment = {
            'url': url_for('api.get_comment', id=self.id),
            'post_url': url_for('api.get_post', id=self.post_id),
            'body': self.body,
            'body_html': self.body_html,
            'timestamp': self.timestamp,
            'author_url': url_for('api.get_user', id=self.author_id),
        }
        return json_comment

    @staticmethod
    def from_json(json_comment):
        body = json_comment.get('body')
        if body is None or body == '':
            raise ValidationError('comment does not have a body')
        return Comment(body=body)


db.event.listen(Comment.body, 'set', Comment.on_changed_body)


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.Text)
    type = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    has_action = db.Column(db.Boolean, default=False)
    from_user = db.Column(db.Integer, db.ForeignKey('agents.id'))
    to_user = db.Column(db.Integer, db.ForeignKey('users.id'))

    def to_json(self):
        json_notification = {
            'id': self.id,
            'subject': self.subject,
            'type': self.type,
            'is_read': self.is_read,
            'has_action': self.has_action,
            'from_user': self.from_user
        }
        return json_notification


class Agent(db.Model):
    __tablename__ = 'agents'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    code = db.Column(db.Integer, unique=True, index=True)
    name = db.Column(db.String(64))
    status = db.Column(db.String(64), default='Draft')
    location = db.Column(db.String(64))
    phone = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)
    users = db.relationship('User', backref='vendor', lazy='dynamic')
    invoices = db.relationship('Invoice', backref='agent', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Agent, self).__init__(**kwargs)
        self.code = random.randint(000000, 999999)

    def to_json(self):
        json_agent = {
            'id': self.id,
            'email': self.email,
            'code': self.code,
            'name': self.name,
            'location': self.location,
            'phone': self.phone,
            'about_me': self.about_me,
            'member_since': self.member_since,
            'status': self.status
        }
        return json_agent


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.Integer, unique=True)
    fullname = db.Column(db.String(64))
    payment = db.Column(db.String(64), default='Unpaid')
    doc_version = db.Column(db.String(64), default='Copy')
    status_id = db.Column(db.Integer, db.ForeignKey('order_status.id'), default=1)
    doc_type_id = db.Column(db.Integer, db.ForeignKey('document_type.id'), default=1)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_type.id'), default=1)
    embassy_id = db.Column(db.Integer, db.ForeignKey('embassy.id'), default=None)
    service_option_id = db.Column(db.Integer, db.ForeignKey('service_option.id'), default=1)
    collection_type_id = db.Column(db.Integer, db.ForeignKey('collection_type.id'), default=1)
    note = db.Column(db.Text())
    working_days = db.Column(db.Integer)
    due_date = db.Column(db.Date())
    completion_date = db.Column(db.Date())
    sending_date = db.Column(db.Date())
    fee = db.Column(db.Integer)
    order_date = db.Column(db.Date(), default=datetime.today().date())
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    UAE_Payment_id = db.Column(db.Integer, db.ForeignKey('uae_payments.id'))
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))

    def __init__(self, **kwargs):
        super(Order, self).__init__(**kwargs)
        self.barcode = random.randint(000000, 999999)
        if self.embassy_id:
            self.add_tariffs(self.embassy_id, self.service_option_id, self.service_type_id == 4)
        else:
            self.add_tariffs(self.service_type_id, self.service_option_id, False)
        self.due_date = self.date_by_adding_business_days(datetime.today().date(), self.working_days)

    def add_tariffs(self, embassy_id, service_opt_id, emb_only):
        tariff = TariffAssist.query.filter_by(
            embassy_id=embassy_id, service_opt_id=service_opt_id).first()
        if emb_only:
            diff = TariffAssist.query.filter_by(embassy_id=2, service_opt_id=service_opt_id).first()
            self.working_days = tariff.working_days - diff.working_days
            self.fee = tariff.fee - diff.fee
        else:
            self.working_days = tariff.working_days
            self.fee = tariff.fee

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
            'status_id': self.status_id,
            'doc_version': self.doc_version,
            'doc_type': Constants.DocTypeCoding[self.doc_type_id],
            'service_type': Constants.ServiceTypeCoding[self.service_type_id],
            'embassy': Constants.EmbassyCoding[self.embassy_id],
            'service_option': Constants.ServiceOptionCoding[self.service_option_id],
            'collection_type': Constants.CollectionTypeCoding[self.collection_type_id],
            'working_days': self.working_days,
            'due_date': self.due_date.strftime("%d-%m-%y"),
            'completion_date': self.completion_date.strftime("%d-%m-%y") if self.completion_date is not None else '…',
            'sending_date': self.sending_date.strftime("%d-%m-%y") if self.sending_date is not None else '…',
            'fee': self.fee,
            'order_date': self.order_date.strftime("%d-%m-%y"),
            'creator': User.query.filter_by(id=self.creator_id).with_entities(User.username).first()[0],
            'UAE_Payment': UAEPayment.query.filter_by(id=self.UAE_Payment_id).with_entities(
                UAEPayment.ATS).first()[0] if self.UAE_Payment_id is not None else '…',
            'has_note': 'y' if self.note is not None else 'n'
        }
        return json_order

    def to_full_json(self):
        json_order = {
            'id': self.id,
            'fullname': self.fullname,
            'status': Constants.OrderStatusCoding[self.status_id],
            'doc_version': self.doc_version,
            'doc_type': Constants.DocTypeCoding[self.doc_type_id],
            'service_type': Constants.ServiceTypeCoding[self.service_type_id],
            'embassy': Constants.EmbassyCoding[self.embassy_id],
            'service_option': Constants.ServiceOptionCoding[self.service_option_id],
            'collection_type': Constants.CollectionTypeCoding[self.collection_type_id],
            'working_days': self.working_days,
            'due_date': self.due_date.strftime("%d-%m-%y"),
            'completion_date': self.completion_date.strftime("%d-%m-%y") if self.completion_date is not None else '…',
            'sending_date': self.sending_date.strftime("%d-%m-%y") if self.sending_date is not None else '…',
            'fee': self.fee,
            'order_date': self.order_date.strftime("%d-%m-%y"),
            'creator': User.query.filter_by(id=self.creator_id).with_entities(User.username).first()[0],
            'UAE_Payment': UAEPayment.query.filter_by(id=self.UAE_Payment_id).with_entities(
                UAEPayment.ATS).first()[0] if self.UAE_Payment_id is not None else '…',
            'barcode': self.barcode,
            'payment': self.payment,
            'note': self.note,
            'documents': [filename[0] for filename in Document.query.filter_by(order_id=self.id).order_by(
                Document.id).with_entities(Document.filename).all()]
        }
        return json_order

    @staticmethod
    def from_json(json_order):
        fullname = json_order.get('fullname')
        doc_type_id = Constants.DocTypeCoding[json_order.get('doc_type')]
        service_type_id = Constants.ServiceTypeCoding[json_order.get('service_type')]
        embassy_id = Constants.EmbassyCoding[json_order.get('embassy')]
        service_option_id = Constants.ServiceOptionCoding[json_order.get('service_option')]
        doc_version = json_order.get('doc_version')
        collection_type_id = Constants.CollectionTypeCoding[json_order.get('collection_type')]
        return Order(fullname=fullname, doc_type_id=doc_type_id, service_type_id=service_type_id,
                     embassy_id=embassy_id, service_option_id=service_option_id,
                     doc_version=doc_version, collection_type_id=collection_type_id)

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


class UAEPayment(db.Model):
    __tablename__ = 'uae_payments'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(64))
    ATS = db.Column(db.String(64))
    uae_date = db.Column(db.DateTime(), default=datetime.utcnow)
    orders = db.relationship('Order', backref='UAE_Payment', lazy='dynamic')


class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(64), unique=True)
    invoice_date = db.Column(db.DateTime(), default=datetime.utcnow)
    inv_status_id = db.Column(db.Integer, db.ForeignKey('invoice_status.id'), default=1)
    orders = db.relationship('Order', backref='invoice', lazy='dynamic')
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'))
    amount = db.Column(db.Integer)

    def __init__(self, **kwargs):
        super(Invoice, self).__init__(**kwargs)
        self.invoice_number = 'INV'+random.randint(00000, 99999)


class InvoiceStatus(db.Model):
    __tablename__ = 'invoice_status'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_invoice_status():
        status = {
            'Unpaid': ['UNPAID', 'yellow'],
            'Paid': ['PAID', 'green'],
            'Postponed': ['POSTPONED', 'blue']
        }
        for s in status:
            stat = InvoiceStatus.query.filter_by(name=s).first()
            if stat is None:
                stat = InvoiceStatus(name=s, code=status[s][0], color=status[s][1])
            db.session.add(stat)
        db.session.commit()


class DocumentType(db.Model):
    __tablename__ = 'document_type'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_document_types():
        types = {
            'Educational': ['EDU', 'green'],
            'Transcript': ['TRANS', 'yellow'],
            'Commercial': ['COMM', 'blue']
        }
        for t in types:
            typ = DocumentType.query.filter_by(name=t).first()
            if typ is None:
                typ = DocumentType(name=t, code=types[t][0], color=types[t][1])
            db.session.add(typ)
        db.session.commit()


class ServiceType(db.Model):
    __tablename__ = 'service_type'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_service_types():
        types = {
            'Full': ['FULL', 'green'],
            'Sol+FCDO': ['SOL + FCDO', 'blue'],
            'FCDO Only': ['FCDO ONLY', 'yellow'],
            'Emb Only': ['EMB ONLY', 'gray']
        }
        for t in types:
            typ = ServiceType.query.filter_by(name=t).first()
            if typ is None:
                typ = ServiceType(name=t, code=types[t][0], color=types[t][1])
            db.session.add(typ)
        db.session.commit()


class Embassy(db.Model):
    __tablename__ = 'embassy'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_embassies():
        embs = {
            'Emirates': ['UAE'],
            'Saudi Arabia': ['KSA'],
            'Qatar': ['QAT'],
            'Egypt': ['EGY'],
            'Kuwait': ['KWT'],
            'Lebanon': ['LBN'],
            'FCDO Only': ['FCDO ONLY'],
            'Sol+FCDO': ['SOL + FCDO']
        }
        for e in embs:
            emb = Embassy.query.filter_by(name=e).first()
            if emb is None:
                emb = Embassy(name=e, code=embs[e][0])
            db.session.add(emb)
        db.session.commit()


class ServiceOption(db.Model):
    __tablename__ = 'service_option'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_service_options():
        options = {
            'Standard': ['STD', 'green'],
            'Express': ['EXP', 'blue'],
            'Urgent': ['URG', 'red']
        }
        for o in options:
            opt = ServiceOption.query.filter_by(name=o).first()
            if opt is None:
                opt = ServiceOption(name=o, code=options[o][0], color=options[o][1])
            db.session.add(opt)
        db.session.commit()


class Tariff(db.Model):
    __tablename__ = 'tariff'
    id = db.Column(db.Integer, primary_key=True)
    embassy_id = db.Column(db.Integer, db.ForeignKey('embassy.id'))
    embassy_code = db.Column(db.String(64))
    std_w = db.Column(db.Integer)
    exp_w = db.Column(db.Integer)
    urg_w = db.Column(db.Integer)
    std_f = db.Column(db.Integer)
    exp_f = db.Column(db.Integer)
    urg_f = db.Column(db.Integer)

    @staticmethod
    def insert_tariffs():
        embassies = [id_code for id_code in Embassy.query.with_entities(Embassy.id, Embassy.code).all()]
        service_types = [id_code for id_code in ServiceType.query.with_entities(
            ServiceType.id, ServiceType.code).all()]
        for e in embassies:
            tar = Tariff.query.filter_by(embassy_id=e[0]).first()
            if tar is None:
                tar = Tariff(embassy_id=e[0], embassy_code=e[1])
            db.session.add(tar)
        for t in service_types:
            if t[0] in (1, 4):
                continue
            tar = Tariff.query.filter_by(embassy_code=t[1]).first()
            if tar is None:
                tar = Tariff(embassy_code=t[1])
            db.session.add(tar)
        db.session.commit()

    def to_json(self):
        json_tariff = {
            'id': self.id,
            'embassy': self.embassy_code,
            'standard_w': self.std_w,
            'express_w': self.exp_w,
            'urgent_w': self.urg_w,
            'standard_f': self.std_f,
            'express_f': self.exp_f,
            'urgent_f': self.urg_f
        }
        return json_tariff


class TariffAssist(db.Model):
    __tablename__ = 'tariff_assist'
    id = db.Column(db.Integer, primary_key=True)
    embassy_id = db.Column(db.Integer, db.ForeignKey('embassy.id'))
    service_opt_id = db.Column(db.Integer, db.ForeignKey('service_option.id'))
    embassy_code = db.Column(db.String(64))
    service_code = db.Column(db.String(64))
    working_days = db.Column(db.Integer)
    fee = db.Column(db.Integer)

    @staticmethod
    def insert_tariffs():
        embassies = [id_code for id_code in Embassy.query.order_by(
            Embassy.id).with_entities(Embassy.id, Embassy.code).all()]
        service_options = [id_code for id_code in ServiceOption.query.order_by(ServiceOption.id).with_entities(
            ServiceOption.id, ServiceOption.code).all()]
        tariff_hash = {r.embassy_id: [
            r.std_w, r.exp_w, r.urg_w, r.std_f, r.exp_f, r.urg_f] for r in Tariff.query.all()}
        for e in embassies:
            for o in service_options:
                tar = TariffAssist.query.filter_by(embassy_id=e[0], service_opt_id=o[0]).first()
                if tar is None:
                    tar = TariffAssist(embassy_id=e[0], service_opt_id=o[0],
                                       embassy_code=e[1], service_code=o[1], working_days=tariff_hash[e[0]][o[0]-1],
                                       fee=tariff_hash[e[0]][(o[0]-1)+3])
                else:
                    tar.working_days = tariff_hash[e[0]][o[0]-1]
                    tar.fee = tariff_hash[e[0]][(o[0]-1)+3]
                db.session.add(tar)
        db.session.commit()

    @staticmethod
    def update_embassy(embassy_id, values):
        service_options = [ids[0] for ids in ServiceOption.query.order_by(ServiceOption.id).with_entities(
            ServiceOption.id).all()]
        for o in service_options:
            tar_assist = TariffAssist.query.filter_by(embassy_id=embassy_id, service_opt_id=o).first()
            tar_assist.working_days = values[(o-1)]
            tar_assist.fee = values[(o - 1) + 3]
            db.session.add(tar_assist)
        db.session.commit()


class CollectionType(db.Model):
    __tablename__ = 'collection_type'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    color = db.Column(db.String(64), unique=True)

    @staticmethod
    def insert_collection_types():
        coll_types = {
            'Customer Courier': ['COURIER', 'yellow'],
            'Royal Mail': ['RM', 'blue'],
            'In Person': ['INP', 'green']
        }
        for o in coll_types:
            c_type = CollectionType.query.filter_by(name=o).first()
            if c_type is None:
                c_type = CollectionType(name=o, code=coll_types[o][0], color=coll_types[o][1])
            db.session.add(c_type)
        db.session.commit()


class AWB(db.Model):
    __tablename__ = 'awb'
    id = db.Column(db.Integer, primary_key=True)
    rec_awb = db.Column(db.String(64), unique=True)
    sen_awb = db.Column(db.String(64), unique=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))


class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(64), unique=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
