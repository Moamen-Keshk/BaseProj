import logging
from flask import request, make_response, jsonify
from . import api
from .. import db
from app.api.models import Category
from app.api.decorators import require_active_staff


@api.route('/categories', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def new_category():
    # 1. INSTANT CORS PREFLIGHT APPROVAL
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        category_data = dict(request.json)
        category_new = Category.from_json(category_data)
        db.session.add(category_new)
        db.session.flush()
        db.session.commit()

        return make_response(jsonify({
            'status': 'success',
            'message': 'Category added successfully.'
        })), 201

    except Exception as e:
        logging.exception(e)
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Some error occurred. Please try again.'
        })), 500


@api.route('/categories/<int:category_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def edit_category(category_id):
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        category_data = request.get_json()
        category = db.session.query(Category).filter_by(id=category_id).first()

        if not category:
            return make_response(jsonify({'status': 'fail', 'message': 'Category not found.'})), 404

        if 'name' in category_data:
            category.name = category_data['name']
        if 'capacity' in category_data:
            category.capacity = category_data['capacity']
        if 'description' in category_data:
            category.description = category_data['description']

        db.session.commit()

        return make_response(jsonify({'status': 'success', 'message': 'Category updated.'})), 200

    except Exception as e:
        logging.exception("Error in edit_category: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update category.'})), 500


@api.route('/categories', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_categories():
    """Allows any active staff member to view the global room categories"""
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        # Fetches ALL categories globally
        categories_list = db.session.query(Category).order_by(Category.id).all()
        serialized_categories = [category.to_json() for category in categories_list]

        return make_response(jsonify({
            'status': 'success',
            'data': serialized_categories,
            'page': 0
        })), 200

    except Exception as e:
        logging.exception("Error in all_categories: %s", str(e))
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch categories.'})), 500