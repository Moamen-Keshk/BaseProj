# from flask import render_template, redirect, request, url_for, flash, g
# from flask_login import login_user, logout_user, login_required
# from flask import jsonify
# from flask_httpauth import HTTPBasicAuth
# from .models import User
# from . import api
# from app.auth.views import auth
# from .errors import unauthorized, forbidden
# from .email import send_email
# from .. import db
# from .forms import LoginForm, RegistrationForm, ChangePasswordForm,\
#     PasswordResetRequestForm, PasswordResetForm, ChangeEmailForm
#
#
# authin = HTTPBasicAuth()
#
#
# @authin.verify_password
# def verify_password(email_or_token, password):
#     if email_or_token == '':
#         return False
#     if password == '':
#         g.current_user = User.verify_auth_token(email_or_token)
#         g.token_used = True
#         return g.current_user is not None
#     user = User.query.filter_by(email=email_or_token.lower()).first()
#     if not user:
#         return False
#     g.current_user = user
#     g.token_used = False
#     return user.verify_password(password)
#
#
# @authin.error_handler
# def auth_error():
#     return unauthorized('Invalid credentials')
#
#
# @api.before_request
# @login_required
# def before_request():
#     if not g.current_user.is_anonymous and \
#             not g.current_user.confirmed:
#         return forbidden('Unconfirmed account')
#
# #
# # @auth.route('/tokens/', methods=['POST'])
# # def get_token():
# #     data = request.json
# #     user = User.query.filter_by(email=data.get('email').lower()).first()
# #     if user is not None and user.verify_password(data.get('password')):
# #         login_user(user)
# #         return jsonify({'token': user.generate_auth_token(
# #             expiration=3600), 'expiration': 3600})
# #     flash('Invalid email or password.')
# #     return unauthorized('Invalid credentials')
# #
# #
# # @auth.route('/login', methods=['GET', 'POST'])
# # def login():
# #     form = LoginForm()
# #     if form.validate_on_submit():
# #         user = User.query.filter_by(email=form.email.data.lower()).first()
# #         if user is not None and user.verify_password(form.password.data):
# #             login_user(user, form.remember_me.data)
# #             next = request.args.get('next')
# #             if next is None or not next.startswith('/'):
# #                 next = url_for('api.index')
# #             return redirect(next)
# #         flash('Invalid email or password.')
# #     return render_template('auth/login.html', form=form)
# #
# #
# # @auth.route('/logout')
# # @authin.login_required
# # def logout():
# #     logout_user()
# #     flash('You have been logged out.')
# #     return redirect(url_for('api.index'))
# #
# #
# # @auth.route('/register', methods=['GET', 'POST'])
# # def register():
# #     form = RegistrationForm()
# #     if form.validate_on_submit():
# #         user = User(email=form.email.data.lower(),
# #                     username=form.username.data,
# #                     password=form.password.data)
# #         db.session.add(user)
# #         db.session.commit()
# #         token = user.generate_confirmation_token()
# #         send_email(user.email, 'Confirm Your Account',
# #                    'auth/email/confirm', user=user, token=token)
# #         flash('A confirmation email has been sent to you by email.')
# #         return redirect(url_for('auth.login'))
# #     return render_template('auth/register.html', form=form)
#
#
# @auth.route('/auth/confirm/<token>')
# @login_required
# def confirm(token):
#     if g.current_user.confirmed:
#         return redirect(url_for('api.index'))
#     if g.current_user.confirm(token):
#         db.session.commit()
#         flash('You have confirmed your account. Thanks!')
#     else:
#         flash('The confirmation link is invalid or has expired.')
#     return redirect(url_for('api.index'))
#
#
# @auth.route('/auth/confirm')
# @login_required
# def resend_confirmation():
#     token = g.current_user.generate_confirmation_token()
#     send_email(g.current_user.email, 'Confirm Your Account',
#                'auth/email/confirm', user=g.current_user, token=token)
#     flash('A new confirmation email has been sent to you by email.')
#     return redirect(url_for('api.index'))
#
#
# @auth.route('/auth/change-password', methods=['GET', 'POST'])
# @login_required
# def change_password():
#     form = ChangePasswordForm()
#     if form.validate_on_submit():
#         if g.current_user.verify_password(form.old_password.data):
#             g.current_user.password = form.password.data
#             db.session.add(g.current_user)
#             db.session.commit()
#             flash('Your password has been updated.')
#             return redirect(url_for('api.index'))
#         else:
#             flash('Invalid password.')
#     return render_template("auth/change_password.html", form=form)
#
#
# @auth.route('/auth/reset', methods=['GET', 'POST'])
# def password_reset_request():
#     if not g.current_user.is_anonymous:
#         return redirect(url_for('api.index'))
#     form = PasswordResetRequestForm()
#     if form.validate_on_submit():
#         user = User.query.filter_by(email=form.email.data.lower()).first()
#         if user:
#             token = user.generate_reset_token()
#             send_email(user.email, 'Reset Your Password',
#                        'auth/email/reset_password',
#                        user=user, token=token)
#         flash('An email with instructions to reset your password has been '
#               'sent to you.')
#         return redirect(url_for('auth.login'))
#     return render_template('auth/reset_password.html', form=form)
#
#
# @auth.route('/auth/reset/<token>', methods=['GET', 'POST'])
# def password_reset(token):
#     if not g.current_user.is_anonymous:
#         return redirect(url_for('api.index'))
#     form = PasswordResetForm()
#     if form.validate_on_submit():
#         if User.reset_password(token, form.password.data):
#             db.session.commit()
#             flash('Your password has been updated.')
#             return redirect(url_for('auth.login'))
#         else:
#             return redirect(url_for('api.index'))
#     return render_template('auth/reset_password.html', form=form)
#
#
# @auth.route('/auth/change_email', methods=['GET', 'POST'])
# @login_required
# def change_email_request():
#     form = ChangeEmailForm()
#     if form.validate_on_submit():
#         if g.current_user.verify_password(form.password.data):
#             new_email = form.email.data.lower()
#             token = g.current_user.generate_email_change_token(new_email)
#             send_email(new_email, 'Confirm your email address',
#                        'auth/email/change_email',
#                        user=g.current_user, token=token)
#             flash('An email with instructions to confirm your new email '
#                   'address has been sent to you.')
#             return redirect(url_for('api.index'))
#         else:
#             flash('Invalid email or password.')
#     return render_template("auth/change_email.html", form=form)
#
#
# @auth.route('/auth/change_email/<token>')
# @login_required
# def change_email(token):
#     if g.current_user.change_email(token):
#         db.session.commit()
#         flash('Your email address has been updated.')
#     else:
#         flash('Invalid request.')
#     return redirect(url_for('api.index'))
#
#
# @auth.route('/auth/unconfirmed')
# def unconfirmed():
#     if g.current_user.is_anonymous or g.current_user.confirmed:
#         return redirect(url_for('api.index'))
#     return render_template('auth/unconfirmed.html')
