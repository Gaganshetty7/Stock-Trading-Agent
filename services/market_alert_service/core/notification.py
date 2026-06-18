from abc import ABC, abstractmethod

from ..models.tracking_object import TrackingObject


class NotificationChannel(ABC):
    """
    Abstract base class for all notification channels.
    Channels are responsible for transforming and delivering the alert.
    """

    @abstractmethod
    def send_alert(self, obj: TrackingObject, current_price: float, alert_type: str = "ENTRY") -> bool:
        """
        Send an alert for the given tracking object.
        Returns True if successful, False otherwise.
        Must not raise exceptions.
        """
        pass
