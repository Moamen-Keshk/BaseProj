import logging
from flask import request, make_response, jsonify
from . import api
from .. import db
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.models import Property, UserPropertyAccess, Role, User, Floor, Amenity


@api.route('/new_property', methods=['POST', 'OPTIONS'], strict_slashes=False)
def new_property():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    user_uid = get_current_user()
    if user_uid:
        try:
            data = request.get_json()

            # 1. Create Basic Property
            property_new = Property.from_json(data)
            db.session.add(property_new)
            db.session.flush()  # Generates property_new.id

            # 2. Assign Amenities (Wizard Step)
            amenity_ids = data.get('amenity_ids', [])
            if amenity_ids:
                amenities = Amenity.query.filter(Amenity.id.in_(amenity_ids)).all()
                property_new.amenities.extend(amenities)

            # 3. Create Floors (Wizard Step)
            floor_numbers = data.get('floors', [])
            for f_num in floor_numbers:
                new_floor = Floor(floor_number=f_num, property_id=property_new.id)
                db.session.add(new_floor)

            # 4. Assign Admin Access
            admin_role = Role.query.filter_by(name='Property Admin').first()
            if admin_role:
                new_access = UserPropertyAccess(
                    user_id=user_uid,
                    property_id=property_new.id,
                    role_id=admin_role.id,
                    account_status_id=2
                )
                db.session.add(new_access)

            db.session.commit()
            return make_response(jsonify({'status': 'success', 'property_id': property_new.id})), 201

        except Exception as e:
            db.session.rollback()
            return make_response(jsonify({'status': 'error', 'message': str(e)})), 500

    return make_response(jsonify({'status': 'fail'})), 401


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
        if 'phone_number' in property_data:  # <--- Added phone_number update logic
            property_to_edit.phone_number = property_data['phone_number']
        if 'email' in property_data:  # <--- Added email update logic
            property_to_edit.email = property_data['email']
        if 'status_id' in property_data:
            property_to_edit.status_id = property_data['status_id']

        # Update amenities relationship
        if 'amenity_ids' in property_data:
            amenities = Amenity.query.filter(Amenity.id.in_(property_data['amenity_ids'])).all()
            property_to_edit.amenities = amenities  # Completely replaces the old list

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
        # Phone and email are handled automatically here by prop.to_json()
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


# Add this to app/api/properties.py

@api.route('/properties/<int:property_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')  # Ensure only Admins can do this
def delete_property(property_id):
    try:
        property_to_delete = Property.query.get(property_id)

        if not property_to_delete:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Property not found.'
            })), 404

        # Because of the cascade="all, delete-orphan" in models.py,
        # deleting the property will automatically delete floors, rooms, bookings, etc.
        db.session.delete(property_to_delete)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Property and all associated data deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error deleting property: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete property. Please try again.'
        })), 500