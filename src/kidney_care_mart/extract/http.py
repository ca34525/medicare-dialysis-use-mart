"""Bounded standard-library HTTP behavior for public source extraction."""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT: Final = (
    "kidney-care-analytics-mart/0.1 "
    "(+public aggregate data ingestion; contact via repository)"
)
DEFAULT_TIMEOUT_SECONDS: Final = 30.0
DEFAULT_CHUNK_SIZE: Final = 64 * 1024
DEFAULT_MAX_JSON_BYTES: Final = 32 * 1024 * 1024


class BinaryResponse(Protocol):
    """Narrow response interface used by production and fake openers."""

    headers: Mapping[str, str]

    def __enter__(self) -> BinaryResponse: ...

    def __exit__(self, *args: object) -> object: ...

    def read(self, size: int = -1) -> bytes: ...


ResponseOpener = Callable[[Request, float], BinaryResponse]
Sleep = Callable[[float], object]
Jitter = Callable[[], float]


class HttpExtractionError(RuntimeError):
    """Base class for bounded HTTP extraction failures."""


class HttpStatusError(HttpExtractionError):
    """A nonretryable or exhausted HTTP status response."""


class ContentLengthMismatchError(HttpExtractionError):
    """The completed body did not match the advertised byte count."""


class JsonResponseError(HttpExtractionError):
    """A response completed but was not valid JSON of the expected shape."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential retry settings for transient transport failures."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds cannot be negative")

    def delay_after(self, failed_attempt: int, jitter_value: float) -> float:
        """Return a capped exponential delay plus bounded injected jitter."""
        if failed_attempt < 1:
            raise ValueError("failed_attempt must be positive")
        if not 0.0 <= jitter_value <= 1.0:
            raise ValueError("jitter must return a value between 0 and 1")
        exponential = self.base_delay_seconds * (2 ** (failed_attempt - 1))
        return min(self.max_delay_seconds, exponential + jitter_value)


DEFAULT_RETRY_POLICY: Final = RetryPolicy()


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Evidence calculated while streaming an unchanged response to disk."""

    path: Path
    content_sha256: str
    content_sha1: str
    byte_count: int
    etag: str | None
    last_modified: str | None
    content_type: str | None
    attempt_count: int

    @property
    def retry_count(self) -> int:
        """Return the number of attempts after the initial request."""
        return self.attempt_count - 1


def _default_opener(request: Request, timeout: float) -> BinaryResponse:
    return cast(BinaryResponse, urlopen(request, timeout=timeout))


