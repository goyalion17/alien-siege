import random

import game as rules
from game import Alien, Box, Game, Shot, build_bunkers, load_high_score, save_high_score


def new_game():
    return Game(rng=random.Random(1))


def quiet_game():
    """A game where the aliens neither move nor shoot unless a test tells them to."""
    g = new_game()
    g.beat_timer = -1000
    g.shot_timer = 1000
    return g


def test_boxes_overlap_only_when_they_share_area():
    a = Box(0, 0, 10, 10)
    assert a.overlaps(Box(9, 0, 10, 10))
    assert not a.overlaps(Box(10, 0, 10, 10))     # touching edges is not a hit
    assert not a.overlaps(Box(0, 20, 10, 10))


def test_new_game_has_a_full_fleet_and_four_bunkers():
    g = new_game()
    assert len(g.aliens) == rules.COLUMNS * len(rules.ROW_KINDS)
    assert g.aliens[0].kind == "warden" and g.aliens[-1].kind == "grub"
    per_bunker = sum(line.count("#") for line in rules.BUNKER_SHAPE)
    assert len(g.blocks) == rules.BUNKERS * per_bunker
    assert g.lives == rules.LIVES and g.score == 0 and g.state == "playing"


def test_bunkers_stay_between_the_walls_and_apart():
    blocks = build_bunkers()
    assert min(b.left for b in blocks) >= rules.LEFT_WALL
    assert max(b.right for b in blocks) <= rules.RIGHT_WALL
    assert not any(a.overlaps(b) for a in blocks for b in blocks if a is not b)


def test_ship_moves_and_stops_at_the_wall():
    g = quiet_game()
    g.update(0.1, steer=1)
    assert g.player.x == rules.PLAYER_SPEED * 0.1
    for _ in range(100):
        g.update(0.05, steer=1)
    assert g.player.right == rules.RIGHT_WALL


def test_only_one_laser_at_a_time():
    g = quiet_game()
    g.fire()
    first = g.laser
    g.fire()
    assert g.laser is first


def test_laser_kills_an_alien_and_scores():
    g = quiet_game()
    g.blocks = []
    target = g.aliens[-1]
    g.laser = Shot(target.x, target.bottom - 1, rules.LASER_WIDTH, rules.LASER_HEIGHT, rules.LASER_SPEED)
    g.update(0.001)
    assert target not in g.aliens
    assert g.score == target.points == 10
    assert g.laser is None
    assert g.high_score == 10
    assert len(g.explosions) == 1


def test_laser_flies_off_the_top():
    g = quiet_game()
    g.aliens = [Alien(300, 200, rules.ALIEN_WIDTH, rules.ALIEN_HEIGHT)]
    g.blocks = []
    g.player.x = -300
    g.fire()
    for _ in range(100):
        g.update(0.02)
    assert g.laser is None
    g.fire()
    assert g.laser is not None


def test_laser_and_bolt_cancel_each_other():
    g = quiet_game()
    g.laser = Shot(0, 0, 3, 14, rules.LASER_SPEED)
    g.bolts = [Shot(0, 5, 6, 14, -rules.BOLT_SPEED)]
    g.check_hits()
    assert g.laser is None and g.bolts == []


def test_shots_chip_the_bunkers():
    g = quiet_game()
    block = g.blocks[0]
    g.bolts = [Shot(block.x, block.y, 6, 14, -rules.BOLT_SPEED)]
    before = len(g.blocks)
    g.check_hits()
    assert block not in g.blocks
    assert 0 < before - len(g.blocks) <= 4
    assert g.bolts == []


def test_fleet_steps_sideways_then_down_at_the_wall():
    g = quiet_game()
    x, y = g.aliens[0].x, g.aliens[0].y
    g.step_fleet()
    assert (g.aliens[0].x, g.aliens[0].y) == (x + rules.STEP_X, y)
    while g.direction == 1:
        g.step_fleet()
    assert g.aliens[0].y == y - rules.STEP_Y
    assert max(a.right for a in g.aliens) <= rules.RIGHT_WALL


def test_fleet_speeds_up_as_aliens_die():
    g = new_game()
    full = g.beat
    assert full == rules.FIRST_BEAT
    g.aliens = g.aliens[:1]
    assert g.beat == rules.LAST_BEAT


def test_fleet_steps_on_the_beat():
    g = new_game()
    g.shot_timer = 1000
    x = g.aliens[0].x
    g.update(rules.FIRST_BEAT - 0.01)
    assert g.aliens[0].x == x
    g.update(0.02)
    assert g.aliens[0].x == x + rules.STEP_X


def test_aliens_shoot_from_the_bottom_of_a_column():
    g = quiet_game()
    for _ in range(20):
        g.bolts = []
        g.alien_fire()
        bolt = g.bolts[0]
        shooters = [a for a in g.aliens if a.x == bolt.x]
        assert bolt.top <= min(a.bottom for a in shooters)


def test_bolt_costs_a_life_and_freezes_the_game():
    g = quiet_game()
    g.bolts = [Shot(g.player.x, g.player.y, 6, 14, -rules.BOLT_SPEED)]
    g.update(0.001)
    assert g.lives == rules.LIVES - 1
    assert g.respawning
    g.fire()
    assert g.laser is None
    g.update(rules.RESPAWN_TIME + 0.01)
    assert not g.respawning


def test_last_life_ends_the_game():
    g = quiet_game()
    g.lives = 1
    g.lose_life()
    assert g.state == "over"
    g.update(1, steer=1)
    assert g.player.x == 0


def test_aliens_reaching_the_ship_end_the_game():
    g = quiet_game()
    g.aliens[-1].y = g.player.top
    g.check_end()
    assert g.state == "over" and g.lives == 0


def test_clearing_a_wave_starts_a_faster_lower_one():
    g = quiet_game()
    top = g.aliens[0].y
    g.aliens = []
    g.check_end()
    assert g.level == 2
    assert g.aliens[0].y == top - rules.LEVEL_DROP
    assert g.beat < rules.FIRST_BEAT


def test_pause_stops_the_game():
    g = new_game()
    g.toggle_pause()
    x = g.aliens[0].x
    g.update(5)
    assert g.aliens[0].x == x
    g.toggle_pause()
    assert g.state == "playing"


def test_restart_keeps_the_high_score():
    g = quiet_game()
    g.score = g.high_score = 500
    g.state = "over"
    g.restart()
    assert g.score == 0 and g.high_score == 500 and g.state == "playing"


def test_high_score_file(tmp_path):
    path = tmp_path / "highscore.txt"
    assert load_high_score(path) == 0
    save_high_score(path, 1230)
    assert load_high_score(path) == 1230
    path.write_text("garbage")
    assert load_high_score(path) == 0
