"""Test WebSocket API."""

import asyncio
from unittest.mock import patch

import pytest

from homeassistant.components.assist_pipeline import PipelineStage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import ENTITY_ID
from .conftest import MockAssistSatellite

from tests.common import MockUser
from tests.typing import WebSocketGenerator


async def test_intercept_wake_word(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test intercepting a wake word."""
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )
    msg = await ws_client.receive_json()
    assert msg["success"]
    assert msg["result"] is None
    subscription_id = msg["id"]

    await entity.async_accept_pipeline_from_satellite(
        object(),  # type: ignore[arg-type]
        start_stage=PipelineStage.STT,
        wake_word_phrase="ok, nabu",
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert msg["id"] == subscription_id
    assert msg["type"] == "event"
    assert msg["event"] == {"wake_word_phrase": "ok, nabu"}


async def test_intercept_wake_word_requires_on_device_wake_word(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test intercepting a wake word fails if detection happens in HA."""
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert msg["success"]
    assert msg["result"] is None

    await entity.async_accept_pipeline_from_satellite(
        object(),  # type: ignore[arg-type]
        # Emulate wake word processing in Home Assistant
        start_stage=PipelineStage.WAKE_WORD,
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert not msg["success"]
    assert msg["error"] == {
        "code": "home_assistant_error",
        "message": "Only on-device wake words currently supported",
    }


async def test_intercept_wake_word_requires_wake_word_phrase(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test intercepting a wake word fails if detection happens in HA."""
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert msg["success"]
    assert msg["result"] is None

    await entity.async_accept_pipeline_from_satellite(
        object(),  # type: ignore[arg-type]
        start_stage=PipelineStage.STT,
        # We are not passing wake word phrase
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert not msg["success"]
    assert msg["error"] == {
        "code": "home_assistant_error",
        "message": "No wake word phrase provided",
    }


async def test_intercept_wake_word_require_admin(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: MockUser,
) -> None:
    """Test intercepting a wake word requires admin access."""
    # Remove admin permission and verify we're not allowed
    hass_admin_user.groups = []
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert not msg["success"]
    assert msg["error"] == {
        "code": "unauthorized",
        "message": "Unauthorized",
    }


async def test_intercept_wake_word_invalid_satellite(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test intercepting a wake word requires admin access."""
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": "assist_satellite.invalid",
        }
    )
    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_found",
        "message": "Entity not found",
    }


async def test_intercept_wake_word_twice(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test intercepting a wake word twice cancels the previous request."""
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )

    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert msg["success"]
    assert msg["result"] is None

    task = hass.async_create_task(ws_client.receive_json())

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )

    # Should get an error from previous subscription
    async with asyncio.timeout(1):
        msg = await task

    assert not msg["success"]
    assert msg["error"] == {
        "code": "home_assistant_error",
        "message": "Wake word interception already in progress",
    }

    # Response to second subscription
    async with asyncio.timeout(1):
        msg = await ws_client.receive_json()

    assert msg["success"]
    assert msg["result"] is None


async def test_intercept_wake_word_unsubscribe(
    hass: HomeAssistant,
    init_components: ConfigEntry,
    entity: MockAssistSatellite,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test that closing the websocket connection stops interception."""
    ws_client = await hass_ws_client(hass)

    await ws_client.send_json_auto_id(
        {
            "type": "assist_satellite/intercept_wake_word",
            "entity_id": ENTITY_ID,
        }
    )

    # Wait for interception to start
    for _ in range(3):
        await asyncio.sleep(0)

    async def receive_json():
        with pytest.raises(TypeError):
            # Raises TypeError when connection is closed
            await ws_client.receive_json()

    task = hass.async_create_task(receive_json())

    # Close connection
    await ws_client.close()
    await task

    with (
        patch(
            "homeassistant.components.assist_satellite.entity.async_pipeline_from_audio_stream",
        ) as mock_pipeline_from_audio_stream,
    ):
        # Start a pipeline with a wake word
        await entity.async_accept_pipeline_from_satellite(
            object(),
            wake_word_phrase="ok, nabu",  # type: ignore[arg-type]
        )

        # Wake word should not be intercepted
        mock_pipeline_from_audio_stream.assert_called_once()
