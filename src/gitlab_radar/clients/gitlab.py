from collections.abc import Callable
from http import HTTPStatus

import gitlab
import requests
from gitlab.exceptions import GitlabHttpError

from gitlab_radar.config import settings
from gitlab_radar.domain.scanning import ScanRateLimitError, StopSignal

REQUEST_TIMEOUT = 20
RATE_LIMIT_ATTEMPTS = 3
MAX_RATE_LIMIT_WAIT = 30


class ScanAdapter:
    def __init__(self, signal: StopSignal, before_request: Callable[[], None] | None = None) -> None:
        self.adapter = requests.adapters.HTTPAdapter(max_retries=0)
        self.signal = signal
        self.before_request = before_request

    def send(self, request: requests.PreparedRequest, **kwargs: object) -> requests.Response:
        self.signal.check()
        if self.before_request is not None:
            self.before_request()
        return self.adapter.send(request, **kwargs)

    def close(self) -> None:
        self.adapter.close()


class ScanGitLab(gitlab.Gitlab):
    def __init__(self, signal: StopSignal, before_request: Callable[[], None] | None = None) -> None:
        super().__init__(
            url=settings.gitlab.url,
            private_token=settings.gitlab.private_token.get_secret_value(),
            timeout=REQUEST_TIMEOUT,
            retry_transient_errors=False,
        )
        self.signal = signal
        self.before_request = before_request
        self.request_count = 0
        self.rate_limit_wait = 5.0
        self.session.mount('https://', ScanAdapter(signal, before_request))
        self.session.mount('http://', ScanAdapter(signal, before_request))
        self.session.hooks.setdefault('response', []).append(self._response)

    def _response(self, response: requests.Response, **_: object) -> requests.Response:
        self.request_count += 1
        try:
            self.rate_limit_wait = min(MAX_RATE_LIMIT_WAIT, max(1, float(response.headers.get('Retry-After', 5))))
        except ValueError:
            self.rate_limit_wait = 5.0
        return response

    def http_request(self, *args: object, **kwargs: object) -> requests.Response:
        kwargs.update(timeout=REQUEST_TIMEOUT, max_retries=0, obey_rate_limit=False)
        for attempt in range(RATE_LIMIT_ATTEMPTS):
            self.signal.check()
            try:
                return super().http_request(*args, **kwargs)
            except GitlabHttpError as error:
                if error.response_code != HTTPStatus.TOO_MANY_REQUESTS:
                    raise
                if attempt == RATE_LIMIT_ATTEMPTS - 1:
                    msg = 'GitLab ограничил частоту запросов; запуск остановлен'
                    raise ScanRateLimitError(msg) from error
                self.signal.wait(self.rate_limit_wait)
        msg = 'Лимит запросов GitLab исчерпан'
        raise ScanRateLimitError(msg)
