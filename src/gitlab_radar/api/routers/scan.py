from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from gitlab_radar.tasks.scan import scan_task

router = APIRouter()

@router.get('/')
async def scan(background_tasks: BackgroundTasks) -> dict:
    if scan_task.is_running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Задача уже выполняется')

    background_tasks.add_task(scan_task)
    return {'status': 'ok'}
