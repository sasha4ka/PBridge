from abc import ABC


class BasePlatform(ABC):
    async def start_handling(self):
        """
        Called once on app startup
        Must handle Cancelled error for app exiting
        """
