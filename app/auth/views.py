import os
import logging

from flask import make_response, jsonify, redirect, request
from flask.views import MethodView

from app.api.email import send_email
from app.api.models import User
from . import auth
from .utils import get_current_user

from .. import db


class RegisterAPI(MethodView):
    """
    User Registration Resource
    """

    @staticmethod
    def post():
        post_data = request.get_json()

        user = User.query.filter_by(email=post_data.get('email')).first()
        if not user:
            if User.query.filter_by(username=post_data.get('username')).first():
                response_object = {
                    'status': 'username',
                    'message': 'Username already in use.',
                }
                return make_response(jsonify(response_object)), 202

            try:
                user = User(
                    uid=get_current_user(),
                    username=post_data.get('username'),
                    email=post_data.get('email'),
                    password=post_data.get('password'),
                )

                db.session.add(user)
                db.session.commit()

                response_object = {
                    'status': 'success',
                    'message': 'Successfully registered.'
                }
                return make_response(jsonify(response_object)), 201

            except Exception as e:
                logging.exception(e)
                response_object = {
                    'status': 'error',
                    'message': 'Some error occurred. Please try again.'
                }
                return make_response(jsonify(response_object)), 401
        else:
            response_object = {
                'status': 'exist',
                'message': 'User already exists. Please Log in.',
            }
            return make_response(jsonify(response_object)), 202


registration_view = RegisterAPI.as_view('register_api')

auth.add_url_rule(
    '/register',
    view_func=registration_view,
    methods=['POST']
)


@auth.route('/reset', methods=['GET', 'POST'])
def password_reset_request():
    user = User.query.filter_by(email=request.get_json().get("email").lower()).first()
    if user:
        token = user.generate_reset_token().replace(".", "£")
        send_email(
            user.email,
            'Reset Your Password',
            'auth/email/reset_password',
            user=user,
            token=token
        )
        response_object = {
            'status': 'success',
            'message': 'Reset request submitted.'
        }
        return make_response(jsonify(response_object)), 200
    else:
        response_object = {
            'status': 'fail',
            'message': 'User does not exist.'
        }
        return make_response(jsonify(response_object)), 202


@auth.route('/reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    if User.reset_password(token, request.get_json().get("password")):
        db.session.commit()
        response_object = {
            'status': 'success',
            'message': 'Your password has been updated.'
        }
        return make_response(jsonify(response_object)), 200
    else:
        return redirect(os.environ.get('BASE_LINK') + '/home')


@auth.route('/change_email', methods=['GET', 'POST'])
def change_email_request():
    resp = get_current_user()
    if isinstance(resp, str):
        user = User.query.get_or_404(resp)
        post_data = request.get_json()
        if user.verify_password(post_data.get('password')):
            new_email = post_data.get('new_email').lower()
            token = user.generate_email_change_token(new_email)
            send_email(
                new_email,
                'Confirm your email address',
                'auth/email/change_email',
                user=user,
                token=token
            )
            response_object = {
                'status': 'success',
                'message': 'An email with instructions to confirm your new email address has been sent to you.'
            }
            return make_response(jsonify(response_object)), 200
        else:
            response_object = {
                'status': 'invalid',
                'message': 'Invalid email or password.'
            }
            return make_response(jsonify(response_object)), 202
    else:
        response_object = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(response_object)), 202


@auth.route('/change_email/<token>')
def change_email(token):
    current_user = User.verify_change_email_token(token)
    if current_user and current_user.change_email(token):
        db.session.commit()
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Your email address has been updated£$home')
    else:
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Link expired, or invalid request£$home')


@auth.route('/change-password', methods=['GET', 'POST'])
def change_password():
    resp = get_current_user()
    if isinstance(resp, str):
        user = User.query.get_or_404(resp)
        post_data = request.get_json()
        if user.verify_password(post_data.get('old_password')):
            user.password = post_data.get('new_password')
            db.session.add(user)
            db.session.commit()
            response_object = {
                'status': 'success',
                'message': 'Your password has been updated.'
            }
            return make_response(jsonify(response_object)), 200
        else:
            response_object = {
                'status': 'invalid',
                'message': 'Invalid password.'
            }
            return make_response(jsonify(response_object)), 202
    else:
        response_object = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(response_object)), 202