"""The rules of Alien Siege, kept apart from the drawing so they can run without a window.

Everything here uses turtle coordinates: (0, 0) is the middle of the window, x grows
to the right and y grows upwards. Times are in seconds, speeds in pixels per second.
"""

import random
from dataclasses import dataclass
from pathlib import Path

WIDTH = 800
HEIGHT = 700
LEFT_WALL = -WIDTH / 2 + 30     # nothing moves closer to the sides than this
RIGHT_WALL = WIDTH / 2 - 30
GROUND_Y = -HEIGHT / 2 + 40     # the line the ship flies over
CEILING_Y = HEIGHT / 2 - 50     # the score line sits above this

PLAYER_Y = GROUND_Y + 25
PLAYER_WIDTH = 44
PLAYER_HEIGHT = 22
PLAYER_SPEED = 320
LIVES = 3
RESPAWN_TIME = 1.2              # everything stands still this long after the ship is hit

LASER_WIDTH = 3
LASER_HEIGHT = 14
LASER_SPEED = 650

COLUMNS = 10
ROW_KINDS = (("warden", 30), ("drone", 20), ("drone", 20), ("grub", 10), ("grub", 10))
ALIEN_WIDTH = 36
ALIEN_HEIGHT = 24
COLUMN_GAP = 52
ROW_GAP = 44
FLEET_TOP = CEILING_Y - 50      # the top row of the first wave...
LEVEL_DROP = 20                 # ...every next wave starts this much lower...
MAX_LEVEL_DROP = 120            # ...but never more than this
STEP_X = 12
STEP_Y = 22
FIRST_BEAT = 0.8                # seconds between fleet steps with the whole fleet alive...
LAST_BEAT = 0.05                # ...and with one alien left
BEAT_PER_LEVEL = 0.06           # every next wave starts a bit faster...
MIN_FIRST_BEAT = 0.4            # ...up to this

BOLT_WIDTH = 6
BOLT_HEIGHT = 14
BOLT_SPEED = 260
BOLT_SPEED_PER_LEVEL = 20
MAX_BOLTS = 3                   # alien shots on the screen at once
SHOT_DELAY = (0.5, 1.4)         # seconds between alien shots, picked at random
AIMED_SHARE = 0.4               # share of shots fired from the column above the ship

BLOCK = 8                       # the bunkers are built from squares of this size
BUNKERS = 4
BUNKER_TOP = PLAYER_Y + 110
BUNKER_SHAPE = (
    "...####...",
    ".########.",
    "##########",
    "##########",
    "####..####",
    "###....###",
)

EXPLOSION_TIME = 0.3


@dataclass(eq=False)
class Box:
    """A rectangle around its centre. Everything that can collide is one."""

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self):
        return self.x - self.width / 2

    @property
    def right(self):
        return self.x + self.width / 2

    @property
    def top(self):
        return self.y + self.height / 2

    @property
    def bottom(self):
        return self.y - self.height / 2

    def overlaps(self, other):
        return (abs(self.x - other.x) * 2 < self.width + other.width
                and abs(self.y - other.y) * 2 < self.height + other.height)


@dataclass(eq=False)
class Alien(Box):
    kind: str = "grub"
    points: int = 10
    column: int = 0


@dataclass(eq=False)
class Shot(Box):
    speed: float = 0            # positive flies up, negative flies down


@dataclass(eq=False)
class Explosion:
    x: float
    y: float
    time_left: float = EXPLOSION_TIME


def build_bunkers():
    """Returns the blocks of all bunkers, spread evenly between the walls."""
    blocks = []
    width = len(BUNKER_SHAPE[0]) * BLOCK
    for i in range(BUNKERS):
        centre = LEFT_WALL + (RIGHT_WALL - LEFT_WALL) * (i + 0.5) / BUNKERS
        left = centre - width / 2 + BLOCK / 2
        for row, line in enumerate(BUNKER_SHAPE):
            for column, cell in enumerate(line):
                if cell == "#":
                    blocks.append(Box(left + column * BLOCK, BUNKER_TOP - row * BLOCK, BLOCK, BLOCK))
    return blocks


