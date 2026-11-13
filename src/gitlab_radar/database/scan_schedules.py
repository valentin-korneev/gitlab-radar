from datetime import UTC, datetime, time, timedelta

from tortoise.transactions import in_transaction

from gitlab_radar.database.models import ScanRun, ScanSchedule
from gitlab_radar.database.scan_jobs import ACTIVE_STATES, SUBMISSION_LOCK
from gitlab_radar.schemas.scan import ScanPhase, ScanSource, ScanState
from gitlab_radar.schemas.scan_management import SchedulePayload


def next_run_at(now: datetime, time_of_day: time, weekdays: list[int]) -> datetime:
    local_date = now.astimezone().date()
    for offset in range(8):
        day = local_date + timedelta(days=offset)
        candidate = datetime.combine(day, time_of_day).astimezone(UTC)
        if day.weekday() in weekdays and candidate > now:
            return candidate
    message = 'В расписании должен быть указан хотя бы один день недели'
    raise ValueError(message)


async def save_schedule(payload: SchedulePayload, schedule_id: int | None = None) -> ScanSchedule | None:
    async with in_transaction() as connection:
        row = None
        if schedule_id is not None:
            row = await ScanSchedule.filter(id=schedule_id).using_db(connection).select_for_update().first()
            if row is None:
                return None
        values = payload.model_dump(mode='python')
        values['time_of_day'] = payload.time_of_day.strftime('%H:%M')
        values['options'] = payload.options.model_dump(mode='json')
        values['next_run_at'] = (
            next_run_at(datetime.now(UTC), payload.time_of_day, payload.weekdays) if payload.enabled else None
        )
        if row is None:
            return await ScanSchedule.create(**values, using_db=connection)
        if (
            payload.enabled
            and row.enabled
            and row.time_of_day == values['time_of_day']
            and row.weekdays == payload.weekdays
            and row.next_run_at is not None
        ):
            values['next_run_at'] = row.next_run_at
        row.update_from_dict(values)
        await row.save(using_db=connection)
        return row


async def set_enabled(schedule_id: int, *, enabled: bool) -> ScanSchedule | None:
    async with in_transaction() as connection:
        row = await ScanSchedule.filter(id=schedule_id).using_db(connection).select_for_update().first()
        if row is None:
            return None
        if row.enabled == enabled:
            return row
        row.enabled = enabled
        row.next_run_at = (
            next_run_at(datetime.now(UTC), time.fromisoformat(row.time_of_day), row.weekdays) if enabled else None
        )
        await row.save(using_db=connection, update_fields=['enabled', 'next_run_at'])
        return row


async def enqueue_due_schedule() -> None:
    async with in_transaction() as connection:
        await connection.execute_query('SELECT pg_advisory_xact_lock($1)', [SUBMISSION_LOCK])
        if await ScanRun.filter(state__in=(ScanState.QUEUED, *ACTIVE_STATES)).using_db(connection).exists():
            return
        now = datetime.now(UTC)
        schedule = (
            await ScanSchedule.filter(enabled=True, next_run_at__lte=now)
            .using_db(connection)
            .select_for_update()
            .order_by('next_run_at', 'id')
            .first()
        )
        if schedule is None:
            return
        await ScanRun.create(
            state=ScanState.QUEUED,
            phase=ScanPhase.IDLE,
            source=ScanSource.SCHEDULE,
            schedule_id=schedule.id,
            schedule_name=schedule.name,
            options=schedule.options,
            using_db=connection,
        )
        schedule.last_run_at = now
        schedule.next_run_at = next_run_at(now, time.fromisoformat(schedule.time_of_day), schedule.weekdays)
        await schedule.save(using_db=connection, update_fields=['last_run_at', 'next_run_at'])
