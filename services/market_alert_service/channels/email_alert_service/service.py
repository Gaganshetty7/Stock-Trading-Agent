import logging
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Optional

from ...core.notification import NotificationChannel
from ...models.tracking_object import TrackingObject

logger = logging.getLogger(__name__)

class EmailChannel(NotificationChannel):
    def __init__(self, smtp_server: str = "smtp.gmail.com", smtp_port: int = 587):
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port
        self._sender: Optional[str] = None
        self._password: Optional[str] = None
        self._receiver: Optional[str] = None

    def _get_credentials(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if self._sender is None:
            self._sender = os.getenv("EMAIL_SENDER")
        if self._password is None:
            self._password = os.getenv("EMAIL_PASSWORD")
        if self._receiver is None:
            self._receiver = os.getenv("EMAIL_RECEIVER", self._sender)
        return self._sender, self._password, self._receiver

    def _build_message(self, obj: TrackingObject, current_price: float, alert_type: str) -> EmailMessage:
        time_str = datetime.now().strftime("%I:%M %p")

        conditions_block = "\n\n".join(
            f"{i + 1}. {c}" for i, c in enumerate(obj.entry_plan.confirmation_conditions)
        )

        if alert_type == "ENTRY":
            title = "🚨 BUY ZONE REACHED"
            subject = f"🚨 BUY ALERT: {obj.symbol} at ₹{current_price}"
            status_text = "Awaiting Confirmation / Active"
        elif alert_type == "TARGET":
            title = "✅ TARGET 1 HIT!"
            subject = f"✅ TARGET HIT: {obj.symbol} at ₹{current_price}"
            status_text = "Target Achieved"
        elif alert_type == "STOPLOSS":
            title = "⚠️ STOP LOSS HIT!"
            subject = f"⚠️ STOP LOSS HIT: {obj.symbol} at ₹{current_price}"
            status_text = "Trade Invalidated"
        else:
            title = "🔔 STOCK ALERT"
            subject = f"🔔 ALERT: {obj.symbol} at ₹{current_price}"
            status_text = "Update"

        entry_price = getattr(obj, "entry_price", "N/A")

        body = (
            f"{title}\n\n"
            f"Stock:\n{obj.symbol}\n\n"
            f"Time:\n{time_str}\n\n"
            f"Current Price:\n{current_price}\n\n"
            f"Entry Zone Was:\n{obj.entry_plan.buy_zone.min} → {obj.entry_plan.buy_zone.max}\n\n"
            f"Entered At:\n{entry_price}\n\n"
            f"Stoploss:\n{obj.stoploss_plan.hard_stoploss}\n\n"
            f"Targets:\n\n"
            f"T1: {obj.target_plan.target_1}\n\n"
            f"T2: {obj.target_plan.target_2}\n\n"
            f"T3: {obj.target_plan.target_3}\n\n"
            f"Confirmation Conditions:\n\n"
            f"{conditions_block}\n\n"
            f"Status:\n{status_text}"
        )

        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        
        return msg

    def send_alert(self, obj: TrackingObject, current_price: float, alert_type: str = "ENTRY") -> bool:
        sender, password, receiver = self._get_credentials()

        if not sender or not password:
            logger.error(
                "[ALERT] Email credentials missing — "
                "set EMAIL_SENDER and EMAIL_PASSWORD in .env"
            )
            return False

        msg = self._build_message(obj, current_price, alert_type)
        msg['From'] = sender
        msg['To'] = receiver

        try:
            with smtplib.SMTP(self._smtp_server, self._smtp_port, timeout=15) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)

            logger.info(
                f"[{alert_type} ALERT SENT] {obj.symbol} @ ₹{current_price} via Email"
            )
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error(f"[ALERT FAIL] {obj.symbol} via Email — Authentication Failed. Check App Password.")
            return False
            
        except Exception as exc:
            logger.error(f"[ALERT FAIL] {obj.symbol} via Email — sending failed: {exc}")
            return False
