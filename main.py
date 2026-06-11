import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def run():
    import uvicorn
    from webapp import app as web_app
    from bot_setup import build_bot

    tg_app = build_bot()

    async with tg_app:
        await tg_app.updater.start_polling(drop_pending_updates=True)
        await tg_app.start()

        port = int(os.environ.get("PORT", 8000))
        config = uvicorn.Config(web_app, host="0.0.0.0", port=port,
                                log_level="info", access_log=True)
        server = uvicorn.Server(config)
        logger.info("Web app iniciado na porta %d", port)
        await server.serve()

        await tg_app.updater.stop()


if __name__ == "__main__":
    asyncio.run(run())
