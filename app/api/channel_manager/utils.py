from models import OTASyncLog
from app import db  # Make sure this imports your SQLAlchemy session

def log_sync_status(ota_name: str, sync_type: str, status: str, message: str = None):
    """
    Records a sync attempt (success or error) in OTASyncLog.
    :param ota_name: e.g., 'booking.com'
    :param sync_type: 'booking', 'rate', 'availability'
    :param status: 'success', 'error'
    :param message: Optional message or error string
    """
    log = OTASyncLog(
        ota_name=ota_name,
        sync_type=sync_type,
        status=status,
        message=message
    )
    db.session.add(log)
    db.session.commit()
