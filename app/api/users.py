from flask import make_response, jsonify
from . import api
from .models import User
from app.auth.views import token_auth


@api.route('/users')
@token_auth.login_required
def get_user():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        responseObject = {
            'status': 'success',
            'data': user.to_json()
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401
