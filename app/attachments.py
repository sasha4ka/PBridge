import io
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import aiohttp

from app.exc import DownloadError
from app.types import Platform

_attachments: dict[tuple[Platform, str], Path] = {}

logger = logging.getLogger("Attachments")


async def _download_file(url: str, filename: Path):
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        if response.status == 200:
            with open(filename, "wb") as f:
                while True:
                    chunk = await response.content.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        else:
            raise DownloadError(f"Failed to download {url}")


async def download(url: str, id: tuple[Platform, str]):
    attachments_directory: str = "attachments"
    path = Path.joinpath(attachments_directory, f"{id[0]}_{id[1]}")  # type: ignore

    try:
        await _download_file(url, path)
        _attachments[id] = path
    except DownloadError:
        logger.warning(f"Failed to download: {id} - {url}")


@contextmanager
def open_attachment(id: tuple[Platform, str]) -> Generator[io.BufferedReader | None]:
    path = _attachments.get(id)

    if path is None:
        yield None
        return

    with open(path, "rb") as f:
        yield f

    return
