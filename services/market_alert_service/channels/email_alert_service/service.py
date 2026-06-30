import logging
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Optional

from ...core.notification import NotificationChannel
from db.models.trade_tracking import TradeTracking

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

    def _build_message(self, trade: TradeTracking, current_price: float, alert_type: str, buying_price: float = None) -> EmailMessage:
        time_str = datetime.now().strftime("%I:%M %p")

        conditions = trade.confirmation_conditions or []
        conditions_block = "\n\n".join(
            f"{i + 1}. {c}" for i, c in enumerate(conditions)
        )

        p_l_block = ""
        if alert_type in ("TARGET", "STOPLOSS", "MARKET_CLOSED") and buying_price:
            diff = current_price - buying_price
            pct = (diff / buying_price * 100) if buying_price else 0.0
            rupee_change = f"+₹{diff:.2f}" if diff >= 0 else f"-₹{abs(diff):.2f}"
            pct_change = f"+{pct:.2f}%" if pct >= 0 else f"-{abs(pct):.2f}%"
            p_l_block = (
                f"Buying Price:\n{buying_price}\n\n"
                f"Selling Price:\n{current_price}\n\n"
                f"Change:\n{rupee_change} ({pct_change})\n\n"
            )

        if alert_type == "ENTRY":
            title = "🚨 BUY ZONE REACHED"
            subject = f"🚨 BUY ALERT: {trade.symbol} at ₹{current_price}"
            status_text = "Awaiting Confirmation / Active"
        elif alert_type == "TARGET":
            title = "✅ TARGET 1 HIT!"
            subject = f"✅ TARGET HIT: {trade.symbol} at ₹{current_price}"
            status_text = "Target Achieved"
        elif alert_type == "STOPLOSS":
            title = "⚠️ STOP LOSS HIT!"
            subject = f"⚠️ STOP LOSS HIT: {trade.symbol} at ₹{current_price}"
            status_text = "Trade Invalidated"
        elif alert_type == "MARKET_CLOSED":
            title = "🛑 TRADE EXITED (MARKET CLOSE)"
            subject = f"🛑 MARKET CLOSE: {trade.symbol} at ₹{current_price}"
            status_text = "Market Closed"
        else:
            title = "🔔 STOCK ALERT"
            subject = f"🔔 ALERT: {trade.symbol} at ₹{current_price}"
            status_text = "Update"

        entry_price = trade.entry_price or "N/A"

        body = f"{title}\n\n"
        body += f"Stock:\n{trade.symbol}\n\n"
        body += f"Time:\n{time_str}\n\n"

        if p_l_block:
            body += p_l_block
        else:
            body += (
                f"Current Price:\n{current_price}\n\n"
                f"Entry Zone Was:\n{trade.buy_zone_min} → {trade.buy_zone_max}\n\n"
                f"Entered At:\n{entry_price}\n\n"
            )

        body += (
            f"Stoploss:\n{trade.hard_stoploss}\n\n"
            f"Targets:\n\n"
            f"T1: {trade.target_1}\n\n"
            f"T2: {trade.target_2}\n\n"
            f"T3: {trade.target_3}\n\n"
            f"Confirmation Conditions:\n\n"
            f"{conditions_block}\n\n"
            f"Status:\n{status_text}"
        )

        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        
        return msg

    def send_alert(self, trade: TradeTracking, current_price: float, alert_type: str = "ENTRY", buying_price: float = None) -> Optional[str]:
        sender, password, receiver = self._get_credentials()

        if not sender or not password:
            logger.error(
                "[ALERT] Email credentials missing — "
                "set EMAIL_SENDER and EMAIL_PASSWORD in .env"
            )
            return None

        msg = self._build_message(trade, current_price, alert_type, buying_price)
        msg['From'] = sender
        msg['To'] = receiver

        try:
            with smtplib.SMTP(self._smtp_server, self._smtp_port, timeout=15) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)

            logger.info(
                f"[{alert_type} ALERT SENT] {trade.symbol} @ ₹{current_price} via Email"
            )
            return "email_sent"

        except smtplib.SMTPAuthenticationError:
            logger.error(f"[ALERT FAIL] {trade.symbol} via Email — Authentication Failed. Check App Password.")
            return None
            
        except Exception as exc:
            logger.error(f"[ALERT FAIL] {trade.symbol} via Email — sending failed: {exc}")
            return None
