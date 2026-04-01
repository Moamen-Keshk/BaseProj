import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import Property, UserPropertyAccess, Role, User
from .. import db
from app.auth.utils import get_current_user
from app.api.decorators import require_permission


@api.route('/new_property', methods=['POST', 'OPTIONS'], strict_slashes=False)
def new_property():
    """Creates a new property and automatically makes the creator a Property Admin."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    user_uid = get_current_user()
    if user_uid:
        try:
            property_new = Property.from_json(dict(request.json))
            # Optional: If your Property model has a creator_id, you can set it here
            # property_new.creator_id = user_uid

            db.session.add(property_new)
            db.session.flush()  # Flush to generate the property_new.id before committing

            # ---> NEW: AUTOMATICALLY ASSIGN CREATOR AS PROPERTY ADMIN <---
            admin_role = Role.query.filter_by(name='Property Admin').first()
            if admin_role:
                new_access = UserPropertyAccess(
                    user_id=user_uid,
                    property_id=property_new.id,
                    role_id=admin_role.id,
                    account_status_id=2  # Active
                )
                db.session.add(new_access)

            db.session.commit()

            responseObject = {
                'status': 'success',
                'message': 'Property created successfully.',
                'property_id': property_new.id
            }
            return make_response(jsonify(responseObject)), 201

        except Exception as e:
            logging.exception(e)
            db.session.rollback()
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 500

    responseObject = {
        'status': 'fail',
        'message': 'Session expired or invalid token, log in required!'
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/edit_property/<int:property_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')  # <--- NEW: Only Admins can edit property details
def edit_property(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        # The decorator already verified the user is logged in and is a Property Admin.
        property_data = request.get_json()

        # Find the property by ID
        property_to_edit = Property.query.get(property_id)
        if not property_to_edit:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Property not found.'
            })), 404

        # Update property fields
        if 'name' in property_data:
            property_to_edit.name = property_data['name']
        if 'address' in property_data:
            property_to_edit.address = property_data['address']
        if 'status_id' in property_data:
            property_to_edit.status_id = property_data['status_id']

        # Save changes to the database
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Property updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_property: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update property. Please try again.'
        })), 500


@api.route('/all-properties', methods=['GET', 'OPTIONS'], strict_slashes=False)
def all_properties():
    """Returns a list of properties. Super Admins see all, Staff see only assigned properties."""
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    user_uid = get_current_user()
    if user_uid:
        user = User.query.get(user_uid)

        if not user:
            return make_response(jsonify({'status': 'fail', 'message': 'User not found.'})), 404

        # ---> NEW: SECURE THE PROPERTY LIST <---
        if user.is_super_admin:
            # Super Admin gets everything
            properties_list = Property.query.order_by(Property.published_date).all()
        else:
            # Standard user only gets properties they are actively assigned to
            access_records = UserPropertyAccess.query.filter_by(
                user_id=user_uid,
                account_status_id=2  # Must be Active
            ).all()
            property_ids = [access.property_id for access in access_records]

            if not property_ids:
                properties_list = []
            else:
                properties_list = Property.query.filter(
                    Property.id.in_(property_ids)
                ).order_by(Property.published_date).all()

        # Serialize list
        serialized_properties = [prop.to_json() for prop in properties_list]

        responseObject = {
            'status': 'success',
            'data': serialized_properties,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    responseObject = {
        'status': 'fail',
        'message': 'Session expired or invalid token, log in required!'
    }
    return make_response(jsonify(responseObject)), 401