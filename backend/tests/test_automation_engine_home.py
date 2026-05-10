from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import Settings
from app.services.automation import AutomationEngine


@dataclass
class StubModeState:
    enabled: bool

    async def is_home_automation_enabled(self) -> bool:
        return self.enabled


class StubHomeController:
    def __init__(self):
        self.called_actions: list[str] = []

    async def publish_action(self, action: str):
        self.called_actions.append(action)
        return {
            "type": action,
            "action": action,
            "domain": "home",
            "status": "executed",
        }


def test_detect_home_command_blocked_when_home_mode_disabled():
    settings = Settings()
    engine = AutomationEngine(
        settings=settings,
        mode_state=StubModeState(enabled=False),
        home_controller=StubHomeController(),
    )

    result = asyncio.run(engine.detect_and_execute("turn on lights"))

    assert result is not None
    assert result["domain"] == "home"
    assert result["status"] == "blocked_home_mode"


def test_detect_home_command_executes_when_enabled():
    settings = Settings()
    controller = StubHomeController()
    engine = AutomationEngine(
        settings=settings,
        mode_state=StubModeState(enabled=True),
        home_controller=controller,
    )

    result = asyncio.run(engine.detect_and_execute("turn on fan"))

    assert result is not None
    assert result["domain"] == "home"
    assert result["status"] == "executed"
    assert controller.called_actions == ["fan_on"]


def test_detect_scene_command_maps_to_scene_action():
    settings = Settings()
    controller = StubHomeController()
    engine = AutomationEngine(
        settings=settings,
        mode_state=StubModeState(enabled=True),
        home_controller=controller,
    )

    result = asyncio.run(engine.detect_and_execute("good night"))

    assert result is not None
    assert result["action"] == "scene_good_night"
    assert controller.called_actions == ["scene_good_night"]


def test_detect_home_command_accepts_raw_toggle_tokens():
    settings = Settings()
    controller = StubHomeController()
    engine = AutomationEngine(
        settings=settings,
        mode_state=StubModeState(enabled=True),
        home_controller=controller,
    )

    result = asyncio.run(engine.detect_and_execute("tv_off"))

    assert result is not None
    assert result["action"] == "tv_off"
    assert result["domain"] == "home"
    assert controller.called_actions == ["tv_off"]


def test_detect_home_command_accepts_status_check_token():
    settings = Settings()
    controller = StubHomeController()
    engine = AutomationEngine(
        settings=settings,
        mode_state=StubModeState(enabled=True),
        home_controller=controller,
    )

    result = asyncio.run(engine.detect_and_execute("status_check"))

    assert result is not None
    assert result["action"] == "status_check"
    assert controller.called_actions == ["status_check"]


def test_detect_home_command_normalizes_filler_words_and_punctuation():
    settings = Settings()
    controller = StubHomeController()
    engine = AutomationEngine(
        settings=settings,
        mode_state=StubModeState(enabled=True),
        home_controller=controller,
    )

    result = asyncio.run(engine.detect_and_execute("Hey Zara, please turn on the lights!"))

    assert result is not None
    assert result["action"] == "light_on"
    assert result["domain"] == "home"
    assert controller.called_actions == ["light_on"]
