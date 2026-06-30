from abc import ABC, abstractmethod
from typing import Optional

from db.models.trade_tracking import TradeTracking


class NotificationChannel(ABC):
    """
    Abstract base class for all notification channels.
    Channels are responsible for transforming and delivering the alert.
    """

    @abstractmethod
    def send_alert(self, trade: TradeTracking, current_price: float, alert_type: str = "ENTRY", buying_price: float = None) -> Optional[str]:
        """
        Send an alert for the given trade tracking row.

        Args:
            trade: The TradeTracking ORM object from the database.
            current_price: The live market price that triggered the alert.
            alert_type: One of "ENTRY", "TARGET", "STOPLOSS".

        Returns:
            The external message ID (e.g. Telegram message_id) on success,
            or None if the alert could not be delivered.
            Channels that don't produce a message ID should return a
            non-None sentinel (e.g. "email_sent") on success.
        """
        pass
