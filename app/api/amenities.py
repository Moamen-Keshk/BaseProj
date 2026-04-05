import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import Amenity
from .. import db
from app.api.decorators import require_active_staff


@api.route('/amenities', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def new_amenity():
    try:
        data = dict(request.json)

        if not data or 'name' not in data or not data['name'].strip():
            responseObject = {
                'status': 'fail',
                'message': 'Amenity name is required.'
            }
            return make_response(jsonify(responseObject)), 400

        amenity = Amenity(
            name=data['name'].strip(),
            icon=data.get('icon')
        )

        db.session.add(amenity)
        db.session.flush()
        db.session.commit()

        responseObject = {
            'status': 'success',
            'message': 'Amenity added successfully.'
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


@api.route('/amenities/<int:amenity_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def edit_amenity(amenity_id):
    try:
        data = request.get_json()

        # Find the amenity by ID
        amenity = db.session.query(Amenity).filter_by(id=amenity_id).first()
        if not amenity:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Amenity not found.'
            })), 404

        # Update amenity fields
        if 'name' in data and data['name'].strip():
            amenity.name = data['name'].strip()
        if 'icon' in data:
            amenity.icon = data['icon']

        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Amenity updated successfully.'
        })), 200

    except Exception as e:
        logging.exception("Error in edit_amenity: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update amenity. Please try again.'
        })), 500


@api.route('/amenities', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_amenities():
    """Allows any active staff member to view the global amenities (Read-Only)"""
    try:
        amenities_list = Amenity.query.order_by(Amenity.name).all()

        serialized_amenities = [amenity.to_json() for amenity in amenities_list]

        responseObject = {
            'status': 'success',
            'data': serialized_amenities,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200

    except Exception as e:
        logging.exception(e)
        responseObject = {
            'status': 'error',
            'message': 'Failed to fetch amenities.'
        }
        return make_response(jsonify(responseObject)), 500


@api.route('/amenities/<int:amenity_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def delete_amenity(amenity_id):
    try:
        amenity = Amenity.query.filter_by(id=amenity_id).first()

        if not amenity:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Amenity not found.'
            })), 404

        db.session.delete(amenity)
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Amenity deleted successfully.'
        })), 200

    except Exception as e:
        logging.exception("An error occurred: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete amenity. Please try again.'
        })), 500