from functools import wraps
from flask import request, jsonify, make_response

# Ensure these import paths match your project structure
from app.auth.utils import get_current_user
from app.api.models import User, UserPropertyAccess
from app.api.constants import Constants


def token_required(f):
    """
    Ensures the request includes a valid Firebase bearer token and that the
    corresponding user exists in the database.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'OPTIONS':
            return make_response(jsonify({"status": "ok"})), 200

        current_uid = get_current_user()
        if not current_uid:
            return make_response(
                jsonify({'status': 'fail', 'message': 'Unauthorized: Missing or invalid token.'})
            ), 401

        user = User.query.get(current_uid)
        if not user:
            return make_response(
                jsonify({'status': 'fail', 'message': 'User not found in database.'})
            ), 404

        return f(*args, **kwargs)

    return decorated_function


def require_auth(f):
    """
    Backward-compatible auth-only decorator for routes that just need a valid
    authenticated user.
    """
    return token_required(f)


def require_permission(required_permission):
    """
    Ensures the user is Active and their assigned role at the target property
    contains the specific permission required to execute the action.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 0. Instant CORS Preflight Bypass
            if request.method == 'OPTIONS':
                return make_response(jsonify({"status": "ok"})), 200

            # 1. Authenticate User via Firebase Token
            user_uid = get_current_user()
            if not user_uid:
                return make_response(
                    jsonify({'status': 'fail', 'message': 'Unauthorized: Missing or invalid token.'})), 401

            user = User.query.get(user_uid)
            if not user:
                return make_response(jsonify({'status': 'fail', 'message': 'User not found in database.'})), 404

            # 2. Super Admins bypass all property-level checks
            if user.is_super_admin:
                return f(*args, **kwargs)

            # 3. Determine the Target Property ID
            property_id = kwargs.get('property_id')

            if not property_id and request.is_json:
                property_id = request.get_json().get('property_id')

            if not property_id:
                property_id = request.args.get('property_id', type=int)

            if not property_id:
                return make_response(jsonify({
                    'status': 'fail',
                    'message': 'A valid property_id is required to check access permissions.'
                })), 400

            # 4. Verify Access in Database
            access = UserPropertyAccess.query.filter_by(
                user_id=user_uid,
                property_id=property_id
            ).first()

            if not access or not access.role:
                return make_response(
                    jsonify({'status': 'fail', 'message': 'Forbidden: You are not assigned to this property.'})), 403

            # 5. Ensure the account has been approved/activated by a superior
            if access.account_status_id != 2:  # 2 = Active
                status_name = Constants.AccountStatusCoding.get(access.account_status_id, "Unknown")
                return make_response(jsonify({
                    'status': 'fail',
                    'message': f'Forbidden: Your account is currently {status_name}.'
                })), 403

            # 6. Check if the assigned role has the specific permission
            # Safely handle cases where permissions_json might be None
            user_permissions = access.role.permissions_json or []
            if required_permission not in user_permissions:
                return make_response(jsonify({
                    'status': 'fail',
                    'message': f'Forbidden: Action requires the [{required_permission}] permission.'
                })), 403

            # Success! Proceed to the route
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_active_staff(f):
    """
    Allows any Active staff member belonging to the property to access the route.
    Does not check for specific granular permissions.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 0. Instant CORS Preflight Bypass
        if request.method == 'OPTIONS':
            return make_response(jsonify({"status": "ok"})), 200

        # 1. Authenticate User
        current_uid = get_current_user()
        if not current_uid:
            return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized: Missing or invalid token.'})), 401

        user = User.query.get(current_uid)
        if not user:
            return make_response(jsonify({'status': 'fail', 'message': 'User not found in database.'})), 404

        # 2. Super Admin Bypass
        if user.is_super_admin:
            return f(*args, **kwargs)

        # 3. Extract Property ID dynamically (Mirrored from require_permission)
        property_id = kwargs.get('property_id')
        if not property_id and request.is_json:
            property_id = request.get_json().get('property_id')
        if not property_id:
            property_id = request.args.get('property_id', type=int)

        if not property_id:
            return make_response(jsonify({'status': 'fail', 'message': 'Property ID missing in request.'})), 400

        # 4. Check Access & Status
        access = UserPropertyAccess.query.filter_by(user_id=current_uid, property_id=property_id).first()
        if not access or access.account_status_id != 2:  # 2 = Active
            return make_response(jsonify(
                {'status': 'fail', 'message': 'Forbidden: You are not an active staff member at this property.'})), 403

        # Success! Proceed to the route
        return f(*args, **kwargs)

    return decorated_function
