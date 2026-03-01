#!/usr/bin/env python3
"""Dump Clue game information and logs from Redis.

Usage:
    python scripts/dump_game.py --list-games
    python scripts/dump_game.py <GAME_ID>
    python scripts/dump_game.py <GAME_ID> --json

Examples:
    python scripts/dump_game.py --list-games
    python scripts/dump_game.py ABC123
    python scripts/dump_game.py --list-games --json
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (default output is human-readable text)",
    )
    return parser.parse_args()


def _pretty_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _print_game_dump_text(output: dict[str, Any]) -> None:
    print(f"Game: {output['game_id']}")
    print(f"Redis: {output['redis_url']}")

    ttl = output.get("ttl_seconds", {})
    print("TTL (seconds):")
    print(
        f"  state={ttl.get('state')} log={ttl.get('log')} chat={ttl.get('chat')} solution={ttl.get('solution')}"
    )

    state = output.get("state")
    if isinstance(state, dict):
        players = state.get("players", [])
        print("State summary:")
        print(
            f"  status={state.get('status')} turn={state.get('turn_number')} whose_turn={state.get('whose_turn')} players={len(players)}"
        )
        if players:
            print("Players:")
            for player in players:
                print(
                    "  - "
                    f"{player.get('id')} name={player.get('name')} type={player.get('type')} "
                    f"character={player.get('character')} active={player.get('active')}"
                )
    else:
        print(f"State: {_pretty_json(state)}")

    log_entries = output.get("log", [])
    print(f"Log entries: {len(log_entries)}")
    for index, entry in enumerate(log_entries, start=1):
        if isinstance(entry, dict):
            timestamp = entry.get("timestamp", "-")
            entry_type = entry.get("type", "-")
            rest = {k: v for k, v in entry.items() if k not in {"timestamp", "type"}}
            print(
                f"  {index:>3}. [{timestamp}] {entry_type} {_pretty_json(rest) if rest else ''}".rstrip()
            )
        else:
            print(f"  {index:>3}. {entry}")

    if "chat" in output:
        chat_entries = output["chat"]
        print(f"Chat messages: {len(chat_entries)}")
        for index, message in enumerate(chat_entries, start=1):
            if isinstance(message, dict):
                print(
                    f"  {index:>3}. [{message.get('timestamp', '-')}] "
                    f"{message.get('player_id')}: {message.get('text')}"
                )
            else:
                print(f"  {index:>3}. {message}")

    if "solution" in output:
        print(f"Solution: {_pretty_json(output['solution'])}")

    if "cards_by_player" in output:
        cards = output["cards_by_player"]
        print("Cards by player:")
        if not cards:
            print("  (none)")
        for player_id, data in cards.items():
            print(
                f"  - {player_id}: ttl={data.get('ttl')} cards={_pretty_json(data.get('cards'))}"
            )


def _print_list_games_text(redis_url: str, games: list[dict[str, Any]]) -> None:
    print(f"Redis: {redis_url}")
    print(f"Games: {len(games)}")
    if not games:
        return

    for game in games:
        print(
            "  - "
            f"{game.get('game_id')} status={game.get('status')} "
            f"players={game.get('player_count')} ttl={game.get('ttl')}"
        )


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
    as_json: bool,
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

        if as_json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            _print_game_dump_text(output)
        return 0
    finally:
        await redis_client.aclose()


async def list_games(redis_url: str, as_json: bool) -> int:
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

        if as_json:
            print(
                json.dumps(
                    {"redis_url": redis_url, "games": games}, indent=2, sort_keys=True
                )
            )
        else:
            _print_list_games_text(redis_url, games)
        return 0
    finally:
        await redis_client.aclose()


async def _main() -> int:
    args = _parse_args()
    if args.list_games:
        return await list_games(redis_url=args.redis_url, as_json=args.json)

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
        as_json=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
