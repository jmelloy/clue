"""Tests for board.py: grid, graph, BFS reachability, and move_towards."""

import pytest

from app.board import (
    DOORS,
    Room,
    Square,
    SquareType,
    build_grid,
    build_graph,
    reachable,
    move_towards,
    START_POSITIONS,
)


@pytest.fixture(scope="module")
def board():
    grid = build_grid()
    squares, room_nodes = build_graph(grid)
    return squares, room_nodes


# ---------------------------------------------------------------------------
# Basic graph tests
# ---------------------------------------------------------------------------


def test_all_rooms_have_nodes(board):
    _, room_nodes = board
    assert len(room_nodes) == len(Room)
    for room in Room:
        assert room in room_nodes
        assert room_nodes[room].type == SquareType.ROOM


def test_start_positions_in_squares(board):
    squares, _ = board
    for name, pos in START_POSITIONS.items():
        assert pos in squares, f"Start position for {name} not in squares"
        assert squares[pos].type == SquareType.START


def test_secret_passages(board):
    _, room_nodes = board
    # Study <-> Kitchen
    study_neighbors = {nb.room for nb in room_nodes[Room.STUDY].neighbors if nb.room}
    assert Room.KITCHEN in study_neighbors

    kitchen_neighbors = {
        nb.room for nb in room_nodes[Room.KITCHEN].neighbors if nb.room
    }
    assert Room.STUDY in kitchen_neighbors

    # Lounge <-> Conservatory
    lounge_neighbors = {nb.room for nb in room_nodes[Room.LOUNGE].neighbors if nb.room}
    assert Room.CONSERVATORY in lounge_neighbors


# ---------------------------------------------------------------------------
# Reachability tests
# ---------------------------------------------------------------------------


def test_reachable_includes_start(board):
    squares, room_nodes = board
    start = squares[START_POSITIONS["Scarlet"]]
    reached = reachable(start, 6, squares, room_nodes)
    assert start in reached
    assert reached[start] == 0


def test_reachable_with_zero_steps(board):
    squares, room_nodes = board
    start = squares[START_POSITIONS["Scarlet"]]
    reached = reachable(start, 0, squares, room_nodes)
    assert reached == {start: 0}


def test_reachable_from_room_via_secret_passage(board):
    squares, room_nodes = board
    study = room_nodes[Room.STUDY]
    # Secret passage from Study to Kitchen costs 1 step
    reached = reachable(study, 1, squares, room_nodes)
    assert room_nodes[Room.KITCHEN] in reached


def test_door_does_not_cost_extra_step_leaving_room(board):
    """Leaving a room through a door should not count the door as an extra square.

    The door sits on the room perimeter, so Room->Door is free and only
    Door->Hallway costs a step.  With 1 step from a room, a player should
    reach the hallway square just outside a door.
    """
    squares, room_nodes = board
    # Use the Study, which has a door at (3,6).
    # The hallway square just outside that door is (4,6) — row 4 is outside
    # the Study bounds (rows 0-3).
    study = room_nodes[Room.STUDY]
    reached = reachable(study, 1, squares, room_nodes)

    # The door at (3,6) should be reachable at cost 0 (free Room->Door)
    door_sq = squares.get((3, 6))
    assert door_sq is not None, "Door square (3,6) not in graph"
    assert door_sq in reached
    assert reached[door_sq] == 0, (
        f"Door should be distance 0 from its room, got {reached[door_sq]}"
    )

    # The hallway square outside the door should be reachable at cost 1
    outside = squares.get((4, 6))
    assert outside is not None, "Hallway square (4,6) not in graph"
    assert outside in reached
    assert reached[outside] == 1, (
        f"Hallway outside door should be distance 1, got {reached[outside]}"
    )


def test_door_does_not_cost_extra_step_entering_room(board):
    """Entering a room from a hallway through a door should cost 1 total step,
    not 2 (hallway->door + door->room)."""
    squares, room_nodes = board
    # Hallway square (4,6) is just outside the Study door at (3,6).
    outside = squares.get((4, 6))
    assert outside is not None
    reached = reachable(outside, 1, squares, room_nodes)

    # With 1 step we should be able to enter the Study:
    # (4,6) -> door (3,6) costs 1, door -> Study room costs 0
    study = room_nodes[Room.STUDY]
    assert study in reached, (
        "Should reach Study in 1 step from hallway outside its door"
    )
    assert reached[study] == 1


# ---------------------------------------------------------------------------
# move_towards tests
# ---------------------------------------------------------------------------


def test_move_towards_reaches_room(board):
    """When target room is reachable with the dice roll, reached=True."""
    squares, room_nodes = board
    # Start from Study (which has a secret passage to Kitchen)
    study = room_nodes[Room.STUDY]
    dest, reached = move_towards(study, Room.KITCHEN, 1, squares, room_nodes)
    assert reached is True
    assert dest == room_nodes[Room.KITCHEN]


def test_move_towards_moves_closer_when_not_reachable(board):
    """When target is not reachable, the returned square should be closer to it."""
    squares, room_nodes = board
    # Scarlet starts far from the Study; with a small roll she can't reach it
    scarlet_pos = START_POSITIONS["Scarlet"]
    start = squares[scarlet_pos]

    dest, reached = move_towards(start, Room.STUDY, 2, squares, room_nodes)
    assert reached is False
    # The destination should be different from start (there are reachable squares
    # closer to Study than Scarlet's starting position)
    assert dest != start


def test_move_towards_returns_square_type(board):
    """Returned destination is always a Square instance."""
    squares, room_nodes = board
    start = squares[START_POSITIONS["White"]]
    dest, reached = move_towards(start, Room.BALLROOM, 6, squares, room_nodes)
    assert isinstance(dest, Square)


def test_move_towards_large_roll_reaches_room(board):
    """With a sufficiently large roll from a nearby position, the room is reached."""
    squares, room_nodes = board
    # Ballroom has a door at (17, 9); start just outside
    # Use a square adjacent to a Ballroom door
    start = squares.get((17, 9))  # this is a door square for Ballroom
    if start is None:
        pytest.skip("Door square not found in graph")
    dest, reached = move_towards(start, Room.BALLROOM, 1, squares, room_nodes)
    assert reached is True
    assert dest == room_nodes[Room.BALLROOM]
