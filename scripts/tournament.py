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
import logging
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Add backend/ to path so we can import app.*
_backend = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend))

import fakeredis.aioredis as fakeredis  # noqa: E402

from app.games.clue.game import ClueGame  # noqa: E402
from app.games.clue.agents import (  # noqa: E402
    RandomAgent,
    WandererAgent,
    LLMAgent,
    INFERENCE_NONE,
    INFERENCE_BASIC,
    INFERENCE_STANDARD,
    INFERENCE_ADVANCED,
    INFERENCE_LEVELS,
)
from app.games.clue.models import ShowCardAction, EndTurnAction  # noqa: E402

logger = logging.getLogger(__name__)

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
    agent_type: str = "random"  # "random" or "llm"
    secret_passage_chance: float | None = None
    explore_chance: float | None = None
    chat_frequency: float | None = None
    label: str = ""  # Human-readable label for tracking
    model: str | None = None  # LLM model override (main decisions)
    nano_model: str | None = None  # LLM model override (quick ops)

    @property
    def display_label(self) -> str:
        return self.label or self.inference_level


# ---------------------------------------------------------------------------
# LLM model presets
# ---------------------------------------------------------------------------

LLM_PRESETS: dict[str, dict[str, str | None]] = {
    "nano": {
        "model": "gpt-5-nano",
        "nano_model": "gpt-5-nano",
        "description": "All nano — cheapest/fastest, both decisions and show_card",
    },
    "mini": {
        "model": "gpt-5-mini",
        "nano_model": "gpt-5-mini",
        "description": "All mini — mid-tier for both decisions and show_card",
    },
    "standard": {
        "model": "gpt-5-mini",
        "nano_model": "gpt-5-nano",
        "description": "Standard mix — mini for decisions, nano for show_card",
    },
    "large": {
        "model": "gpt-5.4",
        "nano_model": "gpt-5-mini",
        "description": "Large — gpt-5.4 for decisions, mini for show_card",
    },
    "large-nano": {
        "model": "gpt-5.4",
        "nano_model": "gpt-5-nano",
        "description": "Large + nano — gpt-5.4 for decisions, nano for show_card",
    },
    "random": {
        "model": None,  # randomly chosen per agent
        "nano_model": None,
        "description": "Random — each agent gets a randomly chosen model preset",
    },
}

_RANDOM_PRESET_POOL = ["nano", "mini", "standard", "large"]


