from flask import make_response, jsonify, request
from . import api
from app.api.models import User, UserPropertyAccess, Role
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.constants import Constants
from app import db


# Helper function to get the numeric rank of the current user to enforce hierarchy
def get_user_rank(user, property_id):
    # Super Admin bypasses and gets the highest rank
    if user.is_super_admin:
        return Constants.RoleHierarchy.get('Super Admin', 50)

    # Get the user's role for this specific property
    access = UserPropertyAccess.query.filter_by(user_id=user.uid, property_id=property_id).first()
    if access and access.role:
        return Constants.RoleHierarchy.get(access.role.name, 0)
    return 0


@api.route('/users')
def get_user():
    resp = get_current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        responseObject = {
            'status': 'success',
            'data': user.to_json()
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/properties/<int:property_id>/staff', methods=['POST'])
@require_permission('manage_staff')
def assign_staff_role(property_id):
    """
    Links an existing User (who just registered) to a Property with a specific Role.
    The account defaults to a 'Pending' status and must be activated by a superior.
    """
    current_uid = get_current_user()
    current_user = User.query.get(current_uid)

    target_user_uid = request.json.get('user_uid')
    role_id = request.json.get('role_id')
    role = Role.query.get(role_id)

    if not role:
        return make_response(jsonify({'status': 'fail', 'message': 'Role not found.'})), 404

    current_user_rank = get_user_rank(current_user, property_id)
    target_role_rank = Constants.RoleHierarchy.get(role.name, 0)

    # HIERARCHY CHECK: Superior can only assign roles strictly below their own level
    if current_user_rank <= target_role_rank:
        return make_response(jsonify({
            'status': 'fail',
            'message': 'Forbidden: You cannot assign roles at or above your own level.'
        })), 403

    existing_access = UserPropertyAccess.query.filter_by(user_id=target_user_uid, property_id=property_id).first()
    if existing_access:
        return make_response(jsonify({'status': 'fail', 'message': 'User already has a role in this property.'})), 400

    # Create the access mapping and default to Pending (1)
    new_access = UserPropertyAccess(
        user_id=target_user_uid,
        property_id=property_id,
        role_id=role.id,
        account_status_id=1
    )
    db.session.add(new_access)
    db.session.commit()

    return make_response(jsonify({
        'status': 'success',
        'message': f'Staff assigned successfully as {role.name} with Pending status.'
    })), 201


@api.route('/properties/<int:property_id>/staff/<string:target_user_uid>/status', methods=['PUT'])
@require_permission('manage_staff')
def update_staff_status(property_id, target_user_uid):
    """
    Allows a superior to Activate (2), Suspend (3), or Cancel (4) a subordinate's account.
    """
    current_uid = get_current_user()
    current_user = User.query.get(current_uid)

    target_access = UserPropertyAccess.query.filter_by(user_id=target_user_uid, property_id=property_id).first()

    if not target_access:
        return make_response(jsonify({'status': 'fail', 'message': 'Target user not found in this property.'})), 404

    current_user_rank = get_user_rank(current_user, property_id)
    target_user_rank = Constants.RoleHierarchy.get(target_access.role.name, 0)

    # HIERARCHY CHECK: Superior can only change status of users strictly below their own level
    if current_user_rank <= target_user_rank:
        return make_response(jsonify({
            'status': 'fail',
            'message': 'Forbidden: You can only manage roles below your own level.'
        })), 403

    new_status_code = request.json.get('status_id')
    if new_status_code not in Constants.AccountStatusCoding:
        return make_response(jsonify({'status': 'fail', 'message': 'Invalid status ID.'})), 400

    # Update the status
    target_access.account_status_id = new_status_code
    db.session.commit()

    status_name = Constants.AccountStatusCoding[new_status_code]
    return make_response(jsonify({
        'status': 'success',
        'message': f'Account status successfully updated to {status_name}.'
    })), 200