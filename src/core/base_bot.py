from abc import ABC, abstractmethod
from typing import Any, List, Optional

class BaseBot(ABC):
    @abstractmethod
    async def send_message(self, user_id: str, text: str, reply_markup: Optional[Any] = None):
        """Sends a text message to a specific user."""
        pass

    @abstractmethod
    async def send_keyboard(self, user_id: str, text: str, options: List[str]) -> int:
        """Sends a message with a keyboard (options) and returns message ID."""
        pass

    @abstractmethod
    async def edit_message(self, user_id: str, message_id: int, text: str, reply_markup=None):
        """Edits an existing message."""
        pass
