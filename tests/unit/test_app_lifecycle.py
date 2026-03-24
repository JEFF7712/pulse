from fastapi.testclient import TestClient


class StubScheduler:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False

    def start(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.shutdown_called = True


def test_create_app_starts_and_stops_scheduler_via_lifecycle() -> None:
    from pulse.app.main import create_app

    scheduler = StubScheduler()
    app = create_app(scheduler_factory=lambda: scheduler)

    assert scheduler.started is False
    assert scheduler.shutdown_called is False

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert scheduler.started is True
        assert scheduler.shutdown_called is False

    assert scheduler.shutdown_called is True
