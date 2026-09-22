from datetime import datetime
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.attachments import Attachment
from app.types import MessageType, Platform


class IngoingMessage(TypedDict):
    platform: Platform

    text_content: str | None
    attachments: list[Attachment]
    message_type: MessageType

    timestamp: datetime
    chat_id: int
    chat_name: str | None
    user_id: int | None
    user_name: str | None


class OutgoingMessage(TypedDict):
    ingoing_message: IngoingMessage

    platform: Platform
    chat_id: int

    mark: str
    text_content_style: Literal["quoted", "plain"] | None


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

    text_content_style: Literal["quoted", "plain"] = "plain"

    datemark_format: str = "%d-%m-%Y %H:%M:%S"


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["field"]

    from_rules: list[RuleFrom]
    to_rules: list[RuleTo]

    options: RuleOptions | None = None


class LinkRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["link"]

    chats: list[RuleFrom]

    options: RuleOptions | None = None


type RuleObject = Annotated[FieldRule | LinkRule, Field(discriminator="type")]

rule_adaptor: TypeAdapter[FieldRule | LinkRule] = TypeAdapter(RuleObject)
