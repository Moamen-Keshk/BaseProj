from functools import wraps
from flask import request, jsonify, make_response
from app.auth.utils import get_current_user
from app.api.models import User, UserPropertyAccess


def require_permission(required_permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Authenticate User
            user_uid = get_current_user()
            if not isinstance(user_uid, str):
                return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized access.'})), 401

            user = User.query.get(user_uid)
            if not user:
                return make_response(jsonify({'status': 'fail', 'message': 'User not found.'})), 404

            # 2. Super Admins bypass all property-level checks
            if user.is_super_admin:
                return f(*args, **kwargs)

            # 3. Determine the Target Property ID
            # Look in URL route variables first (e.g., /properties/<int:property_id>/sync)
            property_id = kwargs.get('property_id')

            # Look in JSON body if not in URL
            if not property_id and request.is_json:
                property_id = request.get_json().get('property_id')

            # Look in Query Parameters (e.g., GET /bookings?property_id=1)
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

            # 5. Check if the assigned role has the specific permission
            if required_permission not in access.role.permissions_json:
                return make_response(jsonify({
                    'status': 'fail',
                    'message': f'Forbidden: Action requires the [{required_permission}] permission.'
                })), 403

            # Success! Proceed to the route
            return f(*args, **kwargs)

        return decorated_function

    return decorator