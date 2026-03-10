#!/usr/bin/env python3
"""ELO-style tournament runner for Clue agents.

Runs N games with configurable agent compositions to measure relative
strength of different inference levels.  Outputs ELO ratings, win rates,
and per-matchup statistics.

Usage:
    # Run from the backend directory (needs app/ on the path):
    cd backend && python ../scripts/tournament.py

    # 500 games, 4 players each, custom composition:
    python ../scripts/tournament.py --games 500 --players 4

    # Specific matchup: 2 advanced vs 2 none
    python ../scripts/tournament.py --roster advanced,advanced,none,none

    # Full round-robin across all inference levels (default)
    python ../scripts/tournament.py --games 1000

    # Quick smoke test
    python ../scripts/tournament.py --games 10 --quiet

Requires: fakeredis (pip install fakeredis)
"""

import argparse
import asyncio
import itertools
import json
import math
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Add backend/ to path so we can import app.*
_backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend))

import fakeredis.aioredis as fakeredis  # noqa: E402

from app.games.clue.game import ClueGame, SUSPECTS, WEAPONS, ROOMS  # noqa: E402
from app.games.clue.agents import (  # noqa: E402
    RandomAgent,
    WandererAgent,
    INFERENCE_NONE,
    INFERENCE_BASIC,
    INFERENCE_STANDARD,
    INFERENCE_ADVANCED,
    INFERENCE_LEVELS,
)
from app.games.clue.models import ShowCardAction  # noqa: E402

MAX_TURNS = 2000


# ---------------------------------------------------------------------------
# ELO rating system
# ---------------------------------------------------------------------------

K_FACTOR = 32  # Standard K-factor for rating updates
DEFAULT_ELO = 1500


