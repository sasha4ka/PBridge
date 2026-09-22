import asyncio
import logging
from datetime import UTC, datetime

from maxapi import Bot, Dispatcher
from maxapi.enums import ChatType
from maxapi.types import BotAdded, BotStarted, MessageCreated
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.abc import BasePlatform
from app.attachments import Attachment
from app.message_router import message_router
from app.models import IngoingMessage, OutgoingMessage
from app.platforms.max.utils import Utils
from app.types import MessageType

logging.getLogger("dispatcher").setLevel(logging.ERROR)


class MAXSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="dev.env", extra="ignore")

    max_api_token: str
    max_admin_id: int | None = None


class MAXPlatform(BasePlatform):
    def __init__(self, settings: MAXSettings | None = None):
        self.settings = settings or MAXSettings()  # type: ignore
        self.bot = Bot(token=self.settings.max_api_token)
        self.dispatcher = Dispatcher()
        self.utils = Utils(self.bot)

    async def _incoming_message_handler(self, event: MessageCreated):
        message = event.message

        if message.sender is None:
            user_id = None
            user_name = None
        else:
            user_id = message.sender.user_id
            user_name = message.sender.full_name

        if not message.body:
            return

        text_content = message.body.text
        timestamp = datetime.fromtimestamp(message.timestamp / 1000, UTC)

        chat_name: str = "Direct"

        if message.recipient.chat_type != ChatType.DIALOG:
            chat = await self.bot.get_chat_by_id(message.recipient.chat_id or 0)
            chat_name = chat.title or "Unknown chat"

        attachments: list[Attachment] = []

        if message.body.attachments:
            for max_atch in message.body.attachments:
                attachment = await self.utils.prepare_attachment(max_atch)
                if attachment is None:
                    continue
                attachments.append(attachment)

        message_type: MessageType = "text"

        if len(attachments) == 1:
            match attachments[0].type:
                case "photo":
                    message_type = "photo"
                case "audio":
                    message_type = "audio"
                case "document":
                    message_type = "document"
                case "video":
                    message_type = "video"
        if len(attachments) > 1:
            message_type = "media_group"

        await message_router.handle_message(
            IngoingMessage(
                platform="max",
                text_content=text_content,
                attachments=attachments,
                message_type=message_type,
                timestamp=timestamp,
                chat_id=message.recipient.chat_id or 0,
                chat_name=chat_name,
                user_id=user_id,
                user_name=user_name,
            )
        )

    async def _send_message(self, outgoing_message: OutgoingMessage):
        blocks: list[str] = []

        if outgoing_message["ingoing_message"]["text_content"]:
            blocks.append(
                f"<blockquote>{outgoing_message['ingoing_message']['text_content']}</blockquote>"
                if outgoing_message["text_content_style"] == "quoted"
                else outgoing_message["ingoing_message"]["text_content"]
            )
        if outgoing_message["mark"]:
            blocks.append(outgoing_message["mark"])
        if outgoing_message["ingoing_message"]["message_type"] != "text":
            blocks.append(
                "\n".join(
                    [
                        self.utils.serialize(attachment)
                        for attachment in outgoing_message["ingoing_message"][
                            "attachments"
                        ]
                    ]
                )
            )

        text = "\n\n".join(blocks)
        await self.bot.send_message(chat_id=outgoing_message["chat_id"], text=text)

    async def _bot_started_handler(self, event: BotStarted):
        await self.bot.send_message(
            chat_id=event.chat_id,
            text=f"Привет. Это max2tg bridge. ID чата: {event.chat_id}",
        )

    async def _bot_added_to_group_handler(self, event: BotAdded):
        if event.chat is None:
            return

        text: str

        match event.chat.type:
            case ChatType.CHANNEL:
                text = f"New channel (wip): {event.chat_id}"
            case ChatType.CHAT:
                text = f"New group: {event.chat_id}"
            case ChatType.DIALOG:
                text = f"New direct: {event.chat_id}"

        await self.bot.send_message(chat_id=self.settings.max_admin_id, text=text)

    async def start_handling(self):
        message_router.register_handler("max", self._send_message)

        self.dispatcher.bot_started.register(self._bot_started_handler)  # type: ignore

        self.dispatcher.message_created.register(self._incoming_message_handler)  # type: ignore

        if self.settings.max_admin_id is not None:
            self.dispatcher.bot_added.register(self._bot_added_to_group_handler)  # type: ignore

        try:
            await self.dispatcher.start_polling(self.bot)
        except asyncio.CancelledError:
            await self.dispatcher.stop_polling()
            if self.bot.session:
                await self.bot.session.close()
            raise
