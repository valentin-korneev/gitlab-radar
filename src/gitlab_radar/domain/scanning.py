from threading import Event


class ScanInterruptedError(Exception):
    pass


class OwnershipLostError(ScanInterruptedError):
    pass


class ScanRateLimitError(Exception):
    pass


class StopSignal:
    def __init__(self) -> None:
        self.event = Event()
        self.reason = 'Сканирование остановлено'
        self.ownership_lost = False

    def stop(self, reason: str = 'Сканирование остановлено', *, lost: bool = False) -> None:
        if lost or not self.event.is_set():
            self.reason = reason
        self.ownership_lost = self.ownership_lost or lost
        self.event.set()

    def check(self) -> None:
        if self.ownership_lost:
            raise OwnershipLostError(self.reason)
        if self.event.is_set():
            raise ScanInterruptedError(self.reason)

    def wait(self, seconds: float) -> None:
        self.event.wait(seconds)
        self.check()


class ScanResultsArchivedError(Exception):
    def __init__(self) -> None:
        super().__init__('Данные этого снимка удалены по сроку хранения. История запуска и изменений сохранена.')
