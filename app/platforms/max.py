import asyncio
import logging
from datetime import UTC, datetime

from maxapi import Bot, Dispatcher
from maxapi.enums import ChatType
from maxapi.types import BotAdded, BotStarted, MessageCreated
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.abc import BasePlatform
from app.message_router import message_router
from app.models import IngoingMessage, OutgoingMessage

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

    async def _incoming_message_handler(self, event: MessageCreated):
        message = event.message

        if message.sender is None:
            return

        message_content = (message.body.text or "") if message.body else ""
        timestamp = datetime.fromtimestamp(message.timestamp / 1000, UTC)

        chat_name: str = "Direct"

        if message.recipient.chat_type == ChatType.CHAT:
            chat = await self.bot.get_chat_by_id(message.recipient.chat_id or 0)
            chat_name = chat.title or "Unknown chat"

        await message_router.handle_message(
            IngoingMessage(
                platform="max",
                content=message_content,
                timestamp=timestamp,
                chat_id=message.recipient.chat_id or message.recipient.user_id or 0,
                chat_name=chat_name,
                user_id=message.sender.user_id,
                user_name=message.sender.full_name,
            )
        )

    async def _send_message(self, outgoing_message: OutgoingMessage):
        await self.bot.send_message(
            chat_id=outgoing_message["chat_id"],
            text=outgoing_message["content"] + outgoing_message["mark"],
        )

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

        self.dispatcher.bot_started.register(self._bot_started_handler)

        self.dispatcher.message_created.register(self._incoming_message_handler)

        if self.settings.max_admin_id is not None:
            self.dispatcher.bot_added.register(self._bot_added_to_group_handler)

        try:
            await self.dispatcher.start_polling(self.bot)
        except asyncio.CancelledError:
            if self.bot.session:
                await self.bot.session.close()
            await self.dispatcher.stop_polling()
            raise
