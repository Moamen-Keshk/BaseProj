from datetime import datetime, timezone, timedelta
from app.celery_app import celery
from app.api.channel_manager.models import ChannelConnection, ChannelSyncJob
from app.api.models import Property, User  # Adjust imports based on your actual models
from app.api.email import send_email  # Assuming you use this based on your repo structure


@celery.task
def monitor_channel_health():
    """
    Runs periodically (e.g., hourly) to find disconnected channels
    or failed sync jobs and alerts the property owners.
    """
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)

    alerts_by_property = {}

    # --- 1. Detect Persistent Connection Errors ---
    # Find connections explicitly marked as 'error' or where the last error was recent
    # and occurred after the last success.
    error_connections = ChannelConnection.query.filter_by(status='error').all()

    for conn in error_connections:
        prop_id = conn.property_id
        if prop_id not in alerts_by_property:
            alerts_by_property[prop_id] = {"jobs": [], "connections": []}

        alerts_by_property[prop_id]["connections"].append(
            f"{conn.channel_code.upper()} connection is currently offline or unauthorized."
        )

    # --- 2. Detect Failed Sync Jobs in the last hour ---
    # We only look at the last hour so we don't re-alert for old failures.
    recent_failed_jobs = ChannelSyncJob.query.filter(
        ChannelSyncJob.status == 'failed',
        ChannelSyncJob.completed_at >= one_hour_ago
    ).all()

    for job in recent_failed_jobs:
        prop_id = job.property_id
        if prop_id not in alerts_by_property:
            alerts_by_property[prop_id] = {"jobs": [], "connections": []}

        alerts_by_property[prop_id]["jobs"].append(
            f"Failed {job.job_type} for {job.channel_code}. Error: {job.last_error}"
        )

    # --- 3. Dispatch Alerts ---
    alerts_sent = 0
    for property_id, issues in alerts_by_property.items():
        # Get the property and its owner/manager email
        # Adjust this query based on how your User/Property relationship is structured
        prop = Property.query.get(property_id)
        if not prop:
            continue

        # Example: Assuming Property has a backref to an owner or an email field
        owner_email = getattr(prop, 'email', None)
        if not owner_email and hasattr(prop, 'user_id'):
            owner = User.query.get(prop.user_id)
            owner_email = owner.email if owner else None

        if owner_email:
            _send_health_alert_email(owner_email, prop.name, issues)
            alerts_sent += 1

    return {"status": "success", "properties_alerted": alerts_sent}


def _send_health_alert_email(to_email: str, property_name: str, issues: dict):
    """Helper function to format and send the alert email."""

    subject = f"⚠️ Channel Manager Alert for {property_name}"

    # Build a simple text body (You can replace this with an HTML template in your /templates/mail folder)
    body = f"Hello,\n\nWe detected syncing issues with your channels for {property_name}:\n\n"

    if issues["connections"]:
        body += "🔴 Connection Errors:\n"
        for idx, err in enumerate(issues["connections"], 1):
            body += f"  {idx}. {err}\n"
        body += "\n"

    if issues["jobs"]:
        body += "🔴 Failed Synchronization Jobs:\n"
        for idx, err in enumerate(issues["jobs"], 1):
            body += f"  {idx}. {err}\n"

    body += "\nPlease log into your dashboard to check your channel mappings and credentials.\n"

    # Using your existing email module structure
    try:
        send_email(
            to_email,
            subject,
            'mail/channel_alert',  # You will need to create this template if using HTML, or just pass text
            body=body,
            property_name=property_name
        )
    except Exception as e:
        # Log email failure but don't crash the task
        print(f"Failed to send alert email to {to_email}: {str(e)}")