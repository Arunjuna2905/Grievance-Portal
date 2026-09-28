import logging

logger = logging.getLogger(__name__)


def notify_new_grievance(complaint: dict):
    """Placeholder for new grievance notifications."""
    logger.info("New grievance created: %s", complaint.get("reference"))
    return []


def notify_status_change(citizen: dict, complaint: dict, status: str, message: str):
    """Placeholder for status change notifications."""
    logger.info("Status change for complaint %s to %s", complaint.get("reference"), status)
    return []
