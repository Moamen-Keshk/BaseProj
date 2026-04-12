import logging
from flask import request, make_response, jsonify
from . import api
from .. import db
from app.auth.utils import get_current_user
from app.api.decorators import require_permission
from app.api.models import Property, UserPropertyAccess, Role, User, Floor, Amenity
from app.api.utils.property_setup import normalize_property_payload


def _can_create_property(user):
    if user is None:
        return False

    if user.is_super_admin:
        return True

    active_accesses = UserPropertyAccess.query.filter_by(
        user_id=user.uid,
        account_status_id=2,
    ).all()
    if not active_accesses:
        return True

    return any(access.role and access.role.name == 'Property Admin' for access in active_accesses)


def _serialize_property(property_record):
    return property_record.to_json()


def _validate_amenities(amenity_ids):
    if not amenity_ids:
        return []

    amenities = Amenity.query.filter(Amenity.id.in_(amenity_ids)).all()
    found_ids = {amenity.id for amenity in amenities}
    missing_ids = [amenity_id for amenity_id in amenity_ids if amenity_id not in found_ids]
    if missing_ids:
        raise ValueError(f'Invalid amenity IDs: {missing_ids}')
    return amenities


@api.route('/new_property', methods=['POST', 'OPTIONS'], strict_slashes=False)
@api.route('/properties', methods=['POST', 'OPTIONS'], strict_slashes=False)
def new_property():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    user_uid = get_current_user()
    if user_uid:
        try:
            user = User.query.get(user_uid)
            if not user:
                return make_response(jsonify({'status': 'fail', 'message': 'User not found.'})), 404
            if not _can_create_property(user):
                return make_response(jsonify({
                    'status': 'fail',
                    'message': 'You do not have permission to create another property.'
                })), 403

            data = request.get_json() or {}
            normalized = normalize_property_payload(data)

            # 1. Create Basic Property
            property_new = Property.from_json(normalized)
            db.session.add(property_new)
            db.session.flush()  # Generates property_new.id

            # 2. Assign Amenities (Wizard Step)
            amenities = _validate_amenities(normalized.get('amenity_ids', []))
            if amenities:
                property_new.amenities.extend(amenities)

            # 3. Create Floors (Wizard Step)
            floor_numbers = normalized.get('floors', [])
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
            return make_response(jsonify({
                'status': 'success',
                'property_id': property_new.id,
                'data': _serialize_property(property_new),
            })), 201

        except ValueError as e:
            db.session.rollback()
            return make_response(jsonify({'status': 'fail', 'message': str(e)})), 400
        except Exception as e:
            logging.exception("Error in new_property: %s", str(e))
            db.session.rollback()
            return make_response(jsonify({'status': 'error', 'message': str(e)})), 500

    return make_response(jsonify({'status': 'fail'})), 401


@api.route('/edit_property/<int:property_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@api.route('/properties/<int:property_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_permission('manage_property')  # <--- NEW: Only Admins can edit property details
def edit_property(property_id):
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        # The decorator already verified the user is logged in and is a Property Admin.
        property_data = request.get_json() or {}
        normalized = normalize_property_payload(property_data, partial=True)

        # Find the property by ID
        property_to_edit = Property.query.get(property_id)
        if not property_to_edit:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Property not found.'
            })), 404

        # Update property fields
        for field in [
            'name',
            'address',
            'phone_number',
            'email',
            'status_id',
            'timezone',
            'currency',
            'tax_rate',
            'default_check_in_time',
            'default_check_out_time',
        ]:
            if field in normalized:
                setattr(property_to_edit, field, normalized[field])

        # Update amenities relationship
        if 'amenity_ids' in normalized:
            amenities = _validate_amenities(normalized['amenity_ids'])
            property_to_edit.amenities = amenities  # Completely replaces the old list

        # Save changes to the database
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Property updated successfully.',
            'data': _serialize_property(property_to_edit),
        })), 200

    except ValueError as e:
        logging.exception("Validation error in edit_property: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'fail',
            'message': str(e)
        })), 400
    except Exception as e:
        logging.exception("Error in edit_property: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update property. Please try again.'
        })), 500


@api.route('/all-properties', methods=['GET', 'OPTIONS'], strict_slashes=False)
@api.route('/properties', methods=['GET', 'OPTIONS'], strict_slashes=False)
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


@api.route('/properties/<int:property_id>', methods=['GET', 'OPTIONS'], strict_slashes=False)
def get_property(property_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    user_uid = get_current_user()
    if not user_uid:
        return make_response(jsonify({'status': 'fail', 'message': 'Session expired or invalid token, log in required!'})), 401

    user = User.query.get(user_uid)
    if not user:
        return make_response(jsonify({'status': 'fail', 'message': 'User not found.'})), 404

    property_record = Property.query.get(property_id)
    if not property_record:
        return make_response(jsonify({'status': 'fail', 'message': 'Property not found.'})), 404

    if not user.is_super_admin:
        access = UserPropertyAccess.query.filter_by(
            user_id=user_uid,
            property_id=property_id,
            account_status_id=2,
        ).first()
        if not access:
            return make_response(jsonify({'status': 'fail', 'message': 'Access denied.'})), 403

    return make_response(jsonify({
        'status': 'success',
        'data': _serialize_property(property_record),
    })), 200


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
