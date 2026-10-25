import asyncio

from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketDisconnect, status

from gitlab_radar.schemas.scan import ScanStatus
from gitlab_radar.tasks.scan import scan_task

router = APIRouter()


@router.websocket('/ws')
async def scan_status_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    updates = scan_task.subscribe()
    try:
        await websocket.send_json((await scan_task.status()).model_dump(mode='json'))
        while True:
            update_task = asyncio.create_task(updates.get())
            disconnect_task = asyncio.create_task(websocket.receive())
            done, pending = await asyncio.wait(
                {update_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if disconnect_task in done:
                message = disconnect_task.result()
                if message['type'] == 'websocket.disconnect':
                    break
                continue
            await websocket.send_json(update_task.result().model_dump(mode='json'))
    except WebSocketDisconnect:
        pass
    finally:
        scan_task.unsubscribe(updates)


@router.get('/', response_model=ScanStatus)
async def get_scan_status(response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    return await scan_task.status()


@router.post('/', status_code=status.HTTP_202_ACCEPTED)
async def scan(response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    if not await scan_task.start():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Задача уже выполняется')
    return await scan_task.status()
