import asyncio
from typing import cast

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import (
    Command,
)
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InputFileUnion, Message, URLInputFile, Voice
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram_mediagroup_handle import MediaGroup, MediaGroupFilter, MediaGroupObserver
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.abc import BasePlatform
from app.attachments import Attachment, FileAttachment, URLAttachment
from app.message_router import message_router
from app.models import IngoingMessage, OutgoingMessage
from app.types import AttachmentType, MessageType


class TGSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="dev.env", extra="ignore")

    tg_api_token: str
    tg_admin_id: int

    tg_proxy: str | None = None


class Utils:
    api_token: str
    proxy_url: str | None = None
    bot: Bot

    def __init__(self, *, settings: TGSettings, bot: Bot):
        self.api_token = settings.tg_api_token
        self.proxy_url = settings.tg_proxy
        self.bot = bot

    async def download_attachment(
        self, file_id: str, type: AttachmentType, filename: str | None = None
    ) -> FileAttachment | None:
        try:
            file_info = await self.bot.get_file(file_id)
        except TelegramBadRequest:
            return None

        url = f"https://api.telegram.org/file/bot{self.api_token}/{file_info.file_path}"

        attachment = await FileAttachment.from_url(
            url, proxy_url=self.proxy_url, filename=filename
        )
        if attachment:
            attachment.type = type
        return attachment

    def attachment_as_telegram(self, attachment: Attachment) -> InputFileUnion:
        if isinstance(attachment, FileAttachment):
            return FSInputFile(attachment.local_path)
        elif isinstance(attachment, URLAttachment):
            return URLInputFile(attachment.url)
        return FSInputFile("media_stub.gif")


