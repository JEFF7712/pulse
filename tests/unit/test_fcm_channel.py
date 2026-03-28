from pulse.domain.notifications import Notification


class FakeHTTPClient:
    def __init__(self, status_code: int = 200):
        self.sent: list[dict] = []
        self.status_code = status_code

    def post(self, url: str, *, headers: dict, json: dict) -> "FakeResponse":
        self.sent.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.status_code)


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class FakeCredentials:
    def __init__(self):
        self.token = "fake-access-token"
        self.valid = True

    def refresh(self, request):
        self.token = "refreshed-access-token"
        self.valid = True


def test_fcm_channel_sends_notification_to_all_tokens():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [{"token": "device-a", "platform": "ios"}]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    result = channel.send(
        Notification(
            title="Morning Briefing",
            body="You have 3 meetings today.",
            category="briefing",
            context_id="2026-03-27",
        )
    )

    assert result is True
    assert len(http.sent) == 1
    payload = http.sent[0]["json"]
    assert payload["message"]["token"] == "device-a"
    assert payload["message"]["notification"]["title"] == "Morning Briefing"
    assert payload["message"]["notification"]["body"] == "You have 3 meetings today."
    assert payload["message"]["data"]["context_id"] == "2026-03-27"


def test_fcm_channel_sends_to_multiple_tokens():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [
        {"token": "device-a", "platform": "ios"},
        {"token": "device-b", "platform": "ios"},
    ]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    channel.send(
        Notification(title="Test", body="Body", category="test")
    )

    assert len(http.sent) == 2
    assert http.sent[0]["json"]["message"]["token"] == "device-a"
    assert http.sent[1]["json"]["message"]["token"] == "device-b"


def test_fcm_channel_returns_false_when_no_tokens():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=[],
        http_client=http,
    )

    result = channel.send(
        Notification(title="Test", body="Body", category="test")
    )

    assert result is False
    assert len(http.sent) == 0


def test_fcm_channel_includes_authorization_header():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [{"token": "device-a", "platform": "ios"}]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    channel.send(
        Notification(title="Test", body="Body", category="test")
    )

    assert http.sent[0]["headers"]["Authorization"] == "Bearer fake-access-token"


def test_fcm_channel_omits_context_id_from_data_when_none():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [{"token": "device-a", "platform": "ios"}]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    channel.send(
        Notification(title="Test", body="Body", category="test", context_id=None)
    )

    data = http.sent[0]["json"]["message"].get("data", {})
    assert "context_id" not in data
