import os
import logging
from flask import make_response, jsonify, redirect, request, g
from werkzeug.security import check_password_hash
from flask.views import MethodView
from app.api.email import send_email
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
from app.api.errors import unauthorized
from itsdangerous import (URLSafeTimedSerializer as Serializer)
from app.api import api
from . import auth

from .. import db
from app.api.models import User

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth('Bearer')
multi_auth = MultiAuth(basic_auth, token_auth)

jws = Serializer(os.environ.get('SECRET_KEY'))


@basic_auth.verify_password
def verify_password(email_or_token, password):
    # first try to authenticate by token
    user = User.verify_auth_token(email_or_token)
    if not user:
        # try to authenticate with username/password
        user = User.query.filter_by(email=email_or_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True


@token_auth.verify_token
def verify_token(token):
    try:
        data = jws.loads(token)
    except Exception as e:
        logging.exception(e)
        return False
    if 'id' in data:
        return data['id']


@token_auth.error_handler
def auth_error():
    return unauthorized('Invalid credentials')


@api.route('/token')
@basic_auth.login_required
def get_auth_token():
    token = g.user.generate_auth_token(3600)
    return jsonify({'token': token})


class RegisterAPI(MethodView):
    """
    User Registration Resource
    """

    @staticmethod
    def post():
        # get the post data
        post_data = request.get_json()
        # check if user already exists
        user = User.query.filter_by(email=post_data.get('email')).first()
        if not user:
            if User.query.filter_by(username=post_data.get('username')).first():
                responseObject = {
                    'status': 'username',
                    'message': 'Username already in use.',
                }
                return make_response(jsonify(responseObject)), 202
            try:
                user = User(
                    username=post_data.get('username'),
                    email=post_data.get('email'),
                    password=post_data.get('password'),
                )

                # insert the user
                db.session.add(user)
                db.session.commit()
                token = user.generate_confirmation_token()
                send_email(user.email, 'Confirm Your Account',
                           'auth/email/confirm', user=user, token=token)
                # generate the auth token
                auth_token = user.generate_auth_token()
                responseObject = {
                    'status': 'success',
                    'message': 'Successfully registered.',
                    'auth_token': auth_token
                }
                return make_response(jsonify(responseObject)), 201
            except Exception as e:
                logging.exception(e)
                responseObject = {
                    'status': 'error',
                    'message': 'Some error occurred. Please try again.'
                }
                return make_response(jsonify(responseObject)), 401
        else:
            responseObject = {
                'status': 'exist',
                'message': 'User already exists. Please Log in.',
            }
            return make_response(jsonify(responseObject)), 202


class LoginAPI(MethodView):
    """
    User Login Resource
    """

    @staticmethod
    def post():
        # get the post data
        post_data = request.get_json()
        try:
            # fetch the user data
            user = User.query.filter_by(
                email=post_data.get('email')
            ).first()
            if user and check_password_hash(
                    user.password_hash, post_data.get('password')
            ):
                auth_token = user.generate_auth_token(3600*10)
                if auth_token:
                    responseObject = {
                        'status': 'success',
                        'message': 'Successfully logged in.',
                        'auth_token': auth_token,
                        'avatar_hash': user.gravatar(size=18)
                    }
                    return make_response(jsonify(responseObject)), 200
            else:
                responseObject = {
                    'status': 'fail',
                    'message': 'Invalid credentials.'
                }
                return make_response(jsonify(responseObject)), 202
        except Exception as e:
            print(e)
            responseObject = {
                'status': 'fail',
                'message': 'Try again'
            }
            return make_response(jsonify(responseObject)), 500


# define the API resources
registration_view = RegisterAPI.as_view('register_api')
login_view = LoginAPI.as_view('login_api')

# add Rules for API Endpoints
auth.add_url_rule(
    '/register',
    view_func=registration_view,
    methods=['POST']
)
auth.add_url_rule(
    '/login',
    view_func=login_view,
    methods=['GET', 'POST']
)


@auth.route('/confirm/<token>')
def confirm(token):
    current_user = User.verify_confirmation_token(token)
    if not bool(current_user):
        return redirect(
            os.environ.get('BASE_LINK') + '/flash/' + 'An error occured, try resend confirmation link!$home')
    if current_user.confirmed:
        return redirect(os.environ.get('BASE_LINK') + '/home')
    if current_user.confirm(token):
        db.session.commit()
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'You have confirmed your account£ Thanks!$home')
    else:
        return redirect(
            os.environ.get('BASE_LINK') + '/flash/' + 'The confirmation link is invalid or has expired£$home')


@auth.route('/re-confirm/<token>')
def resend_confirmation(token):
    current_user = User.verify_auth_token(token)
    if bool(current_user):
        token = current_user.generate_confirmation_token()
        send_email(current_user.email, 'Confirm Your Account',
                   'auth/email/confirm', user=current_user, token=token)
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'A new confirmation email has been sent to you by '
                                                                  'email£$home')
    else:
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Session expired, log in required£$login')


@auth.route('/reset', methods=['GET', 'POST'])
def password_reset_request():
    user = User.query.filter_by(email=request.get_json().get("email").lower()).first()
    if user:
        token = user.generate_reset_token().replace(".", "£")
        send_email(user.email, 'Reset Your Password',
                   'auth/email/reset_password',
                   user=user, token=token)
        responseObject = {
            'status': 'success',
            'message': 'Reset request submitted.'
        }
        return make_response(jsonify(responseObject)), 200
    else:
        responseObject = {
            'status': 'fail',
            'message': 'User does not exist.'
        }
        return make_response(jsonify(responseObject)), 202


@auth.route('/reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    if User.reset_password(token, request.get_json().get("password")):
        db.session.commit()
        responseObject = {
            'status': 'success',
            'message': 'Your password has been updated.'
        }
        return make_response(jsonify(responseObject)), 200
    else:
        return redirect(os.environ.get('BASE_LINK') + '/home')


@auth.route('/change_email', methods=['GET', 'POST'])
@token_auth.login_required
def change_email_request():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        post_data = request.get_json()
        if user.verify_password(post_data.get('password')):
            new_email = post_data.get('new_email').lower()
            token = user.generate_email_change_token(new_email)
            send_email(new_email, 'Confirm your email address',
                       'auth/email/change_email',
                       user=user, token=token)
            responseObject = {
                'status': 'success',
                'message': 'An email with instructions to '
                           'confirm your new email address '
                           'has been sent to you.'
            }
            return make_response(jsonify(responseObject)), 200
        else:
            responseObject = {
                'status': 'invalid',
                'message': 'Invalid email or password.'
            }
            return make_response(jsonify(responseObject)), 202
    else:
        responseObject = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(responseObject)), 202


@auth.route('/change_email/<token>')
def change_email(token):
    current_user = User.verify_change_email_token(token)
    if current_user.change_email(token):
        db.session.commit()
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Your email address has been updated£$home')
    else:
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Link expired, or invalid request£$home')


@auth.route('/change-password', methods=['GET', 'POST'])
@token_auth.login_required
def change_password():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        post_data = request.get_json()
        if user.verify_password(post_data.get('old_password')):
            user.password = post_data.get('new_password')
            db.session.add(user)
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Your password has been updated.'
            }
            return make_response(jsonify(responseObject)), 200
        else:
            responseObject = {
                'status': 'invalid',
                'message': 'Invalid password.'
            }
            return make_response(jsonify(responseObject)), 202
    else:
        responseObject = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(responseObject)), 202
