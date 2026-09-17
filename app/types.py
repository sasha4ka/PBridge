from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models import OutgoingMessage

type Platform = Literal["max", "tg"]
type Handler = Callable[[OutgoingMessage], Awaitable[None]]
