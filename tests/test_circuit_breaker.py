"""Tests for circuit breaker module."""

import time

import pytest

from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        assert cb.state == CircuitState.CLOSED
        assert not cb.is_open()

    def test_stays_closed_below_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_open()

    def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_opens_on_failure(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_context_manager_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
        with cb:
            pass
        assert cb.state == CircuitState.CLOSED

    def test_context_manager_failure(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
        with pytest.raises(ValueError, match="boom"):
            with cb:
                raise ValueError("boom")
        assert cb._failure_count == 1

    def test_context_manager_opens_circuit(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
        for _ in range(2):
            with pytest.raises(ValueError):
                with cb:
                    raise ValueError("boom")
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_rejects_context(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure()
        assert cb.is_open()
        with pytest.raises(CircuitBreakerOpenError):
            with cb:
                pass

    def test_name(self) -> None:
        cb = CircuitBreaker(name="test-api")
        assert cb.name == "test-api"

    def test_failure_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=1.0)
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2

    def test_success_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=1.0)
        cb.record_success()
        cb.record_success()
        assert cb._success_count == 2

    def test_default_name(self) -> None:
        cb = CircuitBreaker()
        assert cb.name == "default"

    def test_open_error_message(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0, name="myapi")
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpenError, match="myapi"):
            with cb:
                pass
