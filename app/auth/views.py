import os
import logging
from flask import make_response, jsonify, redirect
from flask.views import MethodView
from app.api.email import send_email
from . import auth
from typing import Optional
from flask import request
from firebase_admin.auth import verify_id_token

from .. import db
from app.api.models import User


def get_current_user() -> Optional[str]:
    # Return None if no Authorization header.
    if "Authorization" not in request.headers:
        return None
    authorization = request.headers["Authorization"]

    # Authorization header format is "Bearer <token>".
    # This matches OAuth 2.0 spec:
    # https://www.rfc-editor.org/rfc/rfc6750.txt.
    if not authorization.startswith("Bearer "):
        return None

    token = authorization.split("Bearer ")[1]
    try:
        # Verify that the token is valid.
        result = verify_id_token(token, clock_skew_seconds=10)
        # Return the user ID of the authenticated user.
        return result["uid"]
    except Exception as e:
        logging.exception(e)
        return None


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
                    uid=get_current_user(),
                    username=post_data.get('username'),
                    email=post_data.get('email'),
                    password=post_data.get('password'),
                )

                # insert the user
                db.session.add(user)
                db.session.commit()
                # generate the auth token
                responseObject = {
                    'status': 'success',
                    'message': 'Successfully registered.'
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


# define the API resources
registration_view = RegisterAPI.as_view('register_api')

# add Rules for API Endpoints
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
def change_email_request():
    resp = get_current_user()
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
def change_password():
    resp = get_current_user()
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