def expected_score(rating_a: float, rating_b: float) -> float:
    """Expected score of player A vs player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    winner_rating: float, loser_rating: float, k: float = K_FACTOR
) -> tuple[float, float]:
    """Return (new_winner_rating, new_loser_rating) after a win."""
    e_win = expected_score(winner_rating, loser_rating)
    e_lose = expected_score(loser_rating, winner_rating)
    new_winner = winner_rating + k * (1.0 - e_win)
    new_loser = loser_rating + k * (0.0 - e_lose)
    return new_winner, new_loser


# ---------------------------------------------------------------------------
# Player tracking
# ---------------------------------------------------------------------------


@dataclass
class PlayerStats:
    """Aggregate stats for one inference-level profile."""

    inference_level: str
    elo: float = DEFAULT_ELO
    wins: int = 0
    losses: int = 0
    games: int = 0
    total_turns_to_win: int = 0
    wrong_accusations: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def avg_turns_to_win(self) -> float:
        return self.total_turns_to_win / self.wins if self.wins else 0.0


# ---------------------------------------------------------------------------
# Game runner (headless — no Redis server needed)
# ---------------------------------------------------------------------------


@dataclass
class AgentConfig:
    """Configuration for a single agent in a tournament game."""

    inference_level: str = INFERENCE_STANDARD
    secret_passage_chance: float | None = None
    explore_chance: float | None = None
    chat_frequency: float | None = None
    label: str = ""  # Human-readable label for tracking

    @property
    def display_label(self) -> str:
        return self.label or self.inference_level


async def run_single_game(
    game_id: str,
    roster: list[str | AgentConfig],
    redis=None,
) -> dict:
    """Run one complete Clue game and return results.

    Parameters
    ----------
    game_id : str
        Unique game identifier.
    roster : list[str | AgentConfig]
        List of inference levels (str) or AgentConfig objects.
    redis : optional
        FakeRedis instance (created if not provided).

    Returns
    -------
    dict with keys: winner, winner_level, turns, actions, accusations,
                    wrong_accusations, finished, agent_levels
    """
    if redis is None:
        redis = fakeredis.FakeRedis(decode_responses=True)

    # Normalize roster to AgentConfig objects
    configs: list[AgentConfig] = []
    for entry in roster:
        if isinstance(entry, str):
            configs.append(AgentConfig(inference_level=entry))
        else:
            configs.append(entry)

    game = ClueGame(game_id, redis)
    await game.create()

    # Add players — all as "agent" type
    player_ids = []
    for i in range(len(configs)):
        pid = f"P{i}"
        await game.add_player(pid, f"Bot-{i}", "agent")
        player_ids.append(pid)

    state = await game.start()

    # Create agents with specified configs
    agents: dict[str, RandomAgent | WandererAgent] = {}
    agent_levels: dict[str, str] = {}
    for idx, p in enumerate(state.players):
        cards = await game._load_player_cards(p.id)
        if idx < len(configs):
            cfg = configs[idx]
        else:
            cfg = AgentConfig()  # default for wanderer fillers

        if p.type == "wanderer":
            agents[p.id] = WandererAgent(
                player_id=p.id,
                character=p.character,
                cards=cards,
            )
            agent_levels[p.id] = "wanderer"
        else:
            agents[p.id] = RandomAgent(
                player_id=p.id,
                character=p.character,
                cards=cards,
                inference_level=cfg.inference_level,
                secret_passage_chance=cfg.secret_passage_chance,
                explore_chance=cfg.explore_chance,
                chat_frequency=cfg.chat_frequency,
            )
            agent_levels[p.id] = cfg.display_label

    # Show one random card to each wanderer
    real_agents = {
        pid: a for pid, a in agents.items()
        if a.agent_type != "wanderer" and a.own_cards
    }
    if real_agents:
        for pid, a in agents.items():
            if a.agent_type == "wanderer":
                donor_pid, donor = random.choice(list(real_agents.items()))
                card = random.choice(list(donor.own_cards))
                a.observe_shown_card(card, shown_by=donor_pid)

    # Share player names
    player_names = {p.id: p.name for p in state.players}
    for a in agents.values():
        a.player_names = player_names

    # Run game loop
    actions_taken = 0
    wrong_accusations = 0
    total_accusations = 0

    while state.status == "playing" and actions_taken < MAX_TURNS:
        pending = state.pending_show_card
        if pending:
            pid = pending.player_id
            agent = agents[pid]
            suggesting_pid = pending.suggesting_player_id
            matching = pending.matching_cards
            card = await agent.decide_show_card(matching, suggesting_pid)
            action = ShowCardAction(card=card)
            result = await game.process_action(pid, action)

            agents[suggesting_pid].observe_shown_card(card, shown_by=pid)
            suspect = getattr(result, "suspect", "")
            weapon = getattr(result, "weapon", "")
            room = getattr(result, "room", "")
            for aid, a in agents.items():
                if aid not in (suggesting_pid, pid) and suspect and weapon and room:
                    a.observe_card_shown_to_other(
                        shown_by=pid,
                        shown_to=suggesting_pid,
                        suspect=suspect,
                        weapon=weapon,
                        room=room,
                    )
        else:
            pid = state.whose_turn
            agent = agents[pid]
            player_state = await game.get_player_state(pid)
            action = await agent.decide_action(state, player_state)
            result = await game.process_action(pid, action)

            if action.type == "suggest":
                shown_by = getattr(result, "pending_show_by", None)
                players_without = getattr(result, "players_without_match", [])
                for aid, a in agents.items():
                    a.observe_suggestion(
                        suggesting_player_id=pid,
                        suspect=action.suspect,
                        weapon=action.weapon,
                        room=action.room,
                        shown_by=shown_by,
                        players_without_match=players_without,
                    )
                if shown_by is None:
                    agent.observe_suggestion_no_show(
                        action.suspect, action.weapon, action.room,
                    )

            if action.type == "accuse":
                total_accusations += 1
                correct = getattr(result, "correct", False)
                if not correct:
                    wrong_accusations += 1

        state = await game.get_state()
        actions_taken += 1

    await redis.aclose()

    return {
        "winner": state.winner,
        "winner_level": agent_levels.get(state.winner, "?") if state.winner else None,
        "turns": state.turn_number if hasattr(state, "turn_number") else actions_taken,
        "actions": actions_taken,
        "accusations": total_accusations,
        "wrong_accusations": wrong_accusations,
        "finished": state.status == "finished",
        "agent_levels": agent_levels,
    }


# ---------------------------------------------------------------------------
# Tournament orchestrator
# ---------------------------------------------------------------------------


def generate_round_robin_rosters(
    num_players: int = 3,
) -> list[list[str]]:
    """Generate all unique matchup compositions for the given player count.

    Returns rosters like ['none','none','standard'], ['none','basic','advanced'], etc.
    Uses combinations with replacement so each unique composition appears once.
    """
    levels = [INFERENCE_NONE, INFERENCE_BASIC, INFERENCE_STANDARD, INFERENCE_ADVANCED]
    rosters = list(itertools.combinations_with_replacement(levels, num_players))
    # Convert tuples to lists
    return [list(r) for r in rosters]


async def run_tournament(
    num_games: int = 1000,
    roster: list[str] | None = None,
    num_players: int = 3,
    round_robin: bool = True,
    quiet: bool = False,
) -> dict:
    """Run the full tournament and return results.

    Parameters
    ----------
    num_games : int
        Total number of games to run.
    roster : list[str] | None
        Fixed roster of inference levels (e.g. ["advanced", "none", "standard"]).
        If None, uses round-robin across all matchups.
    num_players : int
        Number of players per game (only used for round-robin).
    round_robin : bool
        If True and no fixed roster, cycle through all matchup compositions.
    quiet : bool
        Suppress per-game output.
    """
    stats: dict[str, PlayerStats] = {}
    for level in INFERENCE_LEVELS:
        stats[level] = PlayerStats(inference_level=level)

    # Matchup-specific tracking: (level_a, level_b) -> {wins_a, wins_b}
    matchup_wins: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    # Build roster schedule
    if roster:
        rosters = [roster] * num_games
    elif round_robin:
        all_rosters = generate_round_robin_rosters(num_players)
        # Repeat the roster list to fill num_games, shuffled per cycle
        rosters = []
        while len(rosters) < num_games:
            batch = list(all_rosters)
            random.shuffle(batch)
            rosters.extend(batch)
        rosters = rosters[:num_games]
    else:
        # Random composition
        levels = list(INFERENCE_LEVELS)
        rosters = [
            [random.choice(levels) for _ in range(num_players)]
            for _ in range(num_games)
        ]

    start_time = time.time()
    games_finished = 0
    games_timeout = 0

    for i, game_roster in enumerate(rosters):
        # Shuffle seats so position bias is controlled
        shuffled = list(game_roster)
        random.shuffle(shuffled)

        result = await run_single_game(f"T{i}", shuffled)

        if not result["finished"]:
            games_timeout += 1
            if not quiet:
                print(f"  Game {i}: TIMEOUT after {result['actions']} actions")
            continue

        games_finished += 1
        winner_level = result["winner_level"]

        # Update per-level stats
        levels_in_game = list(result["agent_levels"].values())
        for level in levels_in_game:
            stats[level].games += 1

        if winner_level:
            stats[winner_level].wins += 1
            stats[winner_level].total_turns_to_win += result["turns"]

            # Mark losses for non-winners
            for pid, level in result["agent_levels"].items():
                if pid != result["winner"]:
                    stats[level].losses += 1

            # ELO updates: winner vs each loser
            for pid, level in result["agent_levels"].items():
                if pid != result["winner"] and level != winner_level:
                    w_elo = stats[winner_level].elo
                    l_elo = stats[level].elo
                    new_w, new_l = update_elo(w_elo, l_elo)
                    stats[winner_level].elo = new_w
                    stats[level].elo = new_l

            # Track matchup results
            for pid, level in result["agent_levels"].items():
                if pid != result["winner"]:
                    key = tuple(sorted([winner_level, level]))
                    matchup_wins[key][winner_level] += 1

        if not quiet and (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            print(f"  {i + 1}/{num_games} games ({rate:.1f} games/sec)")

    elapsed = time.time() - start_time

    return {
        "stats": stats,
        "matchup_wins": dict(matchup_wins),
        "games_finished": games_finished,
        "games_timeout": games_timeout,
        "elapsed": elapsed,
        "num_games": num_games,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(results: dict):
    """Print a formatted tournament report."""
    stats = results["stats"]
    matchup_wins = results["matchup_wins"]

    print("\n" + "=" * 70)
    print("  CLUE AGENT TOURNAMENT RESULTS")
    print("=" * 70)
    print(
        f"  Games: {results['games_finished']} finished, "
        f"{results['games_timeout']} timeouts, "
        f"{results['elapsed']:.1f}s elapsed"
    )
    print()

    # Sort by ELO descending
    sorted_stats = sorted(stats.values(), key=lambda s: s.elo, reverse=True)

    print(f"  {'Level':<12} {'ELO':>6} {'Wins':>6} {'Games':>6} {'Win%':>7} {'Avg Turns':>10}")
    print("  " + "-" * 53)
    for s in sorted_stats:
        if s.games == 0:
            continue
        print(
            f"  {s.inference_level:<12} {s.elo:>6.0f} {s.wins:>6} "
            f"{s.games:>6} {s.win_rate:>6.1%} {s.avg_turns_to_win:>10.1f}"
        )

    # Matchup matrix
    levels_with_games = [s.inference_level for s in sorted_stats if s.games > 0]
    if matchup_wins and len(levels_with_games) > 1:
        print()
        print("  HEAD-TO-HEAD WIN RATES:")
        print(f"  {'':>12}", end="")
        for level in levels_with_games:
            print(f" {level[:8]:>8}", end="")
        print()
        print("  " + "-" * (12 + 9 * len(levels_with_games)))

        for row_level in levels_with_games:
            print(f"  {row_level:<12}", end="")
            for col_level in levels_with_games:
                if row_level == col_level:
                    print(f" {'---':>8}", end="")
                    continue
                key = tuple(sorted([row_level, col_level]))
                data = matchup_wins.get(key, {})
                row_wins = data.get(row_level, 0)
                col_wins = data.get(col_level, 0)
                total = row_wins + col_wins
                if total == 0:
                    print(f" {'N/A':>8}", end="")
                else:
                    rate = row_wins / total
                    print(f" {rate:>7.1%}", end="")
            print()

    print()
    print("  DIFFICULTY TIERS (suggested):")
    for s in sorted_stats:
        if s.games == 0:
            continue
        if s.elo >= 1550:
            tier = "HARD"
        elif s.elo >= 1480:
            tier = "MEDIUM"
        else:
            tier = "EASY"
        print(f"    {s.inference_level:<12} -> {tier} (ELO {s.elo:.0f})")

    print()

    # JSON summary for programmatic use
    summary = {
        "ratings": {
            s.inference_level: {
                "elo": round(s.elo),
                "wins": s.wins,
                "games": s.games,
                "win_rate": round(s.win_rate, 3),
                "avg_turns_to_win": round(s.avg_turns_to_win, 1),
            }
            for s in sorted_stats
            if s.games > 0
        },
        "games_finished": results["games_finished"],
        "elapsed_seconds": round(results["elapsed"], 1),
    }
    print("  JSON summary:")
    print("  " + json.dumps(summary, indent=2).replace("\n", "\n  "))
    print()


# ---------------------------------------------------------------------------
# Style parameter analysis
# ---------------------------------------------------------------------------


async def run_style_tournament(
    num_games: int = 200,
    inference_level: str = INFERENCE_STANDARD,
    quiet: bool = False,
) -> dict:
    """Test different style parameter combinations at a fixed inference level.

    Creates named agent profiles with different secret_passage_chance,
    explore_chance values and pits them against each other.
    """
    # Define style profiles to test
    profiles: dict[str, AgentConfig] = {
        "explorer": AgentConfig(
            inference_level=inference_level,
            secret_passage_chance=0.75,
            explore_chance=0.75,
            label="explorer",
        ),
        "cautious": AgentConfig(
            inference_level=inference_level,
            secret_passage_chance=0.25,
            explore_chance=0.25,
            label="cautious",
        ),
        "passage_lover": AgentConfig(
            inference_level=inference_level,
            secret_passage_chance=0.99,
            explore_chance=0.50,
            label="passage_lover",
        ),
        "passage_hater": AgentConfig(
            inference_level=inference_level,
            secret_passage_chance=0.01,
            explore_chance=0.50,
            label="passage_hater",
        ),
        "random_style": AgentConfig(
            inference_level=inference_level,
            # None = random from [0.25, 0.50, 0.75]
            secret_passage_chance=None,
            explore_chance=None,
            label="random_style",
        ),
        "balanced": AgentConfig(
            inference_level=inference_level,
            secret_passage_chance=0.50,
            explore_chance=0.50,
            label="balanced",
        ),
    }

    profile_names = list(profiles.keys())
    stats: dict[str, PlayerStats] = {
        name: PlayerStats(inference_level=name) for name in profile_names
    }
    matchup_wins: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    # Generate matchups: all 3-player combinations of profiles
    matchups = list(itertools.combinations_with_replacement(profile_names, 3))
    rosters = []
    while len(rosters) < num_games:
        batch = list(matchups)
        random.shuffle(batch)
        rosters.extend(batch)
    rosters = rosters[:num_games]

    start_time = time.time()
    games_finished = 0
    games_timeout = 0

    for i, matchup in enumerate(rosters):
        configs = [profiles[name] for name in matchup]
        random.shuffle(configs)

        result = await run_single_game(f"S{i}", configs)

        if not result["finished"]:
            games_timeout += 1
            continue

        games_finished += 1
        winner_label = result.get("winner_level")

        levels_in_game = list(result["agent_levels"].values())
        for label in levels_in_game:
            if label in stats:
                stats[label].games += 1

        if winner_label and winner_label in stats:
            stats[winner_label].wins += 1
            stats[winner_label].total_turns_to_win += result["turns"]

            for pid, label in result["agent_levels"].items():
                if pid != result["winner"] and label in stats:
                    stats[label].losses += 1

            # ELO
            for pid, label in result["agent_levels"].items():
                if pid != result["winner"] and label != winner_label:
                    if label in stats and winner_label in stats:
                        w_elo = stats[winner_label].elo
                        l_elo = stats[label].elo
                        new_w, new_l = update_elo(w_elo, l_elo)
                        stats[winner_label].elo = new_w
                        stats[label].elo = new_l

            for pid, label in result["agent_levels"].items():
                if pid != result["winner"]:
                    key = tuple(sorted([winner_label, label]))
                    matchup_wins[key][winner_label] += 1

        if not quiet and (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            print(f"  {i + 1}/{num_games} games ({rate:.1f} games/sec)")

    elapsed = time.time() - start_time
    return {
        "stats": stats,
        "matchup_wins": dict(matchup_wins),
        "games_finished": games_finished,
        "games_timeout": games_timeout,
        "elapsed": elapsed,
        "num_games": num_games,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Run ELO-style tournament for Clue agents with different inference levels."
    )
    parser.add_argument(
        "--games", "-n", type=int, default=1000,
        help="Number of games to run (default: 1000)",
    )
    parser.add_argument(
        "--players", "-p", type=int, default=3,
        help="Players per game for round-robin mode (default: 3)",
    )
    parser.add_argument(
        "--roster", "-r", type=str, default=None,
        help="Comma-separated inference levels (e.g. 'advanced,standard,none'). "
             "Overrides round-robin.",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress per-game output.",
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--style-test", action="store_true",
        help="Test style parameters (secret_passage_chance, explore_chance) "
             "instead of inference levels.",
    )
    parser.add_argument(
        "--style-level", type=str, default="standard",
        help="Inference level to use for style tests (default: standard).",
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.style_test:
        print(f"Running {args.games} style-parameter games at inference={args.style_level}...")
        results = asyncio.run(
            run_style_tournament(
                num_games=args.games,
                inference_level=args.style_level,
                quiet=args.quiet,
            )
        )
        print_report(results)
        return

    roster = None
    if args.roster:
        roster = [level.strip() for level in args.roster.split(",")]
        for level in roster:
            if level not in INFERENCE_LEVELS:
                parser.error(
                    f"Invalid inference level '{level}'. "
                    f"Must be one of: {INFERENCE_LEVELS}"
                )

    print(f"Running {args.games} tournament games...")
    if roster:
        print(f"  Fixed roster: {roster}")
    else:
        print(f"  Round-robin mode, {args.players} players per game")

    results = asyncio.run(
        run_tournament(
            num_games=args.games,
            roster=roster,
            num_players=args.players,
            quiet=args.quiet,
        )
    )

    print_report(results)


if __name__ == "__main__":
    main()
