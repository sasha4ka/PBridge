import asyncio
from datetime import UTC, datetime

from maxapi import Bot, Dispatcher
from maxapi.enums import ChatType
from maxapi.types import BotStarted, MessageCreated
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.abc import BasePlatform
from app.message_router import message_router
from app.models import IngoingMessage, OutgoingMessage


class MAXSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="dev.env", extra="ignore")

    max_api_token: str
    max_admin_id: int

    max_use_cert: bool = True


class MAXPlatform(BasePlatform):
    def __init__(self, settings: MAXSettings | None = None):
        self.settings = settings or MAXSettings()  # type: ignore
        self.bot = Bot(token=self.settings.max_api_token)
        self.dispatcher = Dispatcher()

    async def _handle_incoming_message(self, event: MessageCreated):
        message = event.message

        if message.sender is None:
            return

        message_content = (message.body.text or "") if message.body else ""
        timestamp = datetime.fromtimestamp(message.timestamp, UTC)

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
            text=outgoing_message["content"],
        )

    async def start_handling(self):
        message_router.register_handler("max", self._send_message)

        @self.dispatcher.bot_started
        async def bot_started(event: BotStarted):
            await self.bot.send_message(
                chat_id=event.chat_id,
                text=f"Привет. Это max2tg bridge. ID чата: {event.chat_id}",
            )

        @self.dispatcher.message_created
        async def default_message(event: MessageCreated):
            await self._handle_incoming_message(event)

        try:
            await self.dispatcher.start_polling(self.bot)
        except asyncio.CancelledError:
            if self.bot.session:
                await self.bot.session.close()
            await self.dispatcher.stop_polling()
            raise
