import asyncio
import signal

from gitlab_radar.config.logging import configure_logging
from gitlab_radar.database.lifecycle import database_lifespan
from gitlab_radar.scanner.worker import ScannerWorker


async def main() -> None:
    async with database_lifespan():
        worker = ScannerWorker()
        await worker.start()
        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, shutdown.set)
        try:
            await shutdown.wait()
        finally:
            await worker.stop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(signum)


if __name__ == '__main__':
    configure_logging()
    asyncio.run(main())
