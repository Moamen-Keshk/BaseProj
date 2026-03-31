from flask import request, current_app, make_response, jsonify, abort
from flask_sqlalchemy.record_queries import get_recorded_queries

from . import api
from .. import db
# REMOVED: Order, Role. ADDED: User, Notification
from app.api.models import User, Notification
from app.auth.utils import get_current_user


@api.after_app_request
def after_request(response):
    for query in get_recorded_queries():
        if query.duration >= current_app.config['SLOW_DB_QUERY_TIME']:
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
    uid = get_current_user()
    if uid and isinstance(uid, str):
        user = User.query.get_or_404(uid)
        return make_response(jsonify({
            'status': 'success',
            'data': user.gravatar(size=128)
        })), 200

    return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401


@api.route('/notifs-count')
def notifications_count():
    uid = get_current_user()
    if uid and isinstance(uid, str):
        count = Notification.query.filter_by(to_user_uid=uid, is_read=False).count()
        return make_response(jsonify({'status': 'success', 'data': count})), 200

    return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401


@api.route('/notifications')
def notifications():
    uid = get_current_user()
    if uid and isinstance(uid, str):
        notifications_list = Notification.query.filter_by(to_user_uid=uid, is_read=False) \
            .order_by(Notification.timestamp.desc()).limit(6).all()

        data = [n.to_json() for n in notifications_list]
        return make_response(jsonify({'status': 'success', 'data': data, 'page': 0})), 200

    return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401


@api.route('/all-notifications')
def all_notifications():
    uid = get_current_user()
    if uid and isinstance(uid, str):
        notifications_list = Notification.query.filter_by(to_user_uid=uid) \
            .order_by(Notification.timestamp.desc()).all()

        data = [n.to_json() for n in notifications_list]
        return make_response(jsonify({'status': 'success', 'data': data, 'page': 0})), 200

    return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401


@api.route('/edit-profile', methods=['POST'])
def edit_profile():
    uid = get_current_user()
    if uid and isinstance(uid, str):
        user = User.query.get_or_404(uid)
        post_data = request.get_json()

        if not post_data:
            return make_response(jsonify({'status': 'fail', 'message': 'Invalid payload'})), 400

        user.name = post_data.get('name', user.name)
        user.location = post_data.get('location', user.location)
        user.about_me = post_data.get('about', user.about_me)

        db.session.add(user)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Your profile has been updated.',
            'user': user.to_json()
        })), 200

    return make_response(jsonify({'status': 'fail', 'message': 'Session expired, login required!'})), 401


@api.route('/admin/edit-profile/<string:target_uid>', methods=['POST'])
def edit_profile_admin(target_uid):
    """
    JSON API for Super Admins to edit other users' core profiles.
    Replaces the old HTML template form rendering.
    """
    current_uid = get_current_user()
    if not current_uid:
        return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401

    current_user = User.query.get(current_uid)
    if not current_user or not current_user.is_super_admin:
        return make_response(jsonify({'status': 'fail', 'message': 'Super Admin access required.'})), 403

    target_user = User.query.get_or_404(target_uid)
    post_data = request.get_json()

    if not post_data:
        return make_response(jsonify({'status': 'fail', 'message': 'Invalid payload'})), 400

    target_user.email = post_data.get('email', target_user.email)
    target_user.username = post_data.get('username', target_user.username)
    target_user.name = post_data.get('name', target_user.name)
    target_user.location = post_data.get('location', target_user.location)
    target_user.about_me = post_data.get('about_me', target_user.about_me)

    # Toggle Super Admin status
    if 'is_super_admin' in post_data:
        target_user.is_super_admin = bool(post_data['is_super_admin'])

    db.session.add(target_user)
    db.session.commit()

    return make_response(jsonify({
        'status': 'success',
        'message': 'User profile updated successfully.',
        'user': target_user.to_json()
    })), 200