from flask import render_template, redirect, url_for, abort, flash, request,\
    current_app, make_response, jsonify
from flask_sqlalchemy.record_queries import get_recorded_queries
from . import api
import logging
from .forms import EditProfileAdminForm
from .. import db
from .models import Role, User, Notification, Order
from .decorators import admin_required
from app.auth.views import get_current_user


@api.after_app_request
def after_request(response):
    for query in get_recorded_queries():
        if query.duration >= current_app.config['FLASKY_SLOW_DB_QUERY_TIME']:
            current_app.logger.warning(
                'Slow query: %s\nParameters: %s\nDuration: %fs\nContext: %s\n'
                % (query.statement, query.parameters, query.duration,
                   query.location))
    return response


@api.route('/shutdown')
def server_shutdown():
    if not current_app.testing:
        abort(404)
    shutdown = request.environ.get('werkzeug.server.shutdown')
    if not shutdown:
        abort(500)
    shutdown()
    return 'Shutting down...'


@api.route('/avatar')
def avatar():
    resp = get_current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        responseObject = {
            'status': 'success',
            'data': user.gravatar(size=18)
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/notifs-count')
def notifications_count():
    uid = get_current_user()
    if not isinstance(uid, str):
        responseObject = {
            'status': 'success',
            'data': Notification.query.filter_by(to_user=uid, is_read=False).count()
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': uid
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/notifications')
def notifications():
    resp = get_current_user()
    if isinstance(resp, str):
        notifications_list = Notification.query.filter_by(to_user=resp, is_read=False).order_by(
            Notification.timestamp.desc()).limit(6).all()
        for x in notifications_list:
            notifications_list[notifications_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': notifications_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/all-notifications')
def all_notifications():
    resp = get_current_user()
    if not isinstance(resp, str):
        notifications_list = Notification.query.filter_by(
            to_user=resp, is_read=False).order_by(Notification.timestamp.desc()).all()
        for x in notifications_list:
            notifications_list[notifications_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': notifications_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/order-list/<int:status_id>')
def order_list(status_id):
    resp = get_current_user()
    if not isinstance(resp, str):
        try:
            orders_list = [o.to_json() for o in Order.query.filter_by(
                status_id=status_id).order_by(Order.id.desc()).all()]
            responseObject = {
                'status': 'success',
                'data': orders_list,
                'page': 0
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/order-detail/<int:order_id>')
def order_detail(order_id):
    resp = get_current_user()
    if not isinstance(resp, str):
        try:
            orders_detail = Order.query.get_or_404(order_id).to_json()
            responseObject = {
                'status': 'success',
                'data': orders_detail,
                'page': 0
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/advance-orders', methods=['GET', 'POST'])
def advance_orders():
    resp = get_current_user()
    if not isinstance(resp, str):
        try:
            orders_list = Order.query.filter(Order.id.in_(request.get_json().get('order_ids'))).all()
            new_status_id = (request.get_json().get('status_id')+1)
            for o in orders_list:
                o.status_id = new_status_id
                db.session.add(o)
            db.session.commit()
            responseObject = {
                'status': 'success',
                'page': 0
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    resp = get_current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        post_data = request.get_json()
        user.name = post_data.get('name')
        user.location = post_data.get('location')
        user.about_me = post_data.get('about')
        db.session.add(user)
        db.session.commit()
        responseObject = {
            'status': 'success',
            'message': 'Your profile has been updated.'
        }
        return make_response(jsonify(responseObject)), 200
    else:
        responseObject = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(responseObject)), 202


@api.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_profile_admin(idi):
    user = User.query.get_or_404(idi)
    form = EditProfileAdminForm(user=user)
    if form.validate_on_submit():
        user.email = form.email.data
        user.username = form.username.data
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.name = form.name.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        db.session.commit()
        flash('The profile has been updated.')
        return redirect(url_for('.get_user', id=user.id))
    form.email.data = user.email
    form.username.data = user.username
    form.confirmed.data = user.confirmed
    form.role.data = user.role_id
    form.name.data = user.name
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('edit_profile.html', form=form, user=user)
