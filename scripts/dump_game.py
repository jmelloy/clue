#!/usr/bin/env python3
"""Dump Clue game information and logs from Redis.

Usage:
    python scripts/dump_game.py --list-games
    python scripts/dump_game.py <GAME_ID>

Examples:
    python scripts/dump_game.py --list-games
    python scripts/dump_game.py ABC123
    python scripts/dump_game.py ABC123 --show-chat --show-cards
    REDIS_URL=redis://localhost:6379 python scripts/dump_game.py ABC123 --show-solution
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any


DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dump game information and logs for a Clue game stored in Redis.",
    )
    parser.add_argument("game_id", nargs="?", help="Game ID (e.g. ABC123)")
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="List all game IDs currently present in Redis",
    )
    parser.add_argument(
        "--redis-url",
        default=DEFAULT_REDIS_URL,
        help=f"Redis connection URL (default: {DEFAULT_REDIS_URL})",
    )
    parser.add_argument(
        "--show-chat",
        action="store_true",
        help="Include chat messages from game:{id}:chat",
    )
    parser.add_argument(
        "--show-solution",
        action="store_true",
        help="Include hidden solution from game:{id}:solution",
    )
    parser.add_argument(
        "--show-cards",
        action="store_true",
        help="Include each player's dealt cards (if game state is present)",
    )
    return parser.parse_args()


async def _get_json(redis_client: Any, key: str) -> Any | None:
    raw = await redis_client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def _get_json_list(redis_client: Any, key: str) -> list[Any]:
    rows = await redis_client.lrange(key, 0, -1)
    out: list[Any] = []
    for row in rows:
        try:
            out.append(json.loads(row))
        except json.JSONDecodeError:
            out.append(row)
    return out


async def dump_game(
    game_id: str,
    redis_url: str,
    show_chat: bool,
    show_solution: bool,
    show_cards: bool,
) -> int:
    try:
        import redis.asyncio as aioredis
    except ImportError:
        print(
            "ERROR: 'redis' package is required. Install with: pip install redis",
            file=sys.stderr,
        )
        return 1

    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    state_key = f"game:{game_id}"
    solution_key = f"game:{game_id}:solution"
    log_key = f"game:{game_id}:log"
    chat_key = f"game:{game_id}:chat"

    try:
        state = await _get_json(redis_client, state_key)
        log_entries = await _get_json_list(redis_client, log_key)

        if state is None and not log_entries:
            print(
                f"No game data found for game_id='{game_id}' at {redis_url}",
                file=sys.stderr,
            )
            return 1

        output: dict[str, Any] = {
            "game_id": game_id,
            "redis_url": redis_url,
            "keys": {
                "state": state_key,
                "log": log_key,
                "chat": chat_key,
                "solution": solution_key,
            },
            "ttl_seconds": {
                "state": await redis_client.ttl(state_key),
                "log": await redis_client.ttl(log_key),
                "chat": await redis_client.ttl(chat_key),
                "solution": await redis_client.ttl(solution_key),
            },
            "state": state,
            "log": log_entries,
        }

        if show_chat:
            output["chat"] = await _get_json_list(redis_client, chat_key)

        if show_solution:
            output["solution"] = await _get_json(redis_client, solution_key)

        if show_cards:
            cards_by_player: dict[str, Any] = {}
            players = (
                (state or {}).get("players", []) if isinstance(state, dict) else []
            )
            for player in players:
                player_id = player.get("id")
                if not player_id:
                    continue
                cards_key = f"game:{game_id}:cards:{player_id}"
                cards_by_player[player_id] = {
                    "key": cards_key,
                    "ttl": await redis_client.ttl(cards_key),
                    "cards": await _get_json(redis_client, cards_key),
                }
            output["cards_by_player"] = cards_by_player

        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    finally:
        await redis_client.aclose()


async def list_games(redis_url: str) -> int:
    try:
        import redis.asyncio as aioredis
    except ImportError:
        print(
            "ERROR: 'redis' package is required. Install with: pip install redis",
            file=sys.stderr,
        )
        return 1

    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        game_ids: set[str] = set()
        async for key in redis_client.scan_iter(match="game:*"):
            parts = key.split(":")
            if len(parts) == 2 and parts[0] == "game":
                game_ids.add(parts[1])

        games: list[dict[str, Any]] = []
        for game_id in sorted(game_ids):
            state_key = f"game:{game_id}"
            state = await _get_json(redis_client, state_key)
            games.append(
                {
                    "game_id": game_id,
                    "state_key": state_key,
                    "ttl": await redis_client.ttl(state_key),
                    "status": state.get("status") if isinstance(state, dict) else None,
                    "player_count": (
                        len(state.get("players", []))
                        if isinstance(state, dict)
                        else None
                    ),
                }
            )

        print(
            json.dumps(
                {"redis_url": redis_url, "games": games}, indent=2, sort_keys=True
            )
        )
        return 0
    finally:
        await redis_client.aclose()


async def _main() -> int:
    args = _parse_args()
    if args.list_games:
        return await list_games(redis_url=args.redis_url)

    if not args.game_id:
        print(
            "ERROR: GAME_ID is required unless --list-games is used.", file=sys.stderr
        )
        return 2

    return await dump_game(
        game_id=args.game_id,
        redis_url=args.redis_url,
        show_chat=args.show_chat,
        show_solution=args.show_solution,
        show_cards=args.show_cards,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
