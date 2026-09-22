import asyncio
import logging

import app.logging_setup
from app.message_router import message_router
from app.platforms.max import MAXPlatform
from app.platforms.tg import TGPlatform

app.logging_setup.setup()

logger = logging.getLogger("Lifecycle")
logger.setLevel(logging.INFO)


async def main():
    message_router.load_rules()

    tg_platform = TGPlatform()
    max_platform = MAXPlatform()

    tasks = [
        asyncio.create_task(tg_platform.start_handling()),
        asyncio.create_task(max_platform.start_handling()),
    ]

    logger.info(f"starting {len(tasks)} platforms:")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            if not task.done():
                task.cancel()
                logger.info(f"stopping {task.get_name()}")
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("bye!")


if __name__ == "__main__":
    asyncio.run(main())
