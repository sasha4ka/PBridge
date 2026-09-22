import io
import logging
import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import aiohttp

from app.exc import DownloadError
from app.types import AttachmentType

logger = logging.getLogger("Attachments")
logger.setLevel(logging.DEBUG)


async def _download_file(url: str, path: Path, proxy_url: str | None = None):
    async with (
        aiohttp.ClientSession(proxy=proxy_url) as session,
        session.get(url) as response,
    ):
        if response.status == 200:
            with open(path, "wb") as f:  # noqa
                while True:
                    chunk = await response.content.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        else:
            raise DownloadError(f"Failed to download {url}")


class Attachment:
    type: AttachmentType


class URLAttachment(Attachment):
    url: str

    def __init__(self, url: str):
        self.url = url


class FileAttachment(Attachment):
    local_path: Path

    def __init__(self, local_path: str | Path):
        self.local_path = Path(local_path)

    @staticmethod
    async def from_url(
        url: str, filename: str | None = None, proxy_url: str | None = None
    ):
        attachments_directory = Path("attachments")

        if not Path.exists(attachments_directory):
            os.mkdir(attachments_directory)

        filename = filename or str(uuid.uuid1())
        path = Path.joinpath(attachments_directory, filename)

        try:
            await _download_file(url, path, proxy_url=proxy_url)
            logger.info(f"Successfully downloaded file: {url} to {path}")
            return FileAttachment(path)
        except DownloadError:
            logger.warning(f"Failed to download: {id} - {url}")

    @contextmanager
    def open(self) -> Generator[io.BufferedReader | None]:
        with open(self.local_path, "rb") as f:
            yield f

        return

    def __del__(self):
        if not Path.exists(self.local_path):
            return

        try:
            os.remove(self.local_path)
        except Exception:
            logger.exception("Failed to cleanup attachment file")
