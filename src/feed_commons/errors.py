from typing import Literal

PollErrorCode = Literal["timeout", "invalid_url", "http_error", "parse_error", "network_error"]


class PollError(Exception):
    def __init__(self, code: PollErrorCode) -> None:
        self.code = code
        super().__init__(code)
