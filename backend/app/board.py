"""
Clue Board - Grid, Linked Graph, and BFS Reachability

Standard board: 25 rows x 24 cols (0-indexed)
Legend: .=hallway  D=door  S=start  X=center(impassable)  #=wall
Room keys: s=Study h=Hall o=Lounge l=Library b=Billiard
           n=Dining c=Conservatory a=Ballroom k=Kitchen
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import sys


class Room(Enum):
    STUDY = "Study"
    HALL = "Hall"
    LOUNGE = "Lounge"
    LIBRARY = "Library"
    BILLIARD_ROOM = "Billiard Room"
    DINING_ROOM = "Dining Room"
    CONSERVATORY = "Conservatory"
    BALLROOM = "Ballroom"
    KITCHEN = "Kitchen"


class SquareType(Enum):
    HALLWAY = "."
    ROOM = "R"
    DOOR = "D"
    START = "S"
    CENTER = "X"


@dataclass
class Square:
    row: int
    col: int
    type: SquareType
    room: Optional[Room] = None
    neighbors: list["Square"] = field(default_factory=list, repr=False)

    @property
    def key(self) -> tuple:
        if self.room:
            return ("room", self.room)
        return (self.row, self.col)

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        return isinstance(other, Square) and self.key == other.key

    def label(self) -> str:
        if self.room:
            return self.room.value
        return f"({self.row},{self.col})"

    def __repr__(self):
        if self.room:
            return f"Square({self.type.name}, {self.room.value})"
        return f"Square({self.row},{self.col}, {self.type.name})"


# ── Board Data ──────────────────────────────────────────────

SECRET_PASSAGES = {
    Room.STUDY: Room.KITCHEN,
    Room.KITCHEN: Room.STUDY,
    Room.LOUNGE: Room.CONSERVATORY,
    Room.CONSERVATORY: Room.LOUNGE,
}

# Room boundaries: (left_col, top_row, right_col, bottom_row)
# Corrected against the board image
ROOM_BOUNDS = {
    Room.STUDY: (0, 0, 6, 3),  # 4x7   top-left
    Room.HALL: (9, 1, 14, 6),  # 6x6   top-center
    Room.LOUNGE: (17, 0, 23, 5),  # 6x7   top-right
    Room.LIBRARY: (0, 7, 6, 10),  # 4x7   mid-left
    Room.BILLIARD_ROOM: (0, 12, 5, 16),  # 5x6   center-left
    Room.DINING_ROOM: (16, 9, 23, 15),  # 7x8   center-right
    Room.CONSERVATORY: (0, 20, 5, 24),  # 5x6   bottom-left (was row 19, fixed)
    Room.BALLROOM: (8, 17, 15, 22),  # 6x8   bottom-center
    Room.KITCHEN: (18, 19, 23, 24),  # 6x6   bottom-right
}

ROOM_KEYS = {
    Room.STUDY: "s",
    Room.HALL: "h",
    Room.LOUNGE: "o",
    Room.LIBRARY: "l",
    Room.BILLIARD_ROOM: "b",
    Room.DINING_ROOM: "n",
    Room.CONSERVATORY: "c",
    Room.BALLROOM: "a",
    Room.KITCHEN: "k",
}

# Doors: (row, col) ON the room perimeter (inset 1 from hallway)
# Each connects to the room node + adjacent hallway square outside the room
DOORS = {
    # Study (0,0)-(3,6): south-east corner
    (3, 6): Room.STUDY,
    # Hall (1,9)-(6,14): 2 south, 1 west
    (6, 11): Room.HALL,
    (6, 12): Room.HALL,
    (4, 9): Room.HALL,
    # Lounge (0,17)-(5,23): south-west
    (5, 17): Room.LOUNGE,
    # Library (7,0)-(10,6): east, south
    (8, 6): Room.LIBRARY,
    (10, 3): Room.LIBRARY,
    # Billiard Room (12,0)-(16,5): north-east, south-east
    (12, 1): Room.BILLIARD_ROOM,
    (15, 5): Room.BILLIARD_ROOM,
    # Dining Room (9,16)-(15,23): west, south-west
    (12, 16): Room.DINING_ROOM,
    (9, 17): Room.DINING_ROOM,
    # Conservatory (20,0)-(24,5): north-east
    (19, 4): Room.CONSERVATORY,
    # Ballroom (18,8)-(24,15): 2 north, west, east
    (17, 9): Room.BALLROOM,
    (17, 14): Room.BALLROOM,
    (19, 8): Room.BALLROOM,
    (19, 15): Room.BALLROOM,
    # Kitchen (18,18)-(24,23): north-west
    (18, 19): Room.KITCHEN,
}

# Start positions (row, col)
START_POSITIONS = {
    "Scarlet": (24, 9),  # bottom, between Conservatory & Ballroom
    "Mustard": (7, 23),  # right side
    "White": (24, 14),  # bottom, between Ballroom & Kitchen
    "Green": (0, 16),  # top, between Hall & Lounge
    "Plum": (5, 0),  # left side, between Study & Library
    "Peacock": (18, 0),  # left side, between Billiard & Conservatory
}


# ── Grid Builder ────────────────────────────────────────────

ROWS, COLS = 25, 24

BOARD = """ssssss .        . oooooo
sssssss..hhhhhh..ooooooo
sssssss..hhhhhh..ooooooo
sssssss..hhhhhh..ooooooo
 ........hhhhhh..ooooooo