class TGPlatform(BasePlatform):
    def __init__(self, settings: TGSettings | None = None):
        self.settings = settings or TGSettings()  # type: ignore
        session = AiohttpSession(proxy=self.settings.tg_proxy)
        self.bot = Bot(token=self.settings.tg_api_token, session=session)
        self.dispatcher = Dispatcher()
        self.router = Router()
        self.dispatcher.include_router(self.router)

        self.utils = Utils(settings=self.settings, bot=self.bot)

    async def _handle_incoming_message(self, message: Message):
        match message.chat.type:
            case "group" | "private" | "supergroup":
                if message.from_user is None:
                    return
                user_id = message.from_user.id
                user_name = message.from_user.full_name
            case _:
                user_id = None
                user_name = None

        attachments: list[Attachment] = []
        message_type: MessageType = "text"

        if message.photo:
            attachment = await self.utils.download_attachment(
                message.photo[-1].file_id, "photo"
            )
            if attachment:
                attachments = [attachment]
                message_type = "photo"

        elif message.document:
            attachment = await self.utils.download_attachment(
                message.document.file_id,
                "document",
                filename=message.document.file_name,
            )
            if attachment:
                attachments = [attachment]
                message_type = "document"

        elif message.video:
            attachment = await self.utils.download_attachment(
                message.video.file_id,
                "video",
            )
            if attachment:
                attachments = [attachment]
                message_type = "video"

        elif message.audio or message.voice:
            file = cast(Voice, message.audio or message.voice)
            attachment = await self.utils.download_attachment(file.file_id, "audio")
            if attachment:
                attachments = [attachment]
                message_type = "audio"

        await message_router.handle_message(
            IngoingMessage(
                platform="tg",
                text_content=message.text,
                timestamp=message.date,
                chat_id=message.chat.id,
                chat_name=message.chat.full_name,
                user_id=user_id,
                user_name=user_name,
                attachments=attachments,
                message_type=message_type,
            )
        )

    async def _handle_media_group(self, message: Message, media_group: MediaGroup):
        match message.chat.type:
            case "group" | "private" | "supergroup":
                if message.from_user is None:
                    return
                user_id = message.from_user.id
                user_name = message.from_user.full_name
            case _:
                user_id = None
                user_name = None

        attachments: list[Attachment] = []

        for media in media_group.photos:
            attachment = await self.utils.download_attachment(
                media[-1].file_id, "photo"
            )
            if attachment:
                attachments.append(attachment)

        for media in media_group.documents:
            attachment = await self.utils.download_attachment(
                media.file_id, "document", filename=media.file_name
            )
            if attachment:
                attachments.append(attachment)

        for media in media_group.video:
            attachment = await self.utils.download_attachment(media.file_id, "video")
            if attachment:
                attachments.append(attachment)

        for media in media_group.audio:
            attachment = await self.utils.download_attachment(media.file_id, "audio")
            if attachment:
                attachments.append(attachment)

        await message_router.handle_message(
            IngoingMessage(
                platform="tg",
                text_content=message.text,
                timestamp=message.date,
                chat_id=message.chat.id,
                chat_name=message.chat.full_name,
                user_id=user_id,
                user_name=user_name,
                attachments=attachments,
                message_type="media_group",
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

        text = "\n\n".join(blocks)

        match outgoing_message["ingoing_message"]["message_type"]:
            case "text":
                await self.bot.send_message(
                    chat_id=outgoing_message["chat_id"],
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            case "photo":
                attachment = outgoing_message["ingoing_message"]["attachments"][0]

                await self.bot.send_photo(
                    chat_id=outgoing_message["chat_id"],
                    caption=text or None,
                    photo=self.utils.attachment_as_telegram(attachment),
                    parse_mode=ParseMode.HTML,
                )
            case "document":
                attachment = outgoing_message["ingoing_message"]["attachments"][0]

                await self.bot.send_document(
                    chat_id=outgoing_message["chat_id"],
                    caption=text or None,
                    document=self.utils.attachment_as_telegram(attachment),
                    parse_mode=ParseMode.HTML,
                )
            case "video":
                attachment = outgoing_message["ingoing_message"]["attachments"][0]

                await self.bot.send_video(
                    chat_id=outgoing_message["chat_id"],
                    caption=text or None,
                    video=self.utils.attachment_as_telegram(attachment),
                    parse_mode=ParseMode.HTML,
                )
            case "audio":
                attachment = outgoing_message["ingoing_message"]["attachments"][0]

                await self.bot.send_audio(
                    chat_id=outgoing_message["chat_id"],
                    caption=text or None,
                    audio=self.utils.attachment_as_telegram(attachment),
                    parse_mode=ParseMode.HTML,
                )
            case "media_group":
                attachments = outgoing_message["ingoing_message"]["attachments"]
                builder = MediaGroupBuilder(caption=text or None)

                for attachment in attachments:
                    file = self.utils.attachment_as_telegram(attachment)
                    match attachment.type:
                        case "photo":
                            builder.add_photo(file)
                        case "document":
                            builder.add_document(file)
                        case "video":
                            builder.add_video(file)
                        case "audio":
                            builder.add_audio(file)

                await self.bot.send_media_group(
                    chat_id=outgoing_message["chat_id"],
                    media=builder.build(),  # type: ignore
                )

    async def start_handling(self):
        MediaGroupObserver().register(self.dispatcher)

        @self.router.message(Command("start"))
        async def start_command(message: Message):
            if not message.chat.is_direct_messages:
                return
            await message.answer(
                "Telegram bridge is active. Send a message to forward it to the configured destinations."
            )

        @self.router.message(MediaGroupFilter())
        async def handle_group(message: Message, state: FSMContext):
            data = await state.get_data()
            media_group: MediaGroup = data[message.media_group_id]  # type: ignore
            await self._handle_media_group(message, media_group)

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
            await self.dispatcher.start_polling(self.bot, handle_signals=False)  # type: ignore
        except asyncio.CancelledError:
            await self.bot.session.close()
            raise

    async def stop_handling(self):
        await self.bot.session.close()
