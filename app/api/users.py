from flask import make_response, jsonify, request
from . import api
from app.api.models import User, UserPropertyAccess, Role, Property, PropertyInvite
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.constants import Constants
from app import db
from app.api.email import send_email


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
    current_uid = get_current_user()
    current_user = User.query.get(current_uid)

    target_user_uid = request.json.get('user_uid')
    role_id = request.json.get('role_id')

    role = Role.query.get(role_id)
    target_user = User.query.get(target_user_uid)
    target_property = Property.query.get(property_id)

    if not role or not target_user or not target_property:
        return make_response(jsonify({'status': 'fail', 'message': 'Invalid Role, User, or Property.'})), 404

    current_user_rank = get_user_rank(current_user, property_id)
    target_role_rank = Constants.RoleHierarchy.get(role.name, 0)

    if current_user_rank <= target_role_rank:
        return make_response(
            jsonify({'status': 'fail', 'message': 'Forbidden: Cannot assign roles at or above your level.'})), 403

    existing_access = UserPropertyAccess.query.filter_by(user_id=target_user_uid, property_id=property_id).first()
    if existing_access:
        return make_response(jsonify({'status': 'fail', 'message': 'User already has a role.'})), 400

    new_access = UserPropertyAccess(
        user_id=target_user_uid,
        property_id=property_id,
        role_id=role.id,
        account_status_id=1  # Pending
    )
    db.session.add(new_access)
    db.session.commit()

    # ---> SEND PENDING NOTIFICATION EMAIL <---
    send_email(
        to=target_user.email,
        subject='Role Assignment Pending Approval',
        template='mail/role_pending',  # You will need to create this template
        user=target_user,
        role_name=role.name,
        property_name=target_property.name,
        assigned_by=current_user.username
    )

    return make_response(jsonify({'status': 'success', 'message': 'Staff assigned with Pending status.'})), 201


@api.route('/properties/<int:property_id>/staff/<string:target_user_uid>/status', methods=['PUT'])
@require_permission('manage_staff')
def update_staff_status(property_id, target_user_uid):
    current_uid = get_current_user()
    current_user = User.query.get(current_uid)

    target_access = UserPropertyAccess.query.filter_by(user_id=target_user_uid, property_id=property_id).first()

    if not target_access:
        return make_response(jsonify({'status': 'fail', 'message': 'Target user not found in this property.'})), 404

    current_user_rank = get_user_rank(current_user, property_id)
    target_user_rank = Constants.RoleHierarchy.get(target_access.role.name, 0)

    if current_user_rank <= target_user_rank:
        return make_response(
            jsonify({'status': 'fail', 'message': 'Forbidden: You can only manage roles below your own level.'})), 403

    new_status_code = request.json.get('status_id')
    if new_status_code not in Constants.AccountStatusCoding:
        return make_response(jsonify({'status': 'fail', 'message': 'Invalid status ID.'})), 400

    target_access.account_status_id = new_status_code
    db.session.commit()

    status_name = Constants.AccountStatusCoding[new_status_code]
    target_user = User.query.get(target_user_uid)
    target_property = Property.query.get(property_id)

    # ---> SEND STATUS UPDATE EMAIL <---
    send_email(
        to=target_user.email,
        subject=f'Your Account Status is now: {status_name}',
        template='mail/status_update',  # You will need to create this template
        user=target_user,
        status_name=status_name,
        property_name=target_property.name,
        role_name=target_access.role.name
    )

    return make_response(jsonify({'status': 'success', 'message': f'Account status updated to {status_name}.'})), 200


@api.route('/properties/<int:property_id>/invites', methods=['POST'])
@require_permission('manage_staff')
def create_invite(property_id):
    """Generates an invitation code and emails it to the future staff member."""
    current_uid = get_current_user()
    current_user = User.query.get(current_uid)

    email = request.json.get('email')
    role_id = request.json.get('role_id')

    role = Role.query.get(role_id)
    target_property = Property.query.get(property_id)

    if not role or not email:
        return make_response(jsonify({'status': 'fail', 'message': 'Email and Role are required.'})), 400

    # HIERARCHY CHECK: Manager can only invite roles below them
    current_user_rank = get_user_rank(current_user, property_id)
    target_role_rank = Constants.RoleHierarchy.get(role.name, 0)

    if current_user_rank <= target_role_rank:
        return make_response(
            jsonify({'status': 'fail', 'message': 'Forbidden: Cannot invite roles at or above your level.'})), 403

    # Generate the invite
    invite = PropertyInvite(property_id=property_id, role_id=role.id, email=email)
    db.session.add(invite)
    db.session.commit()

    # ---> SEND THE INVITE EMAIL <---
    send_email(
        to=email,
        subject=f'You have been invited to join {target_property.name}',
        template='mail/staff_invite',  # You will need to create this template
        property_name=target_property.name,
        role_name=role.name,
        invite_code=invite.invite_code,
        invited_by=current_user.username
    )

    return make_response(jsonify({
        'status': 'success',
        'message': f'Invite sent to {email}.',
        'invite_code': invite.invite_code  # Returning it just in case the frontend wants to display it
    })), 201