def _request(url: str, *, accept: str) -> Request:
    if not url.startswith("https://"):
        raise ValueError("source URL must use HTTPS")
    return Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Read a response header from plain or case-insensitive mappings."""
    value = headers.get(name)
    if value is not None:
        return str(value)
    expected = name.casefold()
    for key, candidate in headers.items():
        if str(key).casefold() == expected:
            return str(candidate)
    return None


def _expected_content_length(headers: Mapping[str, str]) -> int | None:
    raw_value = _header(headers, "Content-Length")
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError as error:
        raise HttpExtractionError(
            f"invalid HTTP Content-Length header: {raw_value!r}"
        ) from error
    if value < 0:
        raise HttpExtractionError("HTTP Content-Length cannot be negative")
    return value


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return error.code in {408, 429} or 500 <= error.code <= 599
    return isinstance(error, (ConnectionError, TimeoutError, URLError))


def _sleep_before_retry(
    policy: RetryPolicy,
    failed_attempt: int,
    *,
    sleep: Sleep,
    jitter: Jitter,
) -> None:
    sleep(policy.delay_after(failed_attempt, jitter()))


def stream_download(
    url: str,
    destination: Path,
    *,
    accept: str = "text/csv,application/octet-stream;q=0.9",
    opener: ResponseOpener = _default_opener,
    sleep: Sleep = time.sleep,
    jitter: Jitter = random.random,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> DownloadResult:
    """Stream one complete response to a new temporary file with evidence.

    The destination must be a staging path. Each failed attempt removes its
    partial file before retrying, and no response bytes are normalized.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if destination.exists():
        raise FileExistsError(f"staging destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    request = _request(url, accept=accept)
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            with opener(request, timeout_seconds) as response:
                expected_length = _expected_content_length(response.headers)
                sha256 = hashlib.sha256()
                sha1 = hashlib.sha1()
                byte_count = 0
                with destination.open("xb") as staged_file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        staged_file.write(chunk)
                        sha256.update(chunk)
                        sha1.update(chunk)
                        byte_count += len(chunk)
                    staged_file.flush()

                if expected_length is not None and byte_count != expected_length:
                    raise ContentLengthMismatchError(
                        "HTTP Content-Length mismatch: "
                        f"expected {expected_length} bytes, received {byte_count}"
                    )

                return DownloadResult(
                    path=destination,
                    content_sha256=sha256.hexdigest(),
                    content_sha1=sha1.hexdigest(),
                    byte_count=byte_count,
                    etag=_header(response.headers, "ETag"),
                    last_modified=_header(response.headers, "Last-Modified"),
                    content_type=_header(response.headers, "Content-Type"),
                    attempt_count=attempt,
                )
        except HTTPError as error:
            destination.unlink(missing_ok=True)
            if not _is_retryable(error) or attempt == retry_policy.max_attempts:
                raise HttpStatusError(
                    f"HTTP {error.code} while retrieving {url}"
                ) from error
            _sleep_before_retry(
                retry_policy,
                attempt,
                sleep=sleep,
                jitter=jitter,
            )
        except ContentLengthMismatchError:
            destination.unlink(missing_ok=True)
            if attempt == retry_policy.max_attempts:
                raise
            _sleep_before_retry(
                retry_policy,
                attempt,
                sleep=sleep,
                jitter=jitter,
            )
        except (ConnectionError, TimeoutError, URLError):
            destination.unlink(missing_ok=True)
            if attempt == retry_policy.max_attempts:
                raise
            _sleep_before_retry(
                retry_policy,
                attempt,
                sleep=sleep,
                jitter=jitter,
            )
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

    raise AssertionError("bounded attempt loop terminated unexpectedly")


def fetch_json(
    url: str,
    *,
    opener: ResponseOpener = _default_opener,
    sleep: Sleep = time.sleep,
    jitter: Jitter = random.random,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_response_bytes: int = DEFAULT_MAX_JSON_BYTES,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> dict[str, Any]:
    """Retrieve a bounded JSON object, retrying transport failures only."""
    if max_response_bytes < 1:
        raise ValueError("max_response_bytes must be positive")
    request = _request(url, accept="application/json")

    body: bytes | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            with opener(request, timeout_seconds) as response:
                expected_length = _expected_content_length(response.headers)
                if expected_length is not None and expected_length > max_response_bytes:
                    raise HttpExtractionError(
                        "JSON response exceeds configured byte limit: "
                        f"{expected_length} > {max_response_bytes}"
                    )
                chunks: list[bytes] = []
                byte_count = 0
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > max_response_bytes:
                        raise HttpExtractionError(
                            "JSON response exceeds configured byte limit"
                        )
                    chunks.append(chunk)
                if expected_length is not None and byte_count != expected_length:
                    raise ContentLengthMismatchError(
                        "HTTP Content-Length mismatch: "
                        f"expected {expected_length} bytes, received {byte_count}"
                    )
                body = b"".join(chunks)
                break
        except HTTPError as error:
            if not _is_retryable(error) or attempt == retry_policy.max_attempts:
                raise HttpStatusError(
                    f"HTTP {error.code} while retrieving {url}"
                ) from error
            _sleep_before_retry(
                retry_policy,
                attempt,
                sleep=sleep,
                jitter=jitter,
            )
        except ContentLengthMismatchError:
            if attempt == retry_policy.max_attempts:
                raise
            _sleep_before_retry(
                retry_policy,
                attempt,
                sleep=sleep,
                jitter=jitter,
            )
        except (ConnectionError, TimeoutError, URLError):
            if attempt == retry_policy.max_attempts:
                raise
            _sleep_before_retry(
                retry_policy,
                attempt,
                sleep=sleep,
                jitter=jitter,
            )

    if body is None:
        raise AssertionError("bounded attempt loop terminated unexpectedly")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JsonResponseError(f"response from {url} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise JsonResponseError(f"response from {url} is not a JSON object")
    return payload
