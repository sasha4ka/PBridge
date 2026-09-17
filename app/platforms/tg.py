import asyncio

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import Message
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.abc import BasePlatform
from app.message_router import message_router
from app.models import IngoingMessage, OutgoingMessage


class TGSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="dev.env", extra="ignore")

    tg_api_token: str
    tg_admin_id: int

    tg_proxy: str | None = None


class TGPlatform(BasePlatform):
    def __init__(self, settings: TGSettings | None = None):
        self.settings = settings or TGSettings()  # type: ignore
        session = AiohttpSession(proxy=self.settings.tg_proxy)
        self.bot = Bot(token=self.settings.tg_api_token, session=session)
        self.dispatcher = Dispatcher()
        self.router = Router()
        self.dispatcher.include_router(self.router)

    async def _handle_incoming_message(self, message: Message):
        if message.from_user is None:
            return

        await message_router.handle_message(
            IngoingMessage(
                platform="tg",
                content=message.text or "",
                timestamp=message.date,
                chat_id=message.chat.id,
                chat_name=message.chat.full_name,
                user_id=message.from_user.id,
                user_name=message.from_user.username,
            )
        )

    async def _send_message(self, outgoing_message: OutgoingMessage):
        await self.bot.send_message(
            chat_id=outgoing_message["chat_id"],
            text=outgoing_message["content"],
        )

    async def start_handling(self):
        @self.router.message(Command("start"))
        async def start_command(message: Message):
            await message.answer(
                "Telegram bridge is active. Send a message to forward it to the configured destinations."
            )

        @self.router.message()
        async def default_message(message: Message):
            await self._handle_incoming_message(message)

        message_router.register_handler("tg", self._send_message)

        try:
            await self.dispatcher.start_polling(self.bot)  # type: ignore
        except asyncio.CancelledError:
            await self.bot.session.close()
            await self.dispatcher.stop_polling()
            raise

    async def stop_handling(self):
        await self.bot.session.close()
