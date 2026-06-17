import logging
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Optional

from ..models.tracking_object import TrackingObject

logger = logging.getLogger(__name__)

# ── Config (loaded from environment) ─────────────────────────────────────────
_EMAIL_SENDER: Optional[str] = None
_EMAIL_PASSWORD: Optional[str] = None
_EMAIL_RECEIVER: Optional[str] = None
_SMTP_SERVER = "smtp.gmail.com"
_SMTP_PORT = 587


def _get_credentials() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Lazy-load credentials from env on first use."""
    global _EMAIL_SENDER, _EMAIL_PASSWORD, _EMAIL_RECEIVER
    if _EMAIL_SENDER is None:
        _EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    if _EMAIL_PASSWORD is None:
        _EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    if _EMAIL_RECEIVER is None:
        # Default to sending it to the sender if not separately defined
        _EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", _EMAIL_SENDER)
    return _EMAIL_SENDER, _EMAIL_PASSWORD, _EMAIL_RECEIVER


# ── Message builder ───────────────────────────────────────────────────────────

def _build_message(obj: TrackingObject, current_price: float) -> EmailMessage:
    time_str = datetime.now().strftime("%I:%M %p")

    conditions_block = "\n\n".join(
        f"{i + 1}. {c}" for i, c in enumerate(obj.entry_plan.confirmation_conditions)
    )

    body = (
        f"🚨 BUY ZONE REACHED\n\n"
        f"Stock:\n{obj.symbol}\n\n"
        f"Time:\n{time_str}\n\n"
        f"Current Price:\n{current_price}\n\n"
        f"Buy Zone:\n{obj.entry_plan.buy_zone.min} → {obj.entry_plan.buy_zone.max}\n\n"
        f"Stoploss:\n{obj.stoploss_plan.hard_stoploss}\n\n"
        f"Targets:\n\n"
        f"T1: {obj.target_plan.target_1}\n\n"
        f"T2: {obj.target_plan.target_2}\n\n"
        f"T3: {obj.target_plan.target_3}\n\n"
        f"Confirmation Conditions:\n\n"
        f"{conditions_block}\n\n"
        f"Status:\nAwaiting Confirmation"
    )

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = f"🚨 BUY ALERT: {obj.symbol} at ₹{current_price}"
    
    return msg


# ── Transport ─────────────────────────────────────────────────────────────────

def send_alert(obj: TrackingObject, current_price: float) -> bool:
    """
    Build and dispatch an Email message.
    Returns True on success, False on any failure.
    Guaranteed to never raise — callers need not wrap in try/except.
    """
    sender, password, receiver = _get_credentials()

    if not sender or not password:
        logger.error(
            "[ALERT] Email credentials missing — "
            "set EMAIL_SENDER and EMAIL_PASSWORD in .env"
        )
        return False

    msg = _build_message(obj, current_price)
    msg['From'] = sender
    msg['To'] = receiver

    try:
        # Use simple SMTP with STARTTLS for Gmail compatibility
        with smtplib.SMTP(_SMTP_SERVER, _SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        logger.info(
            f"[ALERT SENT] {obj.symbol} @ ₹{current_price}  "
            f"zone=₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}"
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(f"[ALERT FAIL] {obj.symbol} — Email Authentication Failed."
                     " Check App Password.")
        return False
        
    except Exception as exc:
        logger.error(f"[ALERT FAIL] {obj.symbol} — Email sending failed: {exc}")
        return False
