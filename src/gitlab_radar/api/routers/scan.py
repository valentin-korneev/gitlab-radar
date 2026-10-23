from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from gitlab_radar.schemas.scan import ScanStatus
from gitlab_radar.tasks.scan import scan_task

router = APIRouter()


@router.get('/', response_model=ScanStatus)
def get_scan_status() -> ScanStatus:
    return scan_task.status()


@router.post('/', status_code=status.HTTP_202_ACCEPTED)
def scan(background_tasks: BackgroundTasks) -> ScanStatus:
    if not scan_task.reserve():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Задача уже выполняется')

    background_tasks.add_task(scan_task)
    return scan_task.status()
