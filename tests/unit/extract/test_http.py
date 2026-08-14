"""Network-free tests for bounded HTTP extraction behavior."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from kidney_care_mart.extract.http import (
    ContentLengthMismatchError,
    HttpStatusError,
    JsonResponseError,
    RetryPolicy,
    fetch_json,
    stream_download,
)


class FakeResponse:
    """Small context-managed binary response with observable chunked reads."""

    def __init__(
        self,
        content: bytes,
        *,
        headers: dict[str, str] | None = None,
        interrupt_after_reads: int | None = None,
    ) -> None:
        self._stream = io.BytesIO(content)
        self.headers = headers or {}
        self.interrupt_after_reads = interrupt_after_reads
        self.read_sizes: list[int] = []
        self.closed = False

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if (
            self.interrupt_after_reads is not None
            and len(self.read_sizes) > self.interrupt_after_reads
        ):
            raise ConnectionError("fixture transfer interrupted")
        return self._stream.read(size)


class SequenceOpener:
    """Return or raise configured outcomes while retaining request evidence."""

    def __init__(self, outcomes: list[FakeResponse | BaseException]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def retry_policy(max_attempts: int = 3) -> RetryPolicy:
    """Return a fast deterministic policy for unit tests."""
    return RetryPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=1.0,
        max_delay_seconds=4.0,
    )


def test_stream_download_preserves_bytes_and_records_transport_evidence(
    tmp_path: Path,
) -> None:
    content = b"alpha,beta\n1,2\n3,4\n"
    response = FakeResponse(
        content,
        headers={
            "Content-Length": str(len(content)),
            "ETag": '"fixture-etag"',
            "Last-Modified": "Fri, 14 Aug 2026 12:00:00 GMT",
        },
    )
    opener = SequenceOpener([response])
    destination = tmp_path / "download.partial"

    result = stream_download(
        "https://data.cms.gov/fixture.csv",
        destination,
        opener=opener,
        timeout_seconds=7.5,
        chunk_size=5,
        retry_policy=retry_policy(),
    )

    assert destination.read_bytes() == content
    assert result.byte_count == len(content)
    assert result.content_sha256 == hashlib.sha256(content).hexdigest()
    assert result.etag == '"fixture-etag"'
    assert result.last_modified == "Fri, 14 Aug 2026 12:00:00 GMT"
    assert result.attempt_count == 1
    assert result.retry_count == 0
    assert len(response.read_sizes) > 2
    request, timeout = opener.calls[0]
    assert timeout == 7.5
    assert request.full_url == "https://data.cms.gov/fixture.csv"
    assert "kidney-care-analytics-mart" in request.get_header("User-agent")


def test_content_length_mismatch_is_bounded_and_cleans_partial_file(
    tmp_path: Path,
) -> None:
    content = b"truncated"
    opener = SequenceOpener(
        [
            FakeResponse(content, headers={"Content-Length": "100"}),
            FakeResponse(content, headers={"Content-Length": "100"}),
        ]
    )
    destination = tmp_path / "download.partial"

    with pytest.raises(ContentLengthMismatchError):
        stream_download(
            "https://data.cms.gov/fixture.csv",
            destination,
            opener=opener,
            sleep=lambda _delay: None,
            jitter=lambda: 0.0,
            retry_policy=retry_policy(max_attempts=2),
        )

    assert len(opener.calls) == 2
    assert not destination.exists()


def retryable_errors() -> list[Callable[[], BaseException]]:
    """Create fresh retryable exceptions for parametrized tests."""
    return [
        lambda: URLError("temporary DNS failure"),
        lambda: TimeoutError("temporary timeout"),
        lambda: ConnectionError("temporary connection failure"),
        lambda: HTTPError("https://example.test", 408, "timeout", {}, None),
        lambda: HTTPError("https://example.test", 429, "limited", {}, None),
        lambda: HTTPError("https://example.test", 503, "unavailable", {}, None),
    ]


@pytest.mark.parametrize("error_factory", retryable_errors())
def test_transient_failures_retry_with_injected_backoff(
    tmp_path: Path,
    error_factory: Callable[[], BaseException],
) -> None:
    sleeps: list[float] = []
    content = b"complete"
    opener = SequenceOpener(
        [
            error_factory(),
            FakeResponse(content, headers={"Content-Length": str(len(content))}),
        ]
    )

    result = stream_download(
        "https://data.cms.gov/fixture.csv",
        tmp_path / "download.partial",
        opener=opener,
        sleep=sleeps.append,
        jitter=lambda: 0.25,
        retry_policy=retry_policy(),
    )

    assert result.attempt_count == 2
    assert result.retry_count == 1
    assert sleeps == [1.25]


def test_nonretryable_http_error_fails_immediately(tmp_path: Path) -> None:
    opener = SequenceOpener(
        [HTTPError("https://example.test", 404, "not found", {}, None)]
    )
    destination = tmp_path / "download.partial"

    with pytest.raises(HttpStatusError, match="404"):
        stream_download(
            "https://data.cms.gov/fixture.csv",
            destination,
            opener=opener,
            sleep=lambda _delay: pytest.fail("ordinary 4xx must not retry"),
            retry_policy=retry_policy(),
        )

    assert len(opener.calls) == 1
    assert not destination.exists()


def test_interrupted_transfer_exhaustion_cleans_partial_file(tmp_path: Path) -> None:
    opener = SequenceOpener(
        [
            FakeResponse(b"abcdefgh", interrupt_after_reads=1),
            FakeResponse(b"abcdefgh", interrupt_after_reads=1),
        ]
    )
    destination = tmp_path / "download.partial"

    with pytest.raises(ConnectionError, match="interrupted"):
        stream_download(
            "https://data.cms.gov/fixture.csv",
            destination,
            opener=opener,
            chunk_size=4,
            sleep=lambda _delay: None,
            jitter=lambda: 0.0,
            retry_policy=retry_policy(max_attempts=2),
        )

    assert not destination.exists()


def test_fetch_json_uses_same_bounded_transport_policy() -> None:
    payload = {"dataset": [{"title": "fixture"}]}
    body = json.dumps(payload).encode()
    sleeps: list[float] = []
    opener = SequenceOpener(
        [
            HTTPError("https://example.test", 503, "unavailable", {}, None),
            FakeResponse(body, headers={"Content-Length": str(len(body))}),
        ]
    )

    result = fetch_json(
        "https://data.cms.gov/data.json",
        opener=opener,
        sleep=sleeps.append,
        jitter=lambda: 0.0,
        retry_policy=retry_policy(),
    )

    assert result == payload
    assert len(opener.calls) == 2
    assert sleeps == [1.0]


def test_invalid_json_is_not_retried() -> None:
    opener = SequenceOpener([FakeResponse(b"not-json"), FakeResponse(b"{}")])

    with pytest.raises(JsonResponseError):
        fetch_json(
            "https://data.cms.gov/data.json",
            opener=opener,
            retry_policy=retry_policy(),
        )

    assert len(opener.calls) == 1