.........hhhhhh..ooooooo
 lllll...hhhhhh........ 
lllllll.................
lllllll..     .........
lllllll..     ..nnnnnnnn
 lllll...     ..nnnnnnnn
 ........     ..nnnnnnnn
bbbbbb...     ..nnnnnnnn
bbbbbb...     ..nnnnnnnn
bbbbbb...     ..nnnnnnnn
bbbbbb.............nnnnn
bbbbbb.................
 .......aaaaaaaa........
........aaaaaaaa..kkkkk
 cccc...aaaaaaaa..kkkkkk
cccccc..aaaaaaaa..kkkkkk
cccccc..aaaaaaaa..kkkkkk
cccccc..aaaaaaaa..kkkkkk
cccccc ...aaaa... kkkkkk
         .    .         """


def build_grid() -> list[list[str]]:
    grid = [[" " for _ in range(COLS)] for _ in range(ROWS)]
    key_to_room = {key: room for room, key in ROOM_KEYS.items()}
    room_records: dict[Room, list[int] | None] = {room: None for room in Room}

    for row, line in enumerate(BOARD.splitlines()):
        for col, ch in enumerate(line):
            grid[row][col] = ch
            room = key_to_room.get(ch)
            if room:
                record = room_records[room]
                if record is None:
                    room_records[room] = [col, row, col, row]
                else:
                    record[0] = min(record[0], col)
                    record[1] = min(record[1], row)
                    record[2] = max(record[2], col)
                    record[3] = max(record[3], row)

    for room, record in room_records.items():
        if record is None:
            raise ValueError(f"Missing room cells for {room.value} in BOARD")
        ROOM_BOUNDS[room] = tuple(record)

    for r, c in DOORS:
        if 0 <= r < ROWS and 0 <= c < COLS:
            grid[r][c] = "D"

    for name, (r, c) in START_POSITIONS.items():
        if 0 <= r < ROWS and 0 <= c < COLS:
            grid[r][c] = "S"

    return grid


# Pre-compute room centers (build_grid updates ROOM_BOUNDS from the BOARD string)
_init_grid = build_grid()
ROOM_CENTERS = {
    room.value: [(_r1 + _r2) // 2, (_c1 + _c2) // 2]
    for room in Room
    for _c1, _r1, _c2, _r2 in [ROOM_BOUNDS[room]]
}


def validate_grid(grid: list[list[str]]):
    errors = []

    # Doors must be inside their room bounds
    for (r, c), room in DOORS.items():
        c1, r1, c2, r2 = ROOM_BOUNDS[room]
        if not (r1 <= r <= r2 and c1 <= c <= c2):
            errors.append(
                f"Door ({r},{c}) not inside {room.value} ({c1},{r1})-({c2},{r2})"
            )

    # Doors must have at least one hallway neighbor OUTSIDE the room
    for (r, c), room in DOORS.items():
        c1, r1, c2, r2 = ROOM_BOUNDS[room]
        has_outside_neighbor = False
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < ROWS and 0 <= nc < COLS:
                inside_room = r1 <= nr <= r2 and c1 <= nc <= c2
                if not inside_room and grid[nr][nc] in (".", "S", "D"):
                    has_outside_neighbor = True
                    break
        if not has_outside_neighbor:
            errors.append(
                f"Door ({r},{c}) for {room.value} has no hallway neighbor outside room!"
            )

    # Starts must not be inside rooms
    room_cells = set()
    for room, (c1, r1, c2, r2) in ROOM_BOUNDS.items():
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                room_cells.add((r, c))
    for name, (r, c) in START_POSITIONS.items():
        if (r, c) in room_cells:
            errors.append(f"Start '{name}' at ({r},{c}) is inside a room!")

    # Room boundaries must not overlap
    for r1_name, b1 in ROOM_BOUNDS.items():
        for r2_name, b2 in ROOM_BOUNDS.items():
            if r1_name.value >= r2_name.value:
                continue
            overlap = (
                b1[0] <= b2[2] and b2[0] <= b1[2] and b1[1] <= b2[3] and b2[1] <= b1[3]
            )
            if overlap:
                errors.append(f"Rooms overlap: {r1_name.value} & {r2_name.value}")

    if errors:
        print("=== VALIDATION ERRORS ===")
        for e in errors:
            print(f"  x {e}")
        return False
    else:
        print("=== Validation: ALL OK ===")
        return True


# ── Graph Builder ───────────────────────────────────────────


def build_graph(
    grid: list[list[str]],
) -> tuple[dict[tuple, Square], dict[Room, Square]]:
    squares: dict[tuple[int, int], Square] = {}

    for r in range(ROWS):
        for c in range(COLS):
            ch = grid[r][c]
            room_keys = set(ROOM_KEYS.values())
            if ch in room_keys or ch in ("X", "#", " "):
                continue
            st = {"D": SquareType.DOOR, "S": SquareType.START}.get(
                ch, SquareType.HALLWAY
            )
            squares[(r, c)] = Square(r, c, st)

    room_nodes: dict[Room, Square] = {}
    for room in Room:
        c1, r1, c2, r2 = ROOM_BOUNDS[room]
        node = Square((r1 + r2) // 2, (c1 + c2) // 2, SquareType.ROOM, room=room)
        room_nodes[room] = node

    # Hallway adjacency
    for (r, c), sq in squares.items():
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nb = squares.get((r + dr, c + dc))
            if nb:
                sq.neighbors.append(nb)

    # Door <-> Room
    for (r, c), room in DOORS.items():
        if (r, c) in squares:
            door = squares[(r, c)]
            rn = room_nodes[room]
            door.neighbors.append(rn)
            rn.neighbors.append(door)

    # Secret passages
    for src, dst in SECRET_PASSAGES.items():
        room_nodes[src].neighbors.append(room_nodes[dst])

    return squares, room_nodes


# ── BFS Reachability ────────────────────────────────────────


def reachable(
    start: Square,
    steps: int,
    squares: dict,
    room_nodes: dict[Room, Square],
) -> dict[Square, int]:
    """
    BFS from `start` up to `steps` moves.
    Entering a room ends your turn (don't expand further from room node).
    Door <-> Room transitions are free (the door sits on the room perimeter).
    Uses 0-1 BFS: 0-cost edges go to the front of the deque.
    """
    visited: dict[Square, int] = {start: 0}
    queue: deque[tuple[Square, int]] = deque([(start, 0)])

    while queue:
        sq, dist = queue.popleft()

        for nb in sq.neighbors:
            # Door <-> Room transitions are free: the door square sits on
            # the room perimeter and shouldn't count as an extra step.
            if (sq.type == SquareType.ROOM and nb.type == SquareType.DOOR) or (
                sq.type == SquareType.DOOR and nb.type == SquareType.ROOM
            ):
                new_dist = dist
            else:
                new_dist = dist + 1

            if new_dist > steps:
                continue

            if nb in visited and visited[nb] <= new_dist:
                continue
            visited[nb] = new_dist

            # Entering a room ends your move
            if nb.type == SquareType.ROOM:
                continue

            # 0-1 BFS: prepend 0-cost edges, append 1-cost edges
            if new_dist == dist:
                queue.appendleft((nb, new_dist))
            else:
                queue.append((nb, new_dist))

    return visited


def show_reachable_on_grid(
    grid: list[list[str]],
    start: Square,
    reached: dict[Square, int],
    steps: int,
):
    disp = [row[:] for row in grid]

    for sq, dist in reached.items():
        if sq.type == SquareType.ROOM:
            continue
        r, c = sq.row, sq.col
        if sq == start:
            disp[r][c] = "@"
        elif dist <= 9:
            disp[r][c] = str(dist)
        else:
            disp[r][c] = "*"

    reached_rooms = [
        (sq, dist) for sq, dist in reached.items() if sq.type == SquareType.ROOM
    ]

    print(f"\nReachable from {start.label()} in {steps} steps:")
    header = "   " + "".join(f"{i % 10}" for i in range(COLS))
    print(header)
    for i, row in enumerate(disp):
        print(f"{i:2} " + "".join(row))

    if reached_rooms:
        print(f"\n  Rooms reachable:")
        for sq, dist in sorted(reached_rooms, key=lambda x: x[1]):
            via = "secret passage" if (dist == 1 and start.room) else "door"
            print(f"    {sq.room.value} (dist {dist}, via {via})")

    hallway_count = sum(
        1 for sq in reached if sq.type != SquareType.ROOM and sq != start
    )
    print(f"  Hallway/door squares: {hallway_count}")
    print(f"  Rooms: {len(reached_rooms)}")


# ── Display ─────────────────────────────────────────────────


def print_grid(grid: list[list[str]]):
    header = "   " + "".join(f"{i % 10}" for i in range(COLS))
    print(header)
    for i, row in enumerate(grid):
        print(f"{i:2} " + "".join(row))


def print_room_info():
    print("\n=== Room Sizes ===")
    for room, (c1, r1, c2, r2) in ROOM_BOUNDS.items():
        h, w = r2 - r1 + 1, c2 - c1 + 1
        doors = [(r, c) for (r, c), rm in DOORS.items() if rm == room]
        passage = SECRET_PASSAGES.get(room)
        parts = [f"{h}x{w}", f"({r1},{c1})-({r2},{c2})", f"doors={doors}"]
        if passage:
            parts.append(f"passage->{passage.value}")
        print(f"  {room.value:16s}: {', '.join(parts)}")


def print_graph_summary(squares, room_nodes):
    print(f"\n=== Graph Summary ===")
    print(
        f"  Hallway: {sum(1 for s in squares.values() if s.type == SquareType.HALLWAY)}"
    )
    print(f"  Doors:   {sum(1 for s in squares.values() if s.type == SquareType.DOOR)}")
    print(
        f"  Starts:  {sum(1 for s in squares.values() if s.type == SquareType.START)}"
    )
    print(f"  Rooms:   {len(room_nodes)}")

    print(f"\n=== Room Connectivity ===")
    for room in Room:
        node = room_nodes[room]
        conns = []
        for nb in node.neighbors:
            if nb.room:
                conns.append(f"  -> {nb.room.value} (secret passage)")
            else:
                conns.append(f"  -> door ({nb.row},{nb.col})")
        print(f"  {room.value}:")
        for c in conns:
            print(f"  {c}")


def find_square(row, col, room_name, squares, room_nodes):
    if room_name:
        for room, node in room_nodes.items():
            if room_name.lower() in room.value.lower():
                return node
        return None
    return squares.get((row, col))


def move_towards(
    start: Square,
    target_room: Room,
    dice: int,
    squares: dict,
    room_nodes: dict[Room, Square],
) -> tuple[Square, bool]:
    """
    Given a current location, a target room, and a dice roll, attempt to move
    the piece toward (or into) that room.

    Returns (destination, reached) where:
      - destination is the Square to move to
      - reached is True if the target room was entered with this dice roll
    """
    reachable_squares = reachable(start, dice, squares, room_nodes)
    target_node = room_nodes[target_room]

    # If the target room is directly reachable, move there
    if target_node in reachable_squares:
        return (target_node, True)

    # Otherwise do an unconstrained BFS from the target room to get distances
    # from every square back to the target, then pick the reachable square with
    # the smallest distance.  Uses 0-1 BFS for free Door <-> Room edges.
    dist_from_target: dict[Square, int] = {target_node: 0}
    bfs_queue: deque[tuple[Square, int]] = deque([(target_node, 0)])
    while bfs_queue:
        sq, dist = bfs_queue.popleft()
        for nb in sq.neighbors:
            if (sq.type == SquareType.ROOM and nb.type == SquareType.DOOR) or (
                sq.type == SquareType.DOOR and nb.type == SquareType.ROOM
            ):
                new_dist = dist
            else:
                new_dist = dist + 1
            if nb not in dist_from_target or new_dist < dist_from_target[nb]:
                dist_from_target[nb] = new_dist
                if nb.type != SquareType.ROOM:
                    if new_dist == dist:
                        bfs_queue.appendleft((nb, new_dist))
                    else:
                        bfs_queue.append((nb, new_dist))

    # Pick the reachable square (excluding start) that is closest to the target
    best_sq = start
    best_dist = dist_from_target.get(start, float("inf"))
    for sq in reachable_squares:
        if sq == start:
            continue
        d = dist_from_target.get(sq, float("inf"))
        if d < best_dist:
            best_dist = d
            best_sq = sq

    return (best_sq, False)


# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    grid = build_grid()
    print("=== Clue Board Grid ===")
    print_grid(grid)
    print_room_info()

    ok = validate_grid(grid)

    squares, room_nodes = build_graph(grid)
    print_graph_summary(squares, room_nodes)

    print("\n" + "=" * 50)
    print("=== Reachability Demos ===")
    print("=" * 50)

    # From Scarlet's start (24,7) with roll of 6
    scarlet = squares[START_POSITIONS["Scarlet"]]
    reached = reachable(scarlet, 6, squares, room_nodes)
    show_reachable_on_grid(grid, scarlet, reached, 6)

    # From Study (secret passage to Kitchen)
    study = room_nodes[Room.STUDY]
    reached = reachable(study, 4, squares, room_nodes)
    show_reachable_on_grid(grid, study, reached, 4)

    # From mid-hallway
    mid = squares.get((7, 17))
    if mid:
        reached = reachable(mid, 5, squares, room_nodes)
        show_reachable_on_grid(grid, mid, reached, 5)

    # CLI mode: python clue_board.py <row> <col> <steps>
    #       or: python clue_board.py <room_name> <steps>
    if len(sys.argv) > 1:
        print("\n=== Custom Query ===")
        try:
            if sys.argv[1].isdigit():
                r, c, s = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
                sq = find_square(r, c, None, squares, room_nodes)
            else:
                name = " ".join(sys.argv[1:-1])
                s = int(sys.argv[-1])
                sq = find_square(None, None, name, squares, room_nodes)
            if sq:
                reached = reachable(sq, s, squares, room_nodes)
                show_reachable_on_grid(grid, sq, reached, s)
            else:
                print("Square not found!")
        except (IndexError, ValueError):
            print("Usage: python clue_board.py <row> <col> <steps>")
            print("   or: python clue_board.py <room_name> <steps>")
