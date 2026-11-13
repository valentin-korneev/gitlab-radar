import asyncio
from collections.abc import Callable

from gitlab_radar.domain.scanning import StopSignal


async def thread_call[T](signal: StopSignal, function: Callable[..., T], *args: object) -> T:
    signal.check()
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        result = await asyncio.shield(task)
    except asyncio.CancelledError:
        signal.stop('Исполнитель останавливается')
        await asyncio.gather(task, return_exceptions=True)
        raise
    signal.check()
    return result
