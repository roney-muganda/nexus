import logging
from win11toast import toast

logger = logging.getLogger(__name__)

def show_notification(title: str, body: str):
    """
    Displays a native Windows toast notification safely.
    """
    try:
        # win11toast handles threading internally much better
        toast(title, body)
        logger.info(f"Notification shown: {title}")
    except Exception as e:
        logger.error(f"Failed to show notification: {e}")