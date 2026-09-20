import asyncio

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import (
    Command,
)
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
        match message.chat.type:
            case "group" | "private" | "supergroup":
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
                        attachments=None,
                    )
                )
            case "channel":
                await message_router.handle_message(
                    IngoingMessage(
                        platform="tg",
                        content=message.text or "",
                        timestamp=message.date,
                        chat_id=message.chat.id,
                        chat_name=message.chat.full_name,
                        user_id=None,
                        user_name=None,
                        attachments=None,
                    )
                )
            case _:
                pass

    async def _send_message(self, outgoing_message: OutgoingMessage):
        if outgoing_message["mark"]:
            text = f"{outgoing_message['content']}\n\n{outgoing_message['mark']}"
        else:
            text = outgoing_message["content"]

        if outgoing_message.get("text_content_style") == "quoted":
            text = f"<blockquote>{outgoing_message['content']}</blockquote>{outgoing_message['mark']}"

        await self.bot.send_message(
            chat_id=outgoing_message["chat_id"],
            text=text,
            parse_mode=ParseMode.HTML,
        )

    async def start_handling(self):
        @self.router.message(Command("start"))
        async def start_command(message: Message):
            if not message.chat.is_direct_messages:
                return
            await message.answer(
                "Telegram bridge is active. Send a message to forward it to the configured destinations."
            )

        @self.router.message()
        async def default_message(message: Message):
            await self._handle_incoming_message(message)

        @self.router.channel_post()
        async def channel_post(message: Message):
            await self._handle_incoming_message(message)

        @self.dispatcher.message(Command("reload_rules"))
        async def reload_rules(message: Message):
            if message.from_user and message.from_user.id == self.settings.tg_admin_id:
                took = message_router.load_rules()
                await message.answer(
                    f"Reload took {took:.3f}s, number of rules: {len(message_router.rules or [])}"
                )

        message_router.register_handler("tg", self._send_message)

        try:
            await self.dispatcher.start_polling(self.bot)  # type: ignore
        except asyncio.CancelledError:
            await self.bot.session.close()
            await self.dispatcher.stop_polling()
            raise

    async def stop_handling(self):
        await self.bot.session.close()
