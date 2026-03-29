from flask import make_response, jsonify
from . import api
from app.api.models import User
from app.auth.utils import get_current_user


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
