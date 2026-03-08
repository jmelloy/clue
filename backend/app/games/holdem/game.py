"""Texas Hold'em game logic — state machine backed by Redis."""

import json
import random
import datetime as dt
import logging

from pydantic import TypeAdapter, ValidationError

from .models import (
    AllInAction,
    AllInResult,
    BetAction,
    BetResult,
    CallAction,
    CallResult,
    Card,
    CheckAction,
    CheckResult,
    CommunityCardsLogEntry,
    FoldAction,
    FoldResult,
    HandStartedLogEntry,
    HoldemAction,
    HoldemActionResult,
    HoldemChatMessage,
    HoldemGameState,
    HoldemHandResult,
    HoldemLogEntryBase,
    HoldemPlayer,
    HoldemPlayerState,
    PlayerActionLogEntry,
    RANKS,
    RaiseAction,
    RaiseResult,
    ShowdownLogEntry,
    ShowdownResult,
    SUITS,
)
from .hand_eval import evaluate_hand, hand_name

logger = logging.getLogger(__name__)

EXPIRY = 24 * 60 * 60  # 24 hours

_action_adapter: TypeAdapter[HoldemAction] = TypeAdapter(HoldemAction)


def _build_deck() -> list[Card]:
    """Return a shuffled standard 52-card deck."""
    deck = [Card(rank=r, suit=s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


class HoldemGame:
    """Texas Hold'em game manager backed by Redis."""

    def __init__(self, game_id: str, redis_client):
        self.game_id = game_id
        self.redis = redis_client
        self._state_key = f"holdem:{game_id}"
        self._deck_key = f"holdem:{game_id}:deck"
        self._log_key = f"holdem:{game_id}:log"
        self._chat_key = f"holdem:{game_id}:chat"

    def _cards_key(self, player_id: str) -> str:
        return f"holdem:{self.game_id}:cards:{player_id}"

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _save_state(self, state: HoldemGameState):
        await self.redis.set(self._state_key, state.model_dump_json(), ex=EXPIRY)

    async def _load_state(self) -> HoldemGameState | None:
        raw = await self.redis.get(self._state_key)
        if raw is None:
            return None
        return HoldemGameState.model_validate_json(raw)

    async def _save_deck(self, deck: list[Card]):
        await self.redis.set(
            self._deck_key,
            json.dumps([c.model_dump() for c in deck]),
            ex=EXPIRY,
        )

    async def _load_deck(self) -> list[Card]:
        raw = await self.redis.get(self._deck_key)
        if raw is None:
            return []
        return [Card(**c) for c in json.loads(raw)]

    async def _save_player_cards(self, player_id: str, cards: list[Card]):
        await self.redis.set(
            self._cards_key(player_id),
            json.dumps([c.model_dump() for c in cards]),
            ex=EXPIRY,
        )

    async def _load_player_cards(self, player_id: str) -> list[Card]:
        raw = await self.redis.get(self._cards_key(player_id))
        if raw is None:
            return []
        return [Card(**c) for c in json.loads(raw)]

    async def _append_log(self, entry: HoldemLogEntryBase):
        await self.redis.rpush(self._log_key, entry.model_dump_json())
        await self.redis.expire(self._log_key, EXPIRY)

    async def add_chat_message(self, message: HoldemChatMessage):
        await self.redis.rpush(self._chat_key, message.model_dump_json())
        await self.redis.expire(self._chat_key, EXPIRY)

    async def get_chat_messages(self) -> list[HoldemChatMessage]:
        entries = await self.redis.lrange(self._chat_key, 0, -1)
        return [HoldemChatMessage.model_validate_json(e) for e in entries]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(
        self, buy_in: int = 2000, allow_rebuys: bool = False
    ) -> HoldemGameState:
        state = HoldemGameState(
            game_id=self.game_id,
            status="waiting",
            buy_in=buy_in,
            allow_rebuys=allow_rebuys,
        )
        await self._save_state(state)
        return state

    async def get_state(self) -> HoldemGameState | None:
        return await self._load_state()

    async def add_player(
        self, player_id: str, player_name: str,
        player_type: str = "human",
    ) -> HoldemPlayer:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "waiting":
            raise ValueError("Game already started")
        if len(state.players) >= 10:
            raise ValueError("Table is full (max 10)")
        if any(p.id == player_id for p in state.players):
            raise ValueError("Already joined")

        player = HoldemPlayer(
            id=player_id, name=player_name, chips=state.buy_in,
            player_type=player_type,
        )
        state.players.append(player)
        await self._save_state(state)
        return player

    async def start(self) -> HoldemGameState:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "waiting":
            raise ValueError("Game already started")
        if len(state.players) < 2:
            raise ValueError("Need at least 2 players to start")

        state.status = "playing"
        state.dealer_index = 0
        await self._save_state(state)

        # Deal the first hand
        await self._deal_new_hand(state)
        return await self._load_state()

    async def _deal_new_hand(self, state: HoldemGameState):
        """Deal a new hand — shuffle, post blinds, deal hole cards."""
        state.hand_number += 1
        state.community_cards = []
        state.pot = 0
        state.current_bet = 0
        state.betting_round = "preflop"
        state.last_raiser = None
        state.actions_this_round = 0

        # Reset per-hand player state
        for p in state.players:
            if p.active:
                p.folded = False
                p.current_bet = 0
                p.all_in = False

        # Build and save deck
        deck = _build_deck()

        # Deal 2 hole cards to each active player
        active = [p for p in state.players if p.active]
        for p in active:
            hole = [deck.pop(), deck.pop()]
            await self._save_player_cards(p.id, hole)

        await self._save_deck(deck)

        # Post blinds
        num_active = len(active)
        if num_active == 2:
            # Heads-up: dealer posts small blind, other posts big blind
            sb_idx = state.dealer_index % num_active
            bb_idx = (state.dealer_index + 1) % num_active
        else:
            sb_idx = (state.dealer_index + 1) % num_active
            bb_idx = (state.dealer_index + 2) % num_active

        sb_player = active[sb_idx]
        bb_player = active[bb_idx]

        sb_amount = min(state.small_blind, sb_player.chips)
        sb_player.chips -= sb_amount
        sb_player.current_bet = sb_amount
        if sb_player.chips == 0:
            sb_player.all_in = True
        state.pot += sb_amount

        bb_amount = min(state.big_blind, bb_player.chips)
        bb_player.chips -= bb_amount
        bb_player.current_bet = bb_amount
        if bb_player.chips == 0:
            bb_player.all_in = True
        state.pot += bb_amount

        state.current_bet = max(sb_amount, bb_amount)

        # First to act preflop: player after BB (or SB in heads-up after dealing)
        if num_active == 2:
            first_to_act_idx = sb_idx  # heads-up: SB acts first preflop
        else:
            first_to_act_idx = (bb_idx + 1) % num_active

        # Find the first player who can actually act (skip all-in players)
        first_actor_id = None
        for offset in range(num_active):
            idx = (first_to_act_idx + offset) % num_active
            if not active[idx].all_in:
                first_actor_id = active[idx].id
                break

        if first_actor_id is not None:
            state.whose_turn = first_actor_id
        # else: everyone is all-in; whose_turn stays None and we auto-advance below

        await self._save_state(state)
        await self._append_log(
            HandStartedLogEntry(
                hand_number=state.hand_number,
                dealer=active[state.dealer_index % num_active].id,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        # If no one can act (all players went all-in posting blinds), auto-advance
        if first_actor_id is None:
            await self._advance_betting_round(state)


    def get_available_actions(
        self, player_id: str, state: HoldemGameState
    ) -> list[str]:
        """Return available actions for a player."""
        if state.status != "playing":
            return []
        if state.whose_turn != player_id:
            return []

        player = next((p for p in state.players if p.id == player_id), None)
        if not player or not player.active or player.folded or player.all_in:
            return []

        actions = ["fold"]

        amount_to_call = state.current_bet - player.current_bet

        if amount_to_call <= 0:
            # No bet to match — can check
            actions.append("check")
            # Can open betting
            if player.chips > 0:
                actions.append("bet")
        else:
            # Must call or raise
            if player.chips >= amount_to_call:
                actions.append("call")
            if player.chips > amount_to_call:
                actions.append("raise")

        # Can always go all-in if they have chips
        if player.chips > 0:
            actions.append("all_in")

        return actions

    async def get_player_state(self, player_id: str) -> HoldemPlayerState | None:
        state = await self._load_state()
        if state is None:
            return None
        cards = await self._load_player_cards(player_id)
        return HoldemPlayerState(
            **state.model_dump(),
            your_cards=cards,
            your_player_id=player_id,
            available_actions=self.get_available_actions(player_id, state),
        )

    async def process_action(
        self, player_id: str, action: HoldemAction | dict
    ) -> HoldemActionResult:
        """Process a player action."""
        if isinstance(action, dict):
            action = _action_adapter.validate_python(action)

        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "playing":
            raise ValueError("Game is not in progress")
        if state.whose_turn != player_id:
            raise ValueError("It is not your turn")

        # Clear previous hand result (will be set again if this action ends a hand)
        if state.last_hand_result is not None:
            state.last_hand_result = None

        available = self.get_available_actions(player_id, state)
        if action.type not in available:
            raise ValueError(
                f"Action '{action.type}' is not available at this time"
            )

        player = next(p for p in state.players if p.id == player_id)

        if isinstance(action, FoldAction):
            result = await self._handle_fold(state, player)
        elif isinstance(action, CheckAction):
            result = await self._handle_check(state, player)
        elif isinstance(action, CallAction):
            result = await self._handle_call(state, player)
        elif isinstance(action, BetAction):
            result = await self._handle_bet(state, player, action.amount)
        elif isinstance(action, RaiseAction):
            result = await self._handle_raise(state, player, action.amount)
        elif isinstance(action, AllInAction):
            result = await self._handle_all_in(state, player)
        else:
            raise ValueError(f"Unknown action type: {action.type}")

        return result

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _handle_fold(
        self, state: HoldemGameState, player: HoldemPlayer
    ) -> FoldResult:
        player.folded = True
        await self._append_log(
            PlayerActionLogEntry(
                player_id=player.id,
                action="fold",
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        # Check if only one player remains
        active_unfolded = [
            p for p in state.players if p.active and not p.folded
        ]
        if len(active_unfolded) == 1:
            # Last player standing wins
            winner = active_unfolded[0]
            winner.chips += state.pot
            # Store hand result for banner (no hands revealed on fold win)
            state.last_hand_result = HoldemHandResult(
                winners=[winner.id],
                pot=state.pot,
            )
            result = FoldResult(player_id=player.id)
            await self._save_state(state)
            await self._end_hand(state, [winner.id], "Last player standing")
            return result

        await self._advance_turn(state)
        return FoldResult(player_id=player.id)

    async def _handle_check(
        self, state: HoldemGameState, player: HoldemPlayer
    ) -> CheckResult:
        state.actions_this_round += 1
        await self._append_log(
            PlayerActionLogEntry(
                player_id=player.id,
                action="check",
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
        await self._advance_turn(state)
        return CheckResult(player_id=player.id)

    async def _handle_call(
        self, state: HoldemGameState, player: HoldemPlayer
    ) -> CallResult:
        amount_to_call = state.current_bet - player.current_bet
        actual = min(amount_to_call, player.chips)
        player.chips -= actual
        player.current_bet += actual
        state.pot += actual
        if player.chips == 0:
            player.all_in = True
        state.actions_this_round += 1

        await self._append_log(
            PlayerActionLogEntry(
                player_id=player.id,
                action="call",
                amount=actual,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
        await self._advance_turn(state)
        return CallResult(player_id=player.id, amount=actual)

    async def _handle_bet(
        self, state: HoldemGameState, player: HoldemPlayer, amount: int
    ) -> BetResult:
        if amount < state.big_blind:
            raise ValueError(f"Minimum bet is {state.big_blind}")
        if amount > player.chips:
            raise ValueError("Not enough chips")

        player.chips -= amount
        player.current_bet += amount
        state.current_bet = player.current_bet
        state.pot += amount
        state.last_raiser = player.id
        state.actions_this_round = 1
        if player.chips == 0:
            player.all_in = True

        await self._append_log(
            PlayerActionLogEntry(
                player_id=player.id,
                action="bet",
                amount=amount,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
        await self._advance_turn(state)
        return BetResult(player_id=player.id, amount=amount)

    async def _handle_raise(
        self, state: HoldemGameState, player: HoldemPlayer, amount: int
    ) -> RaiseResult:
        """Handle a raise. `amount` is the TOTAL bet the player wants to make."""
        amount_to_call = state.current_bet - player.current_bet
        raise_portion = amount - amount_to_call
        if raise_portion < state.big_blind and amount < player.chips:
            raise ValueError(f"Minimum raise is {state.big_blind}")
        if amount > player.chips:
            raise ValueError("Not enough chips")

        player.chips -= amount
        player.current_bet += amount
        state.current_bet = player.current_bet
        state.pot += amount
        state.last_raiser = player.id
        state.actions_this_round = 1
        if player.chips == 0:
            player.all_in = True

        await self._append_log(
            PlayerActionLogEntry(
                player_id=player.id,
                action="raise",
                amount=amount,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
        await self._advance_turn(state)
        return RaiseResult(player_id=player.id, amount=amount)

    async def _handle_all_in(
        self, state: HoldemGameState, player: HoldemPlayer
    ) -> AllInResult:
        amount = player.chips
        player.chips = 0
        player.current_bet += amount
        if player.current_bet > state.current_bet:
            state.current_bet = player.current_bet
            state.last_raiser = player.id
            state.actions_this_round = 1
        else:
            state.actions_this_round += 1
        state.pot += amount
        player.all_in = True

        await self._append_log(
            PlayerActionLogEntry(
                player_id=player.id,
                action="all_in",
                amount=amount,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
        await self._advance_turn(state)
        return AllInResult(player_id=player.id, amount=amount)

    # ------------------------------------------------------------------
    # Turn / round advancement
    # ------------------------------------------------------------------

    def _get_active_in_hand(self, state: HoldemGameState) -> list[HoldemPlayer]:
        """Players who are active, not folded."""
        return [p for p in state.players if p.active and not p.folded]

    def _get_can_act(self, state: HoldemGameState) -> list[HoldemPlayer]:
        """Players who can still take an action (not folded, not all-in)."""
        return [
            p for p in state.players if p.active and not p.folded and not p.all_in
        ]

    async def _advance_turn(self, state: HoldemGameState):
        """Advance to the next player or next betting round."""
        active_in_hand = self._get_active_in_hand(state)
        can_act = self._get_can_act(state)

        # If only one player left (others folded), hand is over
        if len(active_in_hand) <= 1:
            await self._save_state(state)
            return

        # Check if betting round is complete
        round_complete = self._is_round_complete(state, can_act)

        if round_complete:
            await self._advance_betting_round(state)
        else:
            # Move to next player who can act
            current_idx = next(
                i for i, p in enumerate(state.players) if p.id == state.whose_turn
            )
            for offset in range(1, len(state.players) + 1):
                idx = (current_idx + offset) % len(state.players)
                p = state.players[idx]
                if p.active and not p.folded and not p.all_in:
                    state.whose_turn = p.id
                    break
            await self._save_state(state)

    def _is_round_complete(
        self, state: HoldemGameState, can_act: list[HoldemPlayer]
    ) -> bool:
        """Check if the current betting round is complete."""
        if not can_act:
            # Everyone is all-in or folded
            return True

        # All players who can act must have matched the current bet
        all_matched = all(
            p.current_bet == state.current_bet for p in can_act
        )

        if not all_matched:
            return False

        # Everyone has matched. Round is complete if:
        # - In preflop: everyone has had a chance to act (actions >= number who can act)
        #   and no one just raised
        # - Post-flop: similar logic
        if state.last_raiser is None:
            # No bets made — everyone needs to check
            return state.actions_this_round >= len(can_act)
        else:
            # A bet/raise was made — round done when everyone has responded
            # The raiser's action counts as 1, plus everyone else has acted
            return state.actions_this_round >= len(can_act)

    async def _advance_betting_round(self, state: HoldemGameState):
        """Move to the next betting round (flop, turn, river, showdown)."""
        # Reset per-round state
        for p in state.players:
            p.current_bet = 0
        state.current_bet = 0
        state.last_raiser = None
        state.actions_this_round = 0

        deck = await self._load_deck()

        active_in_hand = self._get_active_in_hand(state)
        can_act = self._get_can_act(state)

        if state.betting_round == "preflop":
            state.betting_round = "flop"
            # Deal 3 community cards (burn 1)
            deck.pop()  # burn
            state.community_cards.extend([deck.pop() for _ in range(3)])
        elif state.betting_round == "flop":
            state.betting_round = "turn"
            deck.pop()  # burn
            state.community_cards.append(deck.pop())
        elif state.betting_round == "turn":
            state.betting_round = "river"
            deck.pop()  # burn
            state.community_cards.append(deck.pop())
        elif state.betting_round == "river":
            state.betting_round = "showdown"
            await self._save_deck(deck)
            await self._save_state(state)
            await self._showdown(state)
            return

        await self._save_deck(deck)
        await self._append_log(
            CommunityCardsLogEntry(
                cards=list(state.community_cards),
                betting_round=state.betting_round,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        # If no one can act (all all-in), fast-forward to showdown
        if len(can_act) <= 1:
            # Run out remaining community cards
            while len(state.community_cards) < 5:
                deck = await self._load_deck()
                deck.pop()  # burn
                state.community_cards.append(deck.pop())
                await self._save_deck(deck)
            state.betting_round = "showdown"
            await self._save_state(state)
            await self._showdown(state)
            return

        # Set first to act post-flop: first active player after dealer
        active = [p for p in state.players if p.active]
        dealer_pos = state.dealer_index % len(active)
        for offset in range(1, len(active) + 1):
            idx = (dealer_pos + offset) % len(active)
            p = active[idx]
            if not p.folded and not p.all_in:
                state.whose_turn = p.id
                break

        await self._save_state(state)

    async def _showdown(self, state: HoldemGameState):
        """Evaluate hands and award the pot."""
        active_in_hand = self._get_active_in_hand(state)

        best_score = None
        winners = []
        player_hands = {}
        best_hand_name = ""

        for p in active_in_hand:
            cards = await self._load_player_cards(p.id)
            player_hands[p.id] = cards
            all_cards = cards + state.community_cards
            score = evaluate_hand(all_cards)
            if best_score is None or score > best_score:
                best_score = score
                winners = [p.id]
                best_hand_name = hand_name(score)
            elif score == best_score:
                winners.append(p.id)

        # Split pot among winners
        share = state.pot // len(winners)
        remainder = state.pot % len(winners)
        for pid in winners:
            player = next(p for p in state.players if p.id == pid)
            player.chips += share
        # Give remainder to first winner
        if remainder:
            first_winner = next(p for p in state.players if p.id == winners[0])
            first_winner.chips += remainder

        state.winner = winners[0] if len(winners) == 1 else None
        state.winning_hand = best_hand_name

        # Store hand result for broadcast (persists through deal of next hand)
        state.last_hand_result = HoldemHandResult(
            winners=winners,
            winning_hand=best_hand_name,
            pot=state.pot,
            player_hands=player_hands,
        )

        await self._append_log(
            ShowdownLogEntry(
                winners=winners,
                winning_hand=best_hand_name,
                pot=state.pot,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        await self._end_hand(state, winners, best_hand_name)

    async def _end_hand(
        self, state: HoldemGameState, winners: list[str], hand_desc: str
    ):
        """End the current hand — check for tournament elimination and deal next."""
        # Eliminate players with 0 chips
        for p in state.players:
            if p.active and p.chips <= 0:
                p.active = False

        # Check if the game is over (only 1 player with chips)
        active_players = [p for p in state.players if p.active]
        if len(active_players) <= 1:
            state.status = "finished"
            if active_players:
                state.winner = active_players[0].id
            await self._save_state(state)
            return

        # Move dealer button
        active_indices = [
            i for i, p in enumerate(state.players) if p.active
        ]
        current_dealer_abs = state.dealer_index % len(state.players)
        # Find next active player as dealer
        for offset in range(1, len(state.players) + 1):
            next_idx = (current_dealer_abs + offset) % len(state.players)
            if state.players[next_idx].active:
                state.dealer_index = next_idx
                break

        await self._save_state(state)

        # Deal next hand
        await self._deal_new_hand(state)

    async def get_log(self) -> list[HoldemLogEntryBase]:
        entries = await self.redis.lrange(self._log_key, 0, -1)
        return [HoldemLogEntryBase.model_validate_json(e) for e in entries]
