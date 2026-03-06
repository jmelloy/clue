"""Unit tests for the standalone agent_runner watchdog behavior.

Verifies that the AgentRunner preserves the ``game:{id}:agent_config`` Redis
key when the per-game task exits while the game is still active, so that the
discovery loop can restart agent management on the next poll cycle.
"""

import asyncio
import json
import sys
import os

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

# Ensure the backend package is importable when running from the tests dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.games.clue.game import ClueGame
from agent_runner import AgentRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def runner(redis):
    """An AgentRunner whose Redis client is replaced with fakeredis."""
    r = AgentRunner()
    await r.redis.aclose()
    r.redis = redis
    yield r
    await r.http.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_active_game(redis, game_id: str = "TESTGM") -> str:
    """Create a minimal Clue game in 'playing' state via fakeredis."""
    game = ClueGame(game_id, redis)
    await game.create()

    for i in range(2):
        pid = f"P{i}"
        await game.add_player(pid, f"Bot-{i}", "agent")

    await game.start()
    return game_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentRunnerConfigPreservation:
    """The agent config key must survive a task crash when game is active."""

    @pytest.mark.asyncio
    async def test_config_preserved_when_game_still_playing(self, runner, redis):
        """If _run_game exits while status=='playing', the config key stays."""
        game_id = await _create_active_game(redis)

        # Write a minimal agent config for the game
        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        config_key = f"game:{game_id}:agent_config"
        await redis.set(config_key, json.dumps(config), ex=86400)

        # Patch _run_agent_ws so it immediately returns (simulating agent death)
        async def _instant_return(*args, **kwargs):
            return

        runner._run_agent_ws = _instant_return

        # Run _run_game to completion — the game is still "playing"
        await runner._run_game(game_id, config)

        remaining = await redis.get(config_key)
        assert remaining is not None, (
            "Agent config key must be preserved when game is still active "
            "so the discovery loop can restart management"
        )

    @pytest.mark.asyncio
    async def test_config_deleted_when_game_finished(self, runner, redis):
        """If _run_game exits after the game ends, the config key is removed."""
        game_id = await _create_active_game(redis)

        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        config_key = f"game:{game_id}:agent_config"
        await redis.set(config_key, json.dumps(config), ex=86400)

        # Patch _run_agent_ws to mark the game finished before returning
        async def _finish_game_then_return(gid, pid, agent):
            g = ClueGame(gid, redis)
            state = await g.get_state()
            state.status = "finished"
            await g._save_state(state)

        runner._run_agent_ws = _finish_game_then_return

        await runner._run_game(game_id, config)

        remaining = await redis.get(config_key)
        assert remaining is None, (
            "Agent config key must be deleted when the game has ended"
        )

    @pytest.mark.asyncio
    async def test_finished_game_removed_from_managed_on_rediscovery(
        self, runner, redis
    ):
        """A stale config for a finished/missing game is cleaned up on discovery."""
        game_id = "STALE1"

        # Write a config key but no matching game state
        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        config_key = f"game:{game_id}:agent_config"
        await redis.set(config_key, json.dumps(config), ex=86400)

        # _discover_games should clean up the stale key
        await runner._discover_games()

        remaining = await redis.get(config_key)
        assert remaining is None, (
            "Discovery should delete config key for games that no longer exist"
        )
        assert game_id not in runner.managed_games
