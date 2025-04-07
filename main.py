import asyncio
import nest_asyncio

from assistant_bot.main import start_assistant_bot
from reminders_bot.main import start_reminders_bot


nest_asyncio.apply()


async def main():
    await asyncio.gather(
        start_reminders_bot(),
        start_assistant_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
