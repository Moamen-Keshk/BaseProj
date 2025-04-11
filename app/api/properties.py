from flask import request, make_response, jsonify
from . import api
import logging
from .models import Property
from .. import db
from app.auth.views import get_current_user

@api.route('/new_property', methods=['POST'])
def new_property():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            property_new = Property.from_json(dict(request.json))
            db.session.add(property_new)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Property submitted.'
            }
            return make_response(jsonify(responseObject)), 201
        except Exception as e:
            logging.exception(e)
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'expired',
        'message': 'Session expired, log in required!'
    }
    return make_response(jsonify(responseObject)), 202

@api.route('/edit_property/<int:property_id>', methods=['PUT'])
def edit_property(property_id):
    try:
        # Get the current user ID and ensure they are authorized
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        # Fetch the booking data from the request
        property_data = request.get_json()

        # Find the booking by ID
        property_to_edit = db.session.query(Property).filter_by(id=property_id, creator_id=user_id).first()
        if not property_to_edit:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Booking not found or you do not have permission to edit it.'
            })), 404

        # Update booking fields
        if 'name' in property_data:
            property_to_edit.name = property_data['name']
        if 'address' in property_data:
            property_to_edit.address = property_data['address']
        if 'status_id' in property_data:
            property_to_edit.status_id = property_data['status_id']

        # Additional fields can be updated here
        # ...

        # Save changes to the database
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Floor updated successfully.'
        })), 201

    except Exception as e:
        logging.exception("Error in edit_floor: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update floor. Please try again.'
        })), 500

@api.route('/all-properties')
def all_properties():
    resp = get_current_user()
    if isinstance(resp, str):
        properties_list = Property.query.order_by(Property.published_date).all()
        for x in properties_list:
            properties_list[properties_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': properties_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401