from pulse.analysis.prompts import (
    DiscoveryResponse,
    NewPattern,
    NotificationItem,
    UpdatedPattern,
    build_discovery_prompt,
    parse_discovery_response,
)


def test_build_discovery_prompt_includes_all_sections():
    result = build_discovery_prompt(
        cadence="daily",
        date_range="2026-03-26",
        event_summary="Listened to 5 songs, visited 3 websites",
        active_patterns="sleep-deficit: waking tired on Mondays",
        baselines="avg sleep: 7h",
        user_profile="prefers actionable insights",
    )

    assert "system_prompt" in result
    assert "user_prompt" in result

    user_prompt = result["user_prompt"]
    assert "2026-03-26" in user_prompt
    assert "Listened to 5 songs, visited 3 websites" in user_prompt
    assert "sleep-deficit: waking tired on Mondays" in user_prompt
    assert "avg sleep: 7h" in user_prompt
    assert "prefers actionable insights" in user_prompt

    system_prompt = result["system_prompt"]
    assert "JSON" in system_prompt


def test_build_discovery_prompt_handles_empty_patterns():
    result = build_discovery_prompt(
        cadence="weekly",
        date_range="2026-03-20 to 2026-03-26",
        event_summary="Some events",
        active_patterns="",
        baselines="",
        user_profile="",
    )

    user_prompt = result["user_prompt"]
    assert "No active patterns yet" in user_prompt
    assert "No baselines established yet" in user_prompt


def test_build_discovery_prompt_cadence_instructions():
    daily = build_discovery_prompt(
        cadence="daily",
        date_range="2026-03-26",
        event_summary="events",
        active_patterns="",
        baselines="",
        user_profile="",
    )
    weekly = build_discovery_prompt(
        cadence="weekly",
        date_range="2026-03-20 to 2026-03-26",
        event_summary="events",
        active_patterns="",
        baselines="",
        user_profile="",
    )
    monthly = build_discovery_prompt(
        cadence="monthly",
        date_range="2026-03-01 to 2026-03-31",
        event_summary="events",
        active_patterns="",
        baselines="",
        user_profile="",
    )

    assert "notable" in daily["user_prompt"].lower() or "unusual" in daily["user_prompt"].lower()
    assert "cross-source" in weekly["user_prompt"].lower() or "week" in weekly["user_prompt"].lower()
    assert "long-term" in monthly["user_prompt"].lower() or "trend" in monthly["user_prompt"].lower()


def test_parse_discovery_response_extracts_fields():
    raw = """{
        "new_patterns": [
            {
                "title": "Late-night browsing",
                "observation": "Browsing spikes after 11pm on weekdays",
                "confidence": 0.8,
                "evidence": ["3 visits past 11pm", "avg 45min"],
                "trend": "increasing"
            }
        ],
        "updated_patterns": [
            {
                "slug": "sleep-deficit",
                "status": "confirmed",
                "confidence": 0.9,
                "update_note": "Still occurring",
                "new_evidence": ["Tired Monday again"],
                "trend": "stable"
            }
        ],
        "notifications": [
            {
                "title": "Late-night browsing detected",
                "body": "You browsed late 3 nights this week",
                "priority": "low"
            }
        ],
        "baseline_updates": "avg browsing: 45min/night"
    }"""

    response = parse_discovery_response(raw)

    assert isinstance(response, DiscoveryResponse)
    assert len(response.new_patterns) == 1
    np = response.new_patterns[0]
    assert isinstance(np, NewPattern)
    assert np.title == "Late-night browsing"
    assert np.observation == "Browsing spikes after 11pm on weekdays"
    assert np.confidence == 0.8
    assert np.evidence == ["3 visits past 11pm", "avg 45min"]
    assert np.trend == "increasing"

    assert len(response.updated_patterns) == 1
    up = response.updated_patterns[0]
    assert isinstance(up, UpdatedPattern)
    assert up.slug == "sleep-deficit"
    assert up.status == "confirmed"
    assert up.confidence == 0.9
    assert up.update_note == "Still occurring"
    assert up.new_evidence == ["Tired Monday again"]
    assert up.trend == "stable"

    assert len(response.notifications) == 1
    notif = response.notifications[0]
    assert isinstance(notif, NotificationItem)
    assert notif.title == "Late-night browsing detected"
    assert notif.body == "You browsed late 3 nights this week"
    assert notif.priority == "low"

    assert response.baseline_updates == "avg browsing: 45min/night"


def test_parse_discovery_response_handles_malformed_json():
    response = parse_discovery_response("not valid json")

    assert isinstance(response, DiscoveryResponse)
    assert response.new_patterns == []
    assert response.updated_patterns == []
    assert response.notifications == []
    assert response.baseline_updates is None


def test_parse_discovery_response_handles_empty_lists():
    raw = '{"new_patterns": [], "updated_patterns": [], "notifications": [], "baseline_updates": null}'
    response = parse_discovery_response(raw)

    assert response.new_patterns == []
    assert response.updated_patterns == []
    assert response.notifications == []
    assert response.baseline_updates is None
