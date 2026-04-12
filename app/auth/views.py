import os
import logging

from flask import make_response, jsonify, redirect, request
from flask.views import MethodView
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest

from app.api.email import send_email
from app.api.models import User, PropertyInvite, UserPropertyAccess
from . import auth
from .utils import get_current_user

from .. import db


logger = logging.getLogger(__name__)


def normalize_email(email):
    if not isinstance(email, str):
        return ''
    return email.strip().lower()


class RegisterAPI(MethodView):
    """
    User Registration Resource
    """

    @staticmethod
    def post():
        try:
            post_data = request.get_json()
            email = normalize_email(post_data.get('email'))

            user = User.query.filter(func.lower(User.email) == email).first()
            if not user:
                if User.query.filter_by(username=post_data.get('username')).first():
                    response_object = {
                        'status': 'username',
                        'message': 'Username already in use.',
                    }
                    return make_response(jsonify(response_object)), 409  # Changed to 409 Conflict

                # Capture uid first so we can use it for UserPropertyAccess if needed
                new_uid = get_current_user()

                user = User(
                    uid=new_uid,
                    username=post_data.get('username'),
                    email=email,
                    password=post_data.get('password'),
                )

                db.session.add(user)

                # ---> CHECK FOR INVITE CODE <---
                invite_code = post_data.get('invite_code')
                if invite_code:
                    invite = PropertyInvite.query.filter_by(
                        invite_code=invite_code,
                        is_used=False
                    ).filter(func.lower(PropertyInvite.email) == email).first()

                    if invite:
                        # Consume the invite
                        invite.is_used = True

                        # Automatically assign the role and make them ACTIVE (2)
                        new_access = UserPropertyAccess(
                            user_id=new_uid,
                            property_id=invite.property_id,
                            role_id=invite.role_id,
                            account_status_id=2  # Active immediately because a manager invited them
                        )
                        db.session.add(new_access)

                # Commit both the new User and their Role Access (if applicable) at the same time
                db.session.commit()

                response_object = {
                    'status': 'success',
                    'message': 'Successfully registered.'
                }
                return make_response(jsonify(response_object)), 201

            else:
                response_object = {
                    'status': 'exist',
                    'message': 'User already exists. Please Log in.',
                }
                return make_response(jsonify(response_object)), 409  # Changed to 409 Conflict

        except (AttributeError, BadRequest, SQLAlchemyError, TypeError, ValueError) as exc:
            logger.exception("Error in registration: %s", exc)
            db.session.rollback()  # Rollback to prevent database locks on crash
            response_object = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(response_object)), 500


registration_view = RegisterAPI.as_view('register_api')

auth.add_url_rule(
    '/register',
    view_func=registration_view,
    methods=['POST']
)


@auth.route('/reset', methods=['GET', 'POST'])
def password_reset_request():
    try:
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
            return make_response(jsonify(response_object)), 404

    except (AttributeError, BadRequest, TypeError, ValueError) as exc:
        logger.exception("Error in password_reset_request: %s", exc)
        return make_response(jsonify({'status': 'error', 'message': 'Failed to process request.'})), 500


@auth.route('/reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    try:
        if User.reset_password(token, request.get_json().get("password")):
            db.session.commit()
            response_object = {
                'status': 'success',
                'message': 'Your password has been updated.'
            }
            return make_response(jsonify(response_object)), 200
        else:
            return redirect(os.environ.get('BASE_LINK') + '/home')

    except (AttributeError, BadRequest, SQLAlchemyError, TypeError, ValueError) as exc:
        logger.exception("Error in password_reset: %s", exc)
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update password.'})), 500


@auth.route('/change_email', methods=['GET', 'POST'])
def change_email_request():
    try:
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
                return make_response(jsonify(response_object)), 401
        else:
            response_object = {
                'status': 'fail',
                'message': 'Session expired, log in required!'
            }
            return make_response(jsonify(response_object)), 401

    except (AttributeError, BadRequest, TypeError, ValueError) as exc:
        logger.exception("Error in change_email_request: %s", exc)
        return make_response(jsonify({'status': 'error', 'message': 'Failed to process request.'})), 500


@auth.route('/change_email/<token>')
def change_email(token):
    try:
        current_user = User.verify_change_email_token(token)
        if current_user and current_user.change_email(token):
            db.session.commit()
            return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Your email address has been updated£$home')
        else:
            return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'Link expired, or invalid request£$home')

    except (AttributeError, SQLAlchemyError, TypeError, ValueError) as exc:
        logger.exception("Error in change_email confirmation: %s", exc)
        db.session.rollback()
        return redirect(os.environ.get('BASE_LINK') + '/flash/' + 'An error occurred during update£$home')


@auth.route('/change-password', methods=['GET', 'POST'])
def change_password():
    try:
        resp = get_current_user()
        if isinstance(resp, str):
            user = User.query.get_or_404(resp)
            post_data = request.get_json()

            if user.verify_password(post_data.get('old_password')):
                user.password = post_data.get('new_password')
                db.session.commit()

                response_object = {
                    'status': 'success',
                    'message': 'Your password has been updated.'
                }
                return make_response(jsonify(response_object)), 200
            else:
                response_object = {
                    'status': 'invalid',
                    'message': 'Invalid old password.'
                }
                return make_response(jsonify(response_object)), 401
        else:
            response_object = {
                'status': 'fail',
                'message': 'Session expired, log in required!'
            }
            return make_response(jsonify(response_object)), 401

    except (AttributeError, BadRequest, SQLAlchemyError, TypeError, ValueError) as exc:
        logger.exception("Error in change_password: %s", exc)
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update password.'})), 500
