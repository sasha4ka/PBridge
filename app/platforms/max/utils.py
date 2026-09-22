from maxapi import Bot
from maxapi.types.attachments import Attachment as MAXAttachment
from maxapi.types.attachments.video import VideoUrl

from app.attachments import Attachment, FileAttachment, URLAttachment
from app.types import AttachmentType

ATTACHMENT_TYPES: dict[str, AttachmentType] = {
    "audio": "audio",
    "image": "photo",
    "video": "video",
    "file": "document",
}


class Utils:
    bot: Bot

    def __init__(self, bot: Bot):
        self.bot = bot

    def get_url(self, video: VideoUrl | None) -> str | None:
        return (
            (
                video.mp4_1080
                or video.mp4_720
                or video.mp4_480
                or video.mp4_360
                or video.mp4_240
                or video.mp4_144
            )
            if video
            else None
        )

    def type_to_global(self, type: str) -> AttachmentType:
        return ATTACHMENT_TYPES[type]

    async def prepare_attachment(
        self, max_attachment: MAXAttachment
    ) -> Attachment | None:
        if max_attachment.type in [
            "sticker",
            "contact",
            "location",
            "inline_keyboard",
            "share",
        ]:
            return None

        if max_attachment.payload is None:
            return None

        url = max_attachment.payload.url  # type: ignore

        if max_attachment.type == "file":
            max_attachment = cast(max_attachment, File)
            attachment = FileAttachment.from_url(
                max_attachment.payload.url, filename=max_attachment
            )

        if max_attachment.type == "video":
            video = await self.bot.get_video(max_attachment.payload.token)  # type: ignore
            url = self.get_url(video.urls)
            if url is None:
                return None

        attachment = URLAttachment(url)  # type: ignore
        attachment.type = self.type_to_global(max_attachment.type)
        return attachment

    def serialize(self, attachment: Attachment) -> str:
        if isinstance(attachment, URLAttachment):
            return f"{attachment.type} - {attachment.url}"
        if isinstance(attachment, FileAttachment):
            return f"{attachment.type} - {attachment.local_path}"
        return "empty attachment"
