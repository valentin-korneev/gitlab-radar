import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect, status

from gitlab_radar.auth import consume_websocket_ticket, management_access_dependency
from gitlab_radar.schemas.scan import ScanStatus
from gitlab_radar.tasks.scan import scan_task

router = APIRouter()


@router.websocket('/ws')
async def scan_status_socket(websocket: WebSocket) -> None:
    ticket = websocket.query_params.get('ticket')
    if ticket is None or not await consume_websocket_ticket(ticket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    previous_status: dict | None = None
    try:
        while True:
            status_payload = (await scan_task.status()).model_dump(mode='json')
            if status_payload != previous_status:
                await websocket.send_json(status_payload)
                previous_status = status_payload
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1)
            except TimeoutError:
                continue
            if message['type'] == 'websocket.disconnect':
                break
    except WebSocketDisconnect:
        pass


@router.get('/', response_model=ScanStatus, dependencies=[Depends(management_access_dependency)])
async def get_scan_status(response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    return await scan_task.status()


@router.post('/', status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(management_access_dependency)])
async def scan(response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    if not await scan_task.start():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Задача уже выполняется')
    return await scan_task.status()
