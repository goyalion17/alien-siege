"""Alien Siege: a shoot 'em up drawn with Python's turtle module.

Move with the arrow keys or A and D, shoot with Space, pause with P, quit with Escape.
The rules live in game.py; this file only draws them and passes on the keys.
"""

import math
import time
import turtle
from pathlib import Path

from game import CEILING_Y, GROUND_Y, HEIGHT, LEFT_WALL, RIGHT_WALL, WIDTH, Game, load_high_score, save_high_score

HIGH_SCORE_FILE = Path(__file__).with_name("highscore.txt")
FRAME_MS = 16                   # about 60 frames per second
MAX_DT = 0.05                   # a slow frame doesn't let things jump through each other

BACKGROUND = "#05050f"
TEXT = "#e8e8f0"
FONT = ("Courier", 16, "bold")
BIG_FONT = ("Courier", 36, "bold")

# Every shape is drawn pointing up (heading 90), so its points are plain offsets on
# the screen. The aliens have two frames each, they swap them on every step.
SHIP = (
    ("#3ef0c0", [(-22, -11), (22, -11), (22, -3), (8, -3), (4, 5), (2, 11), (-2, 11), (-4, 5), (-8, -3), (-22, -3)]),
    ("#c8fff0", [(-2, -1), (2, -1), (2, 5), (-2, 5)]),
)
GRUB_BODY = [(-17, 0), (-12, 8), (-6, 12), (6, 12), (12, 8), (17, 0), (12, -6), (-12, -6)]
DRONE_BODY = [(-16, -2), (-8, 6), (8, 6), (16, -2), (8, -8), (-8, -8)]
WARDEN_BODY = [(0, 12), (10, 2), (8, -6), (-8, -6), (-10, 2)]


def mirror(points):
    return [(-x, y) for x, y in points]


def alien_shape(color, body, eyes, limbs):
    return [(color, body)] + [(BACKGROUND, eye) for eye in eyes] + [(color, limb) for limb in limbs]


GRUB_EYES = [[(-8, 2), (-4, 2), (-4, 6), (-8, 6)], [(4, 2), (8, 2), (8, 6), (4, 6)]]
GRUB_MIDDLE_LEG = [(-2, -6), (2, -6), (2, -12), (-2, -12)]
GRUB_LEG_OUT = [(-14, -6), (-10, -6), (-16, -12), (-20, -12)]
GRUB_LEG_IN = [(-14, -6), (-10, -6), (-8, -12), (-12, -12)]

DRONE_EYES = [[(-6, -4), (-2, -4), (-2, 1), (-6, 1)], [(2, -4), (6, -4), (6, 1), (2, 1)]]
DRONE_DOME = [(-6, 6), (-3, 11), (3, 11), (6, 6)]
DRONE_ARM_UP = [(-16, -2), (-21, 8), (-18, 8), (-13, 1)]
DRONE_ARM_DOWN = [(-16, -2), (-21, -11), (-18, -11), (-13, -5)]

WARDEN_EYES = [[(-5, 0), (-2, 0), (-2, 3), (-5, 3)], [(2, 0), (5, 0), (5, 3), (2, 3)]]
WARDEN_MIDDLE = [(-1, -6), (1, -6), (1, -12), (-1, -12)]
WARDEN_TENTACLE_OUT = [(-8, -6), (-5, -6), (-9, -12), (-12, -12)]
WARDEN_TENTACLE_IN = [(-8, -6), (-5, -6), (-3, -12), (-6, -12)]

ALIENS = {
    ("grub", 0): alien_shape("#b6f36b", GRUB_BODY, GRUB_EYES,
                             [GRUB_LEG_OUT, mirror(GRUB_LEG_OUT), GRUB_MIDDLE_LEG]),
    ("grub", 1): alien_shape("#b6f36b", GRUB_BODY, GRUB_EYES,
                             [GRUB_LEG_IN, mirror(GRUB_LEG_IN), GRUB_MIDDLE_LEG]),
    ("drone", 0): alien_shape("#ffb347", DRONE_BODY, DRONE_EYES,
                              [DRONE_DOME, DRONE_ARM_UP, mirror(DRONE_ARM_UP)]),
    ("drone", 1): alien_shape("#ffb347", DRONE_BODY, DRONE_EYES,
                              [DRONE_DOME, DRONE_ARM_DOWN, mirror(DRONE_ARM_DOWN)]),
    ("warden", 0): alien_shape("#ff5c8a", WARDEN_BODY, WARDEN_EYES,
                               [WARDEN_TENTACLE_OUT, mirror(WARDEN_TENTACLE_OUT), WARDEN_MIDDLE]),
    ("warden", 1): alien_shape("#ff5c8a", WARDEN_BODY, WARDEN_EYES,
                               [WARDEN_TENTACLE_IN, mirror(WARDEN_TENTACLE_IN), WARDEN_MIDDLE]),
}

# A zigzag line, three pixels thick.
BOLT_SPINE = [(0, 7), (-2, 3), (2, -1), (-2, -5), (0, -7)]
BOLT = [(x + 1.5, y) for x, y in BOLT_SPINE] + [(x - 1.5, y) for x, y in reversed(BOLT_SPINE)]
LASER = [(-1.5, -7), (1.5, -7), (1.5, 7), (-1.5, 7)]
BLOCK = [(-4, -4), (4, -4), (4, 4), (-4, 4)]
EXPLOSION = [
    ((14 if i % 2 == 0 else 5) * math.cos(math.pi * i / 8), (14 if i % 2 == 0 else 5) * math.sin(math.pi * i / 8))
    for i in range(16)
]


