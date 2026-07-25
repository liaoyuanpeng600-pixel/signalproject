import pytest

from src.ingestion.connector import (
    ConnectorError,
    ConnectorErrorKind,
    HttpResponse,
)


def test_connector_error_exposes_bounded_retry_metadata() -> None:
    error = ConnectorError(
        ConnectorErrorKind.RATE_LIMITED,
        "rate limited",
        retryable=True,
        retry_after_seconds=30,
    )
    assert error.kind == ConnectorErrorKind.RATE_LIMITED
    assert error.retryable
    assert error.retry_after_seconds == 30


def test_http_response_header_is_case_insensitive() -> None:
    response = HttpResponse(
        status=200, body=b"", headers=(("Retry-After", "12"),)
    )
    assert response.header("retry-after") == "12"


def test_connector_error_is_exception() -> None:
    with pytest.raises(ConnectorError):
        raise ConnectorError(
            ConnectorErrorKind.PERMANENT, "invalid", retryable=False
        )
