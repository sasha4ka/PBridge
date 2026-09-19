from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict

from app.types import Platform


class IngoingMessage(TypedDict):
    platform: Platform
    content: str
    timestamp: datetime
    chat_id: int
    chat_name: str | None
    user_id: int | None
    user_name: str | None


class OutgoingMessage(TypedDict):
    content: str
    mark: str
    platform: Platform
    chat_id: int


class RuleFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform
    chat_id: int
    users: list[int] | None = None

    def match(self, message: IngoingMessage) -> bool:
        if message["platform"] != self.platform:
            return False
        if message["chat_id"] != self.chat_id:
            return False
        if not self.users:
            return True
        return message["user_id"] in self.users


class RuleTo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform
    chat_id: int


class RuleOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_mark: (
        list[
            Literal[
                "datemark", "user_id", "user_name", "chat_id", "chat_name", "platform"
            ]
        ]
        | None
    ) = None

    datemark_format: str = "%d-%m-%Y %H:%M:%S"


class RuleObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_rules: list[RuleFrom]
    to_rules: list[RuleTo]
    options: RuleOptions | None = None
