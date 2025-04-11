from flask import request, make_response, jsonify
from . import api
import logging
from .. import db
from .models import Category
from app.auth.views import get_current_user

@api.route('/new-category', methods=['POST'])
def new_category():
    resp = get_current_user()
    if isinstance(resp, str):
        try:
            category_new = Category.from_json(dict(request.json))
            db.session.add(category_new)
            db.session.flush()
            db.session.commit()
            responseObject = {
                'status': 'success',
                'message': 'Category added.'
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

@api.route('/edit_category/<int:category_id>', methods=['PUT'])
def edit_category(category_id):
    try:
        # Get the current user ID and ensure they are authorized
        user_id = get_current_user()
        if not isinstance(user_id, str):
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Unauthorized access.'
            })), 401

        # Fetch the booking data from the request
        category_data = request.get_json()

        # Find the booking by ID
        category = db.session.query(Category).filter_by(id=category_id, creator_id=user_id).first()
        if not category:
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Category not found or you do not have permission to edit it.'
            })), 404

        # Update booking fields
        if 'name' in category_data:
            category.name = category_data['name']
        if 'capacity' in category_data:
            category.capacity = category_data['capacity']
        if 'description' in category_data:
            category.description = category_data['description']

        # Additional fields can be updated here
        # ...

        # Save changes to the database
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Category updated successfully.'
        })), 201
    except Exception as e:
        logging.exception("Error in edit_category: %s", str(e))
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to update category. Please try again.'
        })), 500

@api.route('/all-categories')
def all_categories():
    resp = get_current_user()
    if isinstance(resp, str):
        categories_list = Category.query.order_by(Category.id).all()
        for x in categories_list:
            categories_list[categories_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': categories_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 201
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401