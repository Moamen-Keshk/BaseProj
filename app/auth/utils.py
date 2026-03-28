import logging
from typing import Optional

from flask import request
from firebase_admin.auth import verify_id_token


def get_current_user() -> Optional[str]:
    if "Authorization" not in request.headers:
        return None

    authorization = request.headers["Authorization"]

    if not authorization.startswith("Bearer "):
        return None

    token = authorization.split("Bearer ")[1]

    try:
        result = verify_id_token(token, clock_skew_seconds=10)
        return result["uid"]
    except Exception as e:
        logging.exception(e)
        return None