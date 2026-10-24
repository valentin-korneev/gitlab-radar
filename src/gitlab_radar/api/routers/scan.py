from fastapi import APIRouter, HTTPException, Response, status

from gitlab_radar.schemas.scan import ScanStatus
from gitlab_radar.tasks.scan import scan_task

router = APIRouter()


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
