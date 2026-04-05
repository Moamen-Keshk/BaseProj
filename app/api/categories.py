import logging
from flask import request, make_response, jsonify
from . import api
from app.api.models import Category
from .. import db
from app.api.decorators import require_active_staff


@api.route('/categories', methods=['POST', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def new_category():
    # 👉 FIX: Catch CORS preflight requests before they are processed
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = dict(request.json)
        if not data or 'name' not in data or not data['name'].strip():
            return make_response(jsonify({
                'status': 'fail',
                'message': 'Category name is required.'
            })), 400

        # Safely parse capacity to ensure it is an integer
        try:
            capacity = int(data.get('capacity', 0))
        except (ValueError, TypeError):
            capacity = 0

        # 👉 FIX: Safely handle if description is literally 'null'
        description_raw = data.get('description')
        description = description_raw.strip() if description_raw else ''

        category = Category(
            name=data['name'].strip(),
            description=description,
            capacity=capacity
        )

        db.session.add(category)
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
    # 👉 FIX: Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        data = request.get_json()
        category = db.session.query(Category).filter_by(id=category_id).first()

        if not category:
            return make_response(jsonify({'status': 'fail', 'message': 'Category not found.'})), 404

        if 'name' in data and data['name'] and data['name'].strip():
            category.name = data['name'].strip()

        if 'description' in data:
            description_raw = data['description']
            category.description = description_raw.strip() if description_raw else ''

        if 'capacity' in data:
            try:
                category.capacity = int(data['capacity'])
            except (ValueError, TypeError):
                pass  # Ignore invalid capacity inputs

        db.session.commit()
        return make_response(jsonify({'status': 'success', 'message': 'Category updated successfully.'})), 200

    except Exception as e:
        logging.exception("Error in edit_category: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({'status': 'error', 'message': 'Failed to update category.'})), 500


@api.route('/categories', methods=['GET', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def all_categories():
    # 👉 FIX: Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    """Allows any active staff member to view global categories (Read-Only)"""
    try:
        categories_list = Category.query.order_by(Category.name).all()
        serialized_categories = [category.to_json() for category in categories_list]

        return make_response(jsonify({
            'status': 'success',
            'data': serialized_categories,
            'page': 0
        })), 200

    except Exception as e:
        logging.exception(e)
        return make_response(jsonify({'status': 'error', 'message': 'Failed to fetch categories.'})), 500


@api.route('/categories/<int:category_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@require_active_staff
def delete_category(category_id):
    # 👉 FIX: Catch CORS preflight
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"})), 200

    try:
        category = Category.query.filter_by(id=category_id).first()
        if not category:
            return make_response(jsonify({'status': 'fail', 'message': 'Category not found.'})), 404

        db.session.delete(category)
        db.session.commit()

        return make_response(jsonify({'status': 'success', 'message': 'Category deleted successfully.'})), 200

    except Exception as e:
        logging.exception("An error occurred: %s", str(e))
        db.session.rollback()
        return make_response(jsonify({
            'status': 'error',
            'message': 'Failed to delete category. It might be linked to existing rooms.'
        })), 500