def apply_llm_preset(config: "AgentConfig", preset_name: str) -> "AgentConfig":
    """Apply a named LLM preset to an AgentConfig, returning a new config."""
    if preset_name == "random":
        preset_name = random.choice(_RANDOM_PRESET_POOL)
    preset = LLM_PRESETS[preset_name]
    config.model = preset["model"]
    config.nano_model = preset["nano_model"]
    if not config.label:
        config.label = f"llm-{preset_name}"
    return config


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
    owns_redis = redis is None
    if owns_redis:
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
    agents: dict[str, RandomAgent | WandererAgent | LLMAgent] = {}
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
        elif cfg.agent_type == "llm":
            agents[p.id] = LLMAgent(
                player_id=p.id,
                character=p.character,
                cards=cards,
                inference_level=cfg.inference_level,
                model=cfg.model,
                nano_model=cfg.nano_model,
            )
            agent_levels[p.id] = cfg.display_label
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
        pid: a
        for pid, a in agents.items()
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
            try:
                result = await game.process_action(pid, action)
            except ValueError as e:
                # LLM agents may produce invalid actions (e.g. wrong room);
                # retry once with the error detail so the agent can correct.
                logger.warning("Action rejected for %s: %s – retrying", pid, e)
                action = await agent.decide_action(
                    state, player_state, errors=1, rejection_detail=str(e)
                )
                try:
                    result = await game.process_action(pid, action)
                except ValueError as e2:
                    # Still failing – force an end_turn to avoid crashing
                    logger.warning(
                        "Retry also rejected for %s: %s – forcing end_turn",
                        pid,
                        e2,
                    )
                    result = await game.process_action(pid, EndTurnAction())

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
                        action.suspect,
                        action.weapon,
                        action.room,
                    )

            if action.type == "accuse":
                total_accusations += 1
                correct = getattr(result, "correct", False)
                if not correct:
                    wrong_accusations += 1

        state = await game.get_state()
        actions_taken += 1

    if owns_redis:
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
    roster: list[str] | list[AgentConfig] | None = None,
    num_players: int = 3,
    round_robin: bool = True,
    quiet: bool = False,
    num_llm: int = 0,
    llm_level: str | None = None,
    llm_preset: str = "standard",
) -> dict:
    """Run the full tournament and return results.

    Parameters
    ----------
    num_games : int
        Total number of games to run.
    roster : list[str] | list[AgentConfig] | None
        Fixed roster of inference levels or AgentConfig objects.
        If None, uses round-robin across all matchups.
    num_players : int
        Number of players per game (only used for round-robin).
    round_robin : bool
        If True and no fixed roster, cycle through all matchup compositions.
    quiet : bool
        Suppress per-game output.
    num_llm : int
        Number of LLM agents per game. In round-robin mode, their inference
        level is randomly chosen per game (unless llm_level is fixed).
    llm_level : str | None
        Fixed inference level for LLM agents. If None, randomly chosen per game.
    llm_preset : str
        LLM model preset name (see LLM_PRESETS). Controls which models are
        used for main decisions vs quick operations.
    """
    # Collect all unique labels for stats tracking
    all_labels: set[str] = set()
    if roster:
        for entry in roster:
            if isinstance(entry, AgentConfig):
                all_labels.add(entry.display_label)
            else:
                all_labels.add(entry)
    if not all_labels:
        all_labels = set(INFERENCE_LEVELS)

    stats: dict[str, PlayerStats] = {}
    for label in all_labels | set(INFERENCE_LEVELS):
        stats[label] = PlayerStats(inference_level=label)

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

        # In round-robin mode with LLM agents, build per-game configs
        # with randomly chosen inference levels for the LLM slots
        if num_llm > 0 and not roster:
            configs = []
            for j, entry in enumerate(shuffled):
                level = entry if isinstance(entry, str) else entry.inference_level
                if j < num_llm:
                    ll = llm_level or random.choice(list(INFERENCE_LEVELS))
                    cfg = AgentConfig(
                        inference_level=ll,
                        agent_type="llm",
                        label=f"llm-{llm_preset}({ll})",
                    )
                    apply_llm_preset(cfg, llm_preset)
                    configs.append(cfg)
                else:
                    configs.append(AgentConfig(inference_level=level, label=level))
            shuffled = configs

        result = await run_single_game(f"T{i}", shuffled)

        if not result["finished"]:
            games_timeout += 1
            if not quiet:
                print(f"  Game {i}: TIMEOUT after {result['actions']} actions")
            continue

        games_finished += 1
        winner_level = result["winner_level"]

        # Update per-level stats (lazily create for wanderers / custom labels)
        levels_in_game = list(result["agent_levels"].values())
        for level in levels_in_game:
            if level not in stats:
                stats[level] = PlayerStats(inference_level=level)
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

        if not quiet and (i + 1) % (max(num_games // 10, 1)) == 0:
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

    print(
        f"  {'Level':<12} {'ELO':>6} {'Wins':>6} {'Games':>6} {'Win%':>7} {'Avg Turns':>10}"
    )
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
        "--games",
        "-n",
        type=int,
        default=1000,
        help="Number of games to run (default: 1000)",
    )
    parser.add_argument(
        "--players",
        "-p",
        type=int,
        default=3,
        help="Players per game for round-robin mode (default: 3)",
    )
    parser.add_argument(
        "--roster",
        "-r",
        type=str,
        default=None,
        help="Comma-separated inference levels (e.g. 'advanced,standard,none'). "
        "Overrides round-robin.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-game output.",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--llm",
        type=int,
        default=0,
        metavar="N",
        help="Include N LLM agents in each game. They replace the first N "
        "roster slots. Requires LLM_API_KEY env var.",
    )
    parser.add_argument(
        "--llm-level",
        type=str,
        help="Inference level for LLM agents (default: advanced).",
    )
    parser.add_argument(
        "--llm-preset",
        type=str,
        default="standard",
        choices=list(LLM_PRESETS.keys()),
        help="LLM model preset: "
        + ", ".join(f"'{k}' ({v['description']})" for k, v in LLM_PRESETS.items())
        + " (default: standard).",
    )
    parser.add_argument(
        "--style-test",
        action="store_true",
        help="Test style parameters (secret_passage_chance, explore_chance) "
        "instead of inference levels.",
    )
    parser.add_argument(
        "--style-level",
        type=str,
        default="standard",
        help="Inference level to use for style tests (default: standard).",
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.llm > 0:
        import os

        if not os.getenv("LLM_API_KEY"):
            parser.error("--llm requires LLM_API_KEY environment variable")

    if args.style_test:
        print(
            f"Running {args.games} style-parameter games at inference={args.style_level}..."
        )
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

    # Build AgentConfig roster with LLM agents if requested (fixed roster only)
    config_roster: list[AgentConfig] | None = None
    if args.llm > 0 and roster:
        # Replace first N slots with LLM agents
        config_roster = []
        for i, level in enumerate(roster):
            if i < args.llm:
                ll = args.llm_level or random.choice(INFERENCE_LEVELS)
                cfg = AgentConfig(
                    inference_level=ll,
                    agent_type="llm",
                    label=f"llm-{args.llm_preset}({ll})",
                )
                apply_llm_preset(cfg, args.llm_preset)
                config_roster.append(cfg)
            else:
                config_roster.append(
                    AgentConfig(
                        inference_level=level,
                        label=level,
                    )
                )

    print(f"Running {args.games} tournament games...")
    if config_roster:
        labels = [c.display_label for c in config_roster]
        print(f"  Fixed roster: {labels}")
    elif roster:
        print(f"  Fixed roster: {roster}")
    elif args.llm > 0:
        ll_desc = args.llm_level or "random"
        print(
            f"  Round-robin mode, {args.players} players per game, "
            f"{args.llm} LLM agent(s) with inference={ll_desc}, "
            f"preset={args.llm_preset} per game"
        )
    else:
        print(f"  Round-robin mode, {args.players} players per game")

    results = asyncio.run(
        run_tournament(
            num_games=args.games,
            roster=config_roster or roster,
            num_players=args.players,
            quiet=args.quiet,
            num_llm=args.llm if not config_roster else 0,
            llm_level=args.llm_level,
            llm_preset=args.llm_preset,
        )
    )

    print_report(results)


if __name__ == "__main__":
    main()
