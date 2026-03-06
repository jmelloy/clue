"""Unit tests for the standalone agent_runner watchdog behavior.

Covers:
- Redis distributed lock: acquisition, release, and conflict prevention
- Agent config key preservation when the game is still active
- Agent config key deletion when the game has ended
- Discovery cleanup of stale config keys
"""

import asyncio
import json
import sys
import os

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.games.clue.game import ClueGame
from agent_runner import AgentRunner, _LOCK_TTL, _RUNNER_ID, _release_lock, _renew_lock


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
# Tests: Distributed lock
# ---------------------------------------------------------------------------


class TestAgentRunnerLock:
    """The runner acquires a per-game Redis lock and releases it on exit."""

    @pytest.mark.asyncio
    async def test_lock_acquired_on_discovery(self, runner, redis):
        """Discovery sets game:{id}:agent_lock with this runner's ID."""
        game_id = await _create_active_game(redis)
        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        await redis.set(f"game:{game_id}:agent_config", json.dumps(config), ex=86400)

        # Patch _run_game so it records invocations but doesn't run real agents
        acquired_games: list[str] = []
        done_event = asyncio.Event()

        async def _fake_run_game(gid, cfg):
            acquired_games.append(gid)
            done_event.set()

        runner._run_game = _fake_run_game
        await runner._discover_games()

        # Lock is set synchronously inside _discover_games before the task runs
        lock_val = await redis.get(f"game:{game_id}:agent_lock")
        assert lock_val == _RUNNER_ID, (
            "Discovery should have set the lock to this runner's ID"
        )

        # Wait for the background task to execute
        await asyncio.wait_for(done_event.wait(), timeout=2)
        assert game_id in acquired_games

    @pytest.mark.asyncio
    async def test_locked_game_skipped_by_second_runner(self, runner, redis):
        """A game already locked by another runner is not claimed again."""
        game_id = await _create_active_game(redis)
        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        await redis.set(f"game:{game_id}:agent_config", json.dumps(config), ex=86400)

        # Simulate another runner holding the lock
        other_runner_id = "other-host:99999"
        await redis.set(f"game:{game_id}:agent_lock", other_runner_id, ex=_LOCK_TTL)

        await runner._discover_games()

        # Our runner should not have claimed the game
        assert game_id not in runner.managed_games, (
            "Runner must not manage a game already locked by a peer"
        )
        # Lock value must still belong to the other runner
        lock_val = await redis.get(f"game:{game_id}:agent_lock")
        assert lock_val == other_runner_id

    @pytest.mark.asyncio
    async def test_lock_released_when_game_exits(self, runner, redis):
        """_run_game releases the lock in its finally block."""
        game_id = await _create_active_game(redis)
        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        await redis.set(f"game:{game_id}:agent_config", json.dumps(config), ex=86400)

        # Pre-set the lock as if discovery just acquired it
        await redis.set(f"game:{game_id}:agent_lock", _RUNNER_ID, ex=_LOCK_TTL)

        async def _instant_return(*args, **kwargs):
            return

        runner._run_agent_ws = _instant_return
        await runner._run_game(game_id, config)

        lock_val = await redis.get(f"game:{game_id}:agent_lock")
        assert lock_val is None, (
            "_run_game must delete the lock in its finally block"
        )

    @pytest.mark.asyncio
    async def test_lock_not_deleted_when_held_by_other(self, runner, redis):
        """_run_game does not delete a lock it doesn't own (expired + re-acquired)."""
        game_id = await _create_active_game(redis)
        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        await redis.set(f"game:{game_id}:agent_config", json.dumps(config), ex=86400)

        # Start with our lock; then mid-run another runner takes it over
        other_id = "other-host:77777"

        async def _steal_lock_then_return(gid, pid, agent):
            # Overwrite the lock to simulate the other runner taking over
            await redis.set(f"game:{gid}:agent_lock", other_id, ex=_LOCK_TTL)

        runner._run_agent_ws = _steal_lock_then_return
        # Acquire as this runner before running
        await redis.set(f"game:{game_id}:agent_lock", _RUNNER_ID, ex=_LOCK_TTL)

        await runner._run_game(game_id, config)

        # Lock should still belong to the other runner, not be deleted
        lock_val = await redis.get(f"game:{game_id}:agent_lock")
        assert lock_val == other_id, (
            "_run_game must not delete a lock it no longer owns"
        )


# ---------------------------------------------------------------------------
# Tests: Atomic lock helpers
# ---------------------------------------------------------------------------


class TestAtomicLockHelpers:
    """_release_lock and _renew_lock are safe under concurrent ownership changes."""

    @pytest.mark.asyncio
    async def test_release_lock_deletes_own_lock(self, redis):
        """_release_lock removes the key when this runner owns it."""
        await redis.set("test:lock", _RUNNER_ID, ex=_LOCK_TTL)
        released = await _release_lock(redis, "test:lock")
        assert released is True
        assert await redis.get("test:lock") is None

    @pytest.mark.asyncio
    async def test_release_lock_ignores_foreign_lock(self, redis):
        """_release_lock does not delete a lock owned by another runner."""
        await redis.set("test:lock", "other-host:99", ex=_LOCK_TTL)
        released = await _release_lock(redis, "test:lock")
        assert released is False
        assert await redis.get("test:lock") == "other-host:99"

    @pytest.mark.asyncio
    async def test_release_lock_handles_missing_key(self, redis):
        """_release_lock returns False gracefully when the key doesn't exist."""
        released = await _release_lock(redis, "test:nonexistent")
        assert released is False

    @pytest.mark.asyncio
    async def test_renew_lock_extends_own_ttl(self, redis):
        """_renew_lock refreshes the TTL when this runner owns the key."""
        await redis.set("test:lock", _RUNNER_ID, ex=1)  # short TTL
        renewed = await _renew_lock(redis, "test:lock")
        assert renewed is True
        ttl = await redis.ttl("test:lock")
        assert ttl > 1  # TTL was extended

    @pytest.mark.asyncio
    async def test_renew_lock_ignores_foreign_lock(self, redis):
        """_renew_lock does not extend a lock owned by another runner."""
        await redis.set("test:lock", "other-host:99", ex=_LOCK_TTL)
        renewed = await _renew_lock(redis, "test:lock")
        assert renewed is False


# ---------------------------------------------------------------------------
# Tests: Config key preservation
# ---------------------------------------------------------------------------


class TestAgentRunnerConfigPreservation:
    """The agent config key must survive a task crash when game is active."""

    @pytest.mark.asyncio
    async def test_config_preserved_when_game_still_playing(self, runner, redis):
        """If _run_game exits while status=='playing', the config key stays."""
        game_id = await _create_active_game(redis)

        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        config_key = f"game:{game_id}:agent_config"
        await redis.set(config_key, json.dumps(config), ex=86400)
        await redis.set(f"game:{game_id}:agent_lock", _RUNNER_ID, ex=_LOCK_TTL)

        async def _instant_return(*args, **kwargs):
            return

        runner._run_agent_ws = _instant_return
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
        await redis.set(f"game:{game_id}:agent_lock", _RUNNER_ID, ex=_LOCK_TTL)

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

        config = {"P0": {"type": "agent", "character": "Miss Scarlett", "cards": []}}
        config_key = f"game:{game_id}:agent_config"
        await redis.set(config_key, json.dumps(config), ex=86400)

        await runner._discover_games()

        remaining = await redis.get(config_key)
        assert remaining is None, (
            "Discovery should delete config key for games that no longer exist"
        )
        assert game_id not in runner.managed_games