def load_high_score(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return 0


def save_high_score(path, score):
    Path(path).write_text(f"{score}\n")


class Game:
    """One game, from the first wave until the ship runs out of lives."""

    def __init__(self, high_score=0, rng=None):
        self.rng = rng or random.Random()
        self.high_score = high_score
        self.restart()

    def restart(self):
        self.score = 0
        self.lives = LIVES
        self.level = 1
        self.state = "playing"      # or "paused" or "over"
        self.player = Box(0, PLAYER_Y, PLAYER_WIDTH, PLAYER_HEIGHT)
        self.start_wave()

    def start_wave(self):
        drop = min((self.level - 1) * LEVEL_DROP, MAX_LEVEL_DROP)
        self.aliens = [
            Alien((column - (COLUMNS - 1) / 2) * COLUMN_GAP, FLEET_TOP - drop - row * ROW_GAP,
                  ALIEN_WIDTH, ALIEN_HEIGHT, kind, points, column)
            for row, (kind, points) in enumerate(ROW_KINDS)
            for column in range(COLUMNS)
        ]
        self.fleet_size = len(self.aliens)
        self.direction = 1
        self.frame = 0              # the aliens wave their legs on every step
        self.beat_timer = 0.0
        self.blocks = build_bunkers()
        self.laser = None
        self.bolts = []
        self.explosions = []
        self.shot_timer = self.next_shot_delay()
        self.respawn_timer = 0.0
        self.player.x = 0

    @property
    def beat(self):
        """Seconds between fleet steps. The fewer aliens are left, the faster they go."""
        first = max(FIRST_BEAT - (self.level - 1) * BEAT_PER_LEVEL, MIN_FIRST_BEAT)
        share = (len(self.aliens) - 1) / (self.fleet_size - 1)
        return LAST_BEAT + (first - LAST_BEAT) * share

    @property
    def respawning(self):
        return self.respawn_timer > 0

    def next_shot_delay(self):
        return self.rng.uniform(*SHOT_DELAY)

    def toggle_pause(self):
        if self.state == "playing":
            self.state = "paused"
        elif self.state == "paused":
            self.state = "playing"

    def fire(self):
        if self.state != "playing" or self.respawning or self.laser:
            return
        self.laser = Shot(self.player.x, self.player.top + LASER_HEIGHT / 2,
                          LASER_WIDTH, LASER_HEIGHT, LASER_SPEED)

    def update(self, dt, steer=0):
        """Moves the game on by dt seconds. steer is -1 for left, 1 for right, 0 to stay."""
        if self.state != "playing":
            return
        for explosion in self.explosions:
            explosion.time_left -= dt
        self.explosions = [e for e in self.explosions if e.time_left > 0]
        if self.respawning:
            self.respawn_timer -= dt
            return

        half = PLAYER_WIDTH / 2
        x = self.player.x + steer * PLAYER_SPEED * dt
        self.player.x = min(max(x, LEFT_WALL + half), RIGHT_WALL - half)
        self.move_shots(dt)

        self.beat_timer += dt
        while self.beat_timer >= self.beat:
            self.beat_timer -= self.beat
            self.step_fleet()

        self.shot_timer -= dt
        if self.shot_timer <= 0:
            self.alien_fire()
            self.shot_timer = self.next_shot_delay()

        self.check_hits()
        self.check_end()

    def move_shots(self, dt):
        if self.laser:
            self.laser.y += self.laser.speed * dt
            if self.laser.bottom > CEILING_Y:
                self.laser = None
        for bolt in self.bolts:
            bolt.y += bolt.speed * dt
        self.bolts = [b for b in self.bolts if b.top > GROUND_Y]

    def step_fleet(self):
        """One step sideways, or one step down and back at a wall."""
        self.frame = 1 - self.frame
        left = min(a.left for a in self.aliens)
        right = max(a.right for a in self.aliens)
        if right + STEP_X > RIGHT_WALL and self.direction > 0 or left - STEP_X < LEFT_WALL and self.direction < 0:
            self.direction = -self.direction
            for alien in self.aliens:
                alien.y -= STEP_Y
        else:
            for alien in self.aliens:
                alien.x += self.direction * STEP_X
        # Aliens flying into a bunker crush it.
        self.blocks = [b for b in self.blocks if not any(b.overlaps(a) for a in self.aliens)]

    def alien_fire(self):
        if len(self.bolts) >= MAX_BOLTS:
            return
        lowest = {}
        for alien in self.aliens:
            if alien.column not in lowest or alien.y < lowest[alien.column].y:
                lowest[alien.column] = alien
        if self.rng.random() < AIMED_SHARE:
            shooter = min(lowest.values(), key=lambda a: abs(a.x - self.player.x))
        else:
            shooter = self.rng.choice(list(lowest.values()))
        speed = BOLT_SPEED + (self.level - 1) * BOLT_SPEED_PER_LEVEL
        self.bolts.append(Shot(shooter.x, shooter.bottom - BOLT_HEIGHT / 2,
                               BOLT_WIDTH, BOLT_HEIGHT, -speed))

    def erode(self, shot):
        """Knocks out the bunker blocks the shot touches. Returns True if there were any."""
        hit = [b for b in self.blocks if b.overlaps(shot)]
        for block in hit:
            self.blocks.remove(block)
        return bool(hit)

    def check_hits(self):
        if self.laser:
            alien = next((a for a in self.aliens if a.overlaps(self.laser)), None)
            bolt = next((b for b in self.bolts if b.overlaps(self.laser)), None)
            if alien:
                self.aliens.remove(alien)
                self.score += alien.points
                self.high_score = max(self.high_score, self.score)
                self.explosions.append(Explosion(alien.x, alien.y))
                self.laser = None
            elif bolt:
                self.bolts.remove(bolt)
                self.laser = None
            elif self.erode(self.laser):
                self.laser = None

        for bolt in list(self.bolts):
            if self.erode(bolt):
                self.bolts.remove(bolt)
            elif bolt.overlaps(self.player):
                self.lose_life()
                return

    def lose_life(self):
        self.lives -= 1
        self.explosions.append(Explosion(self.player.x, self.player.y))
        self.laser = None
        self.bolts = []
        if self.lives == 0:
            self.state = "over"
        else:
            self.respawn_timer = RESPAWN_TIME

    def check_end(self):
        if not self.aliens:
            self.level += 1
            self.start_wave()
        elif min(a.bottom for a in self.aliens) <= self.player.top:
            self.lives = 0
            self.state = "over"
