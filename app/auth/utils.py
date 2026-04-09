import logging
from typing import Optional

from flask import request
from firebase_admin.auth import (
    CertificateFetchError,
    ExpiredIdTokenError,
    InvalidIdTokenError,
    RevokedIdTokenError,
    UserDisabledError,
    verify_id_token,
)


logger = logging.getLogger(__name__)


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
    except (
        CertificateFetchError,
        ExpiredIdTokenError,
        InvalidIdTokenError,
        RevokedIdTokenError,
        UserDisabledError,
        ValueError,
    ) as exc:
        logger.exception("Failed to verify Firebase ID token: %s", exc)
        return None
