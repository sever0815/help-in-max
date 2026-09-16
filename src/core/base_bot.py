from abc import ABC, abstractmethod
from typing import Any, List, Optional

class BaseBot(ABC):
    @abstractmethod
    async def send_message(self, user_id: str, text: str, reply_markup: Optional[Any] = None):
        """Sends a text message to a specific user."""
        pass

    @abstractmethod
    async def send_keyboard(self, user_id: str, text: str, options: List[str]):
        """Sends a message with a keyboard (options)."""
        pass

    @abstractmethod
    async def on_message_received(self, user_id: str, text: str):
        """Callback for handling incoming messages."""
        pass