def register_shapes(screen):
    def compound(name, parts):
        shape = turtle.Shape("compound")
        for color, points in parts:
            shape.addcomponent(points, color, color)
        screen.register_shape(name, shape)

    compound("ship", SHIP)
    for (kind, frame), parts in ALIENS.items():
        compound(f"{kind}{frame}", parts)
    compound("laser", [("#e8fbff", LASER)])
    compound("bolt", [("#ff7b7b", BOLT)])
    compound("block", [("#2fbf71", BLOCK)])
    compound("explosion", [("#ffd166", EXPLOSION)])


def make_pen():
    # Without an undo buffer clearing a stamp doesn't search through it.
    pen = turtle.Turtle(visible=False, undobuffersize=0)
    pen.penup()
    pen.setheading(90)
    return pen


class StampLayer:
    """Draws objects as stamps. A stamp costs nothing to keep on the screen, so an
    object is only drawn again when it moves or changes its look."""

    def __init__(self):
        self.pen = make_pen()
        self.stamps = {}            # object -> ((shape, x, y), stamp id)

    def sync(self, objects, shape_of):
        objects = list(objects)
        for obj in self.stamps.keys() - set(objects):
            self.pen.clearstamp(self.stamps.pop(obj)[1])
        for obj in objects:
            look = (shape_of(obj), obj.x, obj.y)
            old = self.stamps.get(obj)
            if old and old[0] == look:
                continue
            if old:
                self.pen.clearstamp(old[1])
            self.pen.shape(look[0])
            self.pen.goto(obj.x, obj.y)
            self.stamps[obj] = (look, self.pen.stamp())


class View:
    def __init__(self, screen):
        self.screen = screen
        self.blocks = StampLayer()
        self.aliens = StampLayer()
        self.shots = StampLayer()
        self.ship = StampLayer()
        self.explosions = StampLayer()
        self.hud = make_pen()
        self.message = make_pen()
        self.hud_text = None
        self.message_text = None
        self.draw_ground()

    @staticmethod
    def draw_ground():
        pen = make_pen()
        pen.color("#3ef0c0")
        pen.goto(LEFT_WALL, GROUND_Y)
        pen.pendown()
        pen.goto(RIGHT_WALL, GROUND_Y)

    def draw(self, game):
        self.blocks.sync(game.blocks, lambda b: "block")
        self.aliens.sync(game.aliens, lambda a: f"{a.kind}{game.frame}")
        self.shots.sync(([game.laser] if game.laser else []) + game.bolts,
                        lambda s: "laser" if s is game.laser else "bolt")
        alive = game.lives > 0 and not game.respawning
        self.ship.sync([game.player] if alive else [], lambda p: "ship")
        self.explosions.sync(game.explosions, lambda e: "explosion")
        self.draw_hud(game)
        self.draw_message(game)

    def draw_hud(self, game):
        text = (f"SCORE {game.score:05}", f"HI {game.high_score:05}",
                f"WAVE {game.level}  LIVES {game.lives}")
        if text == self.hud_text:
            return
        self.hud_text = text
        self.hud.clear()
        self.hud.color(TEXT)
        y = CEILING_Y + 15
        for words, x, align in zip(text, (LEFT_WALL, 0, RIGHT_WALL), ("left", "center", "right")):
            self.hud.goto(x, y)
            self.hud.write(words, align=align, font=FONT)

    def draw_message(self, game):
        if game.state == "over":
            text = ("GAME OVER", "Press Enter to play again")
        elif game.state == "paused":
            text = ("PAUSED", "Press P to go on")
        else:
            text = None
        if text == self.message_text:
            return
        self.message_text = text
        self.message.clear()
        if text:
            self.message.color(TEXT)
            self.message.goto(0, -70)
            self.message.write(text[0], align="center", font=BIG_FONT)
            self.message.goto(0, -110)
            self.message.write(text[1], align="center", font=FONT)


def main():
    screen = turtle.Screen()
    screen.setup(WIDTH, HEIGHT)
    # Tk 9 doesn't centre the default 400x300 canvas in a bigger window. A canvas a
    # bit smaller than the window fills it without scrollbars.
    screen.screensize(WIDTH - 10, HEIGHT - 10)
    screen.title("Alien Siege")
    screen.bgcolor(BACKGROUND)
    screen.tracer(0)
    register_shapes(screen)

    game = Game(high_score=load_high_score(HIGH_SCORE_FILE))
    view = View(screen)
    held = set()
    running = True

    def hold(key):
        screen.onkeypress(lambda: held.add(key), key)
        screen.onkeyrelease(lambda: held.discard(key), key)

    for key in ("Left", "Right", "a", "d"):
        hold(key)

    def play_again():
        if game.state == "over":
            game.restart()

    def quit_game():
        nonlocal running
        running = False
        save_high_score(HIGH_SCORE_FILE, game.high_score)
        screen.bye()

    screen.onkeypress(game.fire, "space")
    screen.onkeypress(game.toggle_pause, "p")
    screen.onkeypress(play_again, "Return")
    screen.onkeypress(quit_game, "Escape")
    screen.getcanvas().winfo_toplevel().protocol("WM_DELETE_WINDOW", quit_game)
    screen.listen()

    last = time.perf_counter()

    def tick():
        nonlocal last
        if not running:
            return
        now = time.perf_counter()
        dt = min(now - last, MAX_DT)
        last = now
        steer = bool(held & {"Right", "d"}) - bool(held & {"Left", "a"})
        was_over = game.state == "over"
        game.update(dt, steer)
        if game.state == "over" and not was_over:
            save_high_score(HIGH_SCORE_FILE, game.high_score)
        view.draw(game)
        screen.update()
        screen.ontimer(tick, FRAME_MS)

    tick()
    screen.mainloop()


if __name__ == "__main__":
    main()
