import logging
from flask import request, current_app, make_response, jsonify, abort
from flask_sqlalchemy.record_queries import get_recorded_queries

from . import api
from .. import db
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


@api.route('/avatar', methods=['GET', 'OPTIONS'], strict_slashes=False)
def avatar():
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if uid:
            user = User.query.get_or_404(uid)
            return make_response(jsonify({
                'status': 'success',
                'data': user.gravatar(size=128)
            })), 200

        return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401
    except Exception as e:
        logging.exception("Error in avatar: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch avatar.'})), 500


@api.route('/notifs-count', methods=['GET', 'OPTIONS'], strict_slashes=False)
def notifications_count():
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if uid:
            count = Notification.query.filter_by(to_user=uid, is_read=False).count()
            return make_response(jsonify({'status': 'success', 'data': count})), 200

        return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401
    except Exception as e:
        logging.exception("Error in notifications_count: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch notification count.'})), 500


@api.route('/notifications', methods=['GET', 'OPTIONS'], strict_slashes=False)
def notifications():
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if uid:
            notifications_list = Notification.query.filter_by(to_user=uid, is_read=False) \
                .order_by(Notification.timestamp.desc()).limit(6).all()

            data = [n.to_json() for n in notifications_list]
            return make_response(jsonify({'status': 'success', 'data': data, 'page': 0})), 200

        return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401
    except Exception as e:
        logging.exception("Error in notifications: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch notifications.'})), 500


@api.route('/all-notifications', methods=['GET', 'OPTIONS'], strict_slashes=False)
def all_notifications():
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if uid:
            notifications_list = Notification.query.filter_by(to_user=uid) \
                .order_by(Notification.timestamp.desc()).all()

            data = [n.to_json() for n in notifications_list]
            return make_response(jsonify({'status': 'success', 'data': data, 'page': 0})), 200

        return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401
    except Exception as e:
        logging.exception("Error in all_notifications: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch all notifications.'})), 500


@api.route('/notifications/<int:notification_id>/read', methods=['PUT', 'OPTIONS'], strict_slashes=False)
def mark_notification_read(notification_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if not uid:
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401

        notification = Notification.query.filter_by(id=notification_id, to_user=uid).first()
        if not notification:
            return make_response(jsonify({'status': 'fail', 'message': 'Notification not found.'})), 404

        notification.is_read = True
        db.session.commit()
        return make_response(jsonify({'status': 'success', 'message': 'Notification marked as read.'})), 200
    except Exception as e:
        logging.exception("Error in mark_notification_read: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update notification.'})), 500


@api.route('/notifications/read-all', methods=['PUT', 'OPTIONS'], strict_slashes=False)
def mark_all_notifications_read():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if not uid:
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401

        Notification.query.filter_by(to_user=uid, is_read=False).update(
            {'is_read': True},
            synchronize_session=False,
        )
        db.session.commit()
        return make_response(jsonify({'status': 'success', 'message': 'Notifications marked as read.'})), 200
    except Exception as e:
        logging.exception("Error in mark_all_notifications_read: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update notifications.'})), 500


@api.route('/edit-profile', methods=['POST', 'OPTIONS'], strict_slashes=False)
def edit_profile():
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        uid = get_current_user()
        if uid:
            user = User.query.get_or_404(uid)
            post_data = request.get_json()

            if not post_data:
                return make_response(jsonify({'status': 'fail', 'message': 'Invalid payload'})), 400

            user.name = post_data.get('name', user.name)
            user.location = post_data.get('location', user.location)
            user.about_me = post_data.get('about', user.about_me)

            db.session.commit()

            return make_response(jsonify({
                'status': 'success',
                'message': 'Your profile has been updated.',
                'user': user.to_json()
            })), 200

        return make_response(jsonify({'status': 'fail', 'message': 'Session expired, login required!'})), 401

    except Exception as e:
        logging.exception("Error in edit_profile: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update profile.'})), 500


@api.route('/admin/edit-profile/<string:target_uid>', methods=['POST', 'OPTIONS'], strict_slashes=False)
def edit_profile_admin(target_uid):
    """
    JSON API for Super Admins to edit other users' core profiles and grant Super Admin rights.
    """
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        current_uid = get_current_user()
        if not current_uid:
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized'})), 401

        current_user = User.query.get(current_uid)

        # Explicitly checking for Super Admin status since this is a global action
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

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'User profile updated successfully.',
            'user': target_user.to_json()
        })), 200

    except Exception as e:
        logging.exception("Error in edit_profile_admin: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update user profile.'})), 500
