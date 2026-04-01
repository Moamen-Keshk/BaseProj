import logging
from flask import make_response, jsonify, request
from . import api
from .. import db
from app.api.models import User, UserPropertyAccess, Role, Property, PropertyInvite
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.constants import Constants
from app.api.email import send_email


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_user_rank(user, property_id):
    """
    Returns the numeric rank of the user based on the RoleHierarchy to prevent
    lower-level staff from modifying higher-level staff.
    """
    if user.is_super_admin:
        return Constants.RoleHierarchy.get('Super Admin', 50)

    access = UserPropertyAccess.query.filter_by(user_id=user.uid, property_id=property_id).first()
    if access and access.role:
        return Constants.RoleHierarchy.get(access.role.name, 0)
    return 0


# ==========================================
# CURRENT USER PROFILE
# ==========================================

@api.route('/users', methods=['GET', 'OPTIONS'], strict_slashes=False)
def get_user():
    """Gets the profile of the currently logged-in user and attaches their PMS Role."""

    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    # 2. ACTUAL GET REQUEST LOGIC
    try:
        user_uid = get_current_user()

        if user_uid:
            user = User.query.get_or_404(user_uid)
            user_data = user.to_json()

            # Attach the Role & Access Status for Flutter
            if user.is_super_admin:
                user_data['account_status_id'] = 2  # Super Admins are always Active
                user_data['role_name'] = 'Super Admin'
                user_data['property_id'] = None
            else:
                access = UserPropertyAccess.query.filter_by(user_id=user.uid).first()
                if access:
                    user_data['account_status_id'] = access.account_status_id
                    user_data['role_name'] = access.role.name
                    user_data['property_id'] = access.property_id
                else:
                    user_data['account_status_id'] = 1
                    user_data['role_name'] = 'Unassigned'
                    user_data['property_id'] = None

            return make_response(jsonify({'status': 'success', 'data': user_data})), 201

        return make_response(jsonify({'status': 'fail', 'message': 'Unauthorized: Invalid Token'})), 401

    except Exception as e:
        logging.exception("Error in get_user: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch user.'})), 500


# ==========================================
# STAFF MANAGEMENT ENDPOINTS
# ==========================================

@api.route('/properties/<int:property_id>/staff', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def get_staff(property_id):
    """Returns a list of all staff members assigned to the property."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        access_records = UserPropertyAccess.query.filter_by(property_id=property_id).all()

        staff_list = []
        for access in access_records:
            status_name = Constants.AccountStatusCoding.get(access.account_status_id, 'Unknown')
            staff_list.append({
                'user_uid': access.user.uid,
                'username': access.user.username,
                'email': access.user.email,
                'role_name': access.role.name,
                'status_id': access.account_status_id,
                'status_name': status_name
            })

        return make_response(jsonify({
            'status': 'success',
            'data': staff_list
        })), 201
    except Exception as e:
        logging.exception("Error in get_staff: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch staff.'})), 500


@api.route('/properties/<int:property_id>/staff', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def assign_staff_role(property_id):
    """Directly links an existing User to a Property with a Pending Role."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
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

        # Send Email Notification
        send_email(
            to=target_user.email,
            subject='Role Assignment Pending Approval',
            template='mail/role_pending',
            user=target_user,
            role_name=role.name,
            property_name=target_property.name,
            assigned_by=current_user.username
        )

        return make_response(jsonify({'status': 'success', 'message': 'Staff assigned with Pending status.'})), 201

    except Exception as e:
        logging.exception("Error in assign_staff_role: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to assign staff.'})), 500


@api.route('/properties/<int:property_id>/staff/<string:target_user_uid>/status', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def update_staff_status(property_id, target_user_uid):
    """Activates, Suspends, or Cancels an existing staff account."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        current_uid = get_current_user()
        current_user = User.query.get(current_uid)

        target_access = UserPropertyAccess.query.filter_by(user_id=target_user_uid, property_id=property_id).first()

        if not target_access:
            return make_response(jsonify({'status': 'fail', 'message': 'Target user not found in this property.'})), 404

        current_user_rank = get_user_rank(current_user, property_id)
        target_user_rank = Constants.RoleHierarchy.get(target_access.role.name, 0)

        if current_user_rank <= target_user_rank:
            return make_response(
                jsonify(
                    {'status': 'fail', 'message': 'Forbidden: You can only manage roles below your own level.'})), 403

        new_status_code = request.json.get('status_id')
        if new_status_code not in Constants.AccountStatusCoding:
            return make_response(jsonify({'status': 'fail', 'message': 'Invalid status ID.'})), 400

        target_access.account_status_id = new_status_code
        db.session.commit()

        status_name = Constants.AccountStatusCoding[new_status_code]
        target_user = User.query.get(target_user_uid)
        target_property = Property.query.get(property_id)

        # Send Status Update Email
        send_email(
            to=target_user.email,
            subject=f'Your Account Status is now: {status_name}',
            template='mail/status_update',
            user=target_user,
            status_name=status_name,
            property_name=target_property.name,
            role_name=target_access.role.name
        )

        return make_response(
            jsonify({'status': 'success', 'message': f'Account status updated to {status_name}.'})), 201

    except Exception as e:
        logging.exception("Error in update_staff_status: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update staff status.'})), 500


# ==========================================
# INVITATION MANAGEMENT ENDPOINTS
# ==========================================

@api.route('/properties/<int:property_id>/invites', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def get_invites(property_id):
    """Returns a list of all pending email invitations for the property."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        invites = PropertyInvite.query.filter_by(property_id=property_id, is_used=False).all()

        invite_list = []
        for invite in invites:
            invite_list.append({
                'id': invite.id,
                'email': invite.email,
                'role_name': invite.role.name,
                'created_at': invite.created_at.isoformat() if invite.created_at else None,
                'invite_code': invite.invite_code
            })

        return make_response(jsonify({'status': 'success', 'data': invite_list})), 201
    except Exception as e:
        logging.exception("Error in get_invites: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch invites.'})), 500


@api.route('/properties/<int:property_id>/invites', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def create_invite(property_id):
    """Generates an invitation code and emails it to the future staff member."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        current_uid = get_current_user()
        current_user = User.query.get(current_uid)

        email = request.json.get('email')
        role_id = request.json.get('role_id')

        role = Role.query.get(role_id)
        target_property = Property.query.get(property_id)

        if not role or not email:
            return make_response(jsonify({'status': 'fail', 'message': 'Email and Role are required.'})), 400

        # Enforce Hierarchy
        current_user_rank = get_user_rank(current_user, property_id)
        target_role_rank = Constants.RoleHierarchy.get(role.name, 0)

        if current_user_rank <= target_role_rank:
            return make_response(
                jsonify({'status': 'fail', 'message': 'Forbidden: Cannot invite roles at or above your level.'})), 403

        invite = PropertyInvite(property_id=property_id, role_id=role.id, email=email)
        db.session.add(invite)
        db.session.commit()

        # Send the Email
        send_email(
            to=email,
            subject=f'You have been invited to join {target_property.name}',
            template='mail/staff_invite',
            property_name=target_property.name,
            role_name=role.name,
            invite_code=invite.invite_code,
            invited_by=current_user.username
        )

        return make_response(jsonify({
            'status': 'success',
            'message': f'Invite sent to {email}.',
            'invite_code': invite.invite_code
        })), 201

    except Exception as e:
        logging.exception("Error in create_invite: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to create invite.'})), 500


@api.route('/properties/<int:property_id>/invites/<int:invite_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def delete_invite(property_id, invite_id):
    """Revokes a pending invitation."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        current_uid = get_current_user()
        current_user = User.query.get(current_uid)

        invite = PropertyInvite.query.filter_by(id=invite_id, property_id=property_id).first()
        if not invite:
            return make_response(jsonify({'status': 'fail', 'message': 'Invite not found.'})), 404

        # Verify hierarchy before allowing deletion
        current_user_rank = get_user_rank(current_user, property_id)
        target_role_rank = Constants.RoleHierarchy.get(invite.role.name, 0)

        if current_user_rank <= target_role_rank:
            return make_response(
                jsonify({'status': 'fail',
                         'message': 'Forbidden: Cannot delete invites for roles at or above your level.'})), 403

        db.session.delete(invite)
        db.session.commit()

        return make_response(jsonify({'status': 'success', 'message': 'Invitation successfully revoked.'})), 201

    except Exception as e:
        logging.exception("Error in delete_invite: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to revoke invite.'})), 500


@api.route('/properties/<int:property_id>/assignable-roles', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_staff')
def get_assignable_roles(property_id):
    """Returns roles from the database that the current user is allowed to assign."""
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        current_uid = get_current_user()
        current_user = User.query.get(current_uid)

        # Get the numeric rank of the logged-in user
        current_user_rank = get_user_rank(current_user, property_id)

        all_roles = Role.query.all()
        assignable_roles = []

        for role in all_roles:
            target_role_rank = Constants.RoleHierarchy.get(role.name, 0)

            # Only return roles strictly below the current user's rank
            # (Change to <= if you want them to assign equals)
            if target_role_rank < current_user_rank:
                assignable_roles.append({
                    'id': role.id,
                    'name': role.name,
                    'description': role.description
                })

        return make_response(jsonify({'status': 'success', 'data': assignable_roles})), 200
    except Exception as e:
        logging.exception("Error in get_assignable_roles: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch roles.'})), 500