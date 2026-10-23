from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from gitlab_radar.tasks.scan import scan_task

router = APIRouter()


@router.post('/', status_code=status.HTTP_202_ACCEPTED)
async def scan(background_tasks: BackgroundTasks) -> dict[str, str]:
    if not scan_task.reserve():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Задача уже выполняется')

    background_tasks.add_task(scan_task)
    return {'status': 'accepted'}
