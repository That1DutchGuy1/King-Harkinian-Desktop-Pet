#!/usr/bin/env python3
"""
King Harkinian Desktop Pet
- Made by That One Dutch Guy
- Roams your desktop with low-quality funny animations
- Plays random voice lines via pygame or aplay
- Toggle on/off with the tray icon or right-click
- Requires: python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0
- Optional (better audio): python3-pygame   OR   aplay (from alsa-utils, usually pre-installed)
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

try:
    gi.require_version("AppIndicator3", "0.1")
    HAS_INDICATOR = True
except Exception:
    HAS_INDICATOR = False

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import math
import random
import os
import subprocess
import threading

# ── Audio backend (pygame preferred, falls back to aplay) ─────────────────────
try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")  # suppresses "Hello from pygame"
    os.environ.setdefault("PYGAME_DETECT_AVX2", "1")          # suppresses AVX2 RuntimeWarning
    import pygame
    pygame.mixer.init()
    AUDIO = "pygame"
except Exception:
    AUDIO = "aplay"   # aplay ships with alsa-utils on every Ubuntu/Mint install

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PNG_PATH   = os.path.join(SCRIPT_DIR, "King-Harkinian-CD-i.png")

VOICE_LINES = [
    "Dinner.mp3",
    "Mah-Boi.mp3",
    "King-Harkinian-Laugh.mp3",
    "This-Peace-Is-What-All-True-Warriors-Strive-For.mp3",
    "scrub-all-the-floors-in-hyrule.mp3",
    "duke-onkled-under-attack.mp3",
    "enough.mp3",
    "im-going-to-gamelon.mp3",
    "hmm.mp3",
    "piece-of-shit.mp3",
    "triforce-of-courage.mp3",
    "ship-sails.mp3",
    "wonder-whats-for-dinner.mp3",
    "you-saved-me.mp3",
]
# Keep only files that actually exist next to the script
VOICE_LINES = [os.path.join(SCRIPT_DIR, f) for f in VOICE_LINES
               if os.path.isfile(os.path.join(SCRIPT_DIR, f))]

GOODBYE_CLIP      = os.path.join(SCRIPT_DIR, "king-oah.mp3")
FOOD_EXCITED_CLIP = os.path.join(SCRIPT_DIR, "king-hoa.mp3")
EATING_SFX   = os.path.join(SCRIPT_DIR, "eating.mp3")
BURP_SFX     = os.path.join(SCRIPT_DIR, "burp.mp3")
HIT_SFX      = os.path.join(SCRIPT_DIR, "hit.mp3")
FIST_PNG     = os.path.join(SCRIPT_DIR, "fist.png")
PIECE_SFX    = os.path.join(SCRIPT_DIR, "piece-of-shit.mp3")
EXPLODE_SFX  = os.path.join(SCRIPT_DIR, "explode.mp3")

DINNER_MACHINE_PNG = os.path.join(SCRIPT_DIR, "dinner-machine.png")

# Each entry: (image_path, fat_points)
# strawberry-cake has the most fat points; spaghetti the least.
# 20× the strawberry-cake fat points triggers the King's explode sequence.
FOOD_CATALOG = [
    ("pizza.png",          8),   # classic fat slice
    ("panini.png",         5),   # pressed but not *that* bad
    ("happy-meal.png",     6),   # tiny but salty
    ("chicken-bucket.png", 10),  # whole bucket of fried chicken
    ("cheesecake.png",     12),  # rich and creamy
    ("ice-cream-cone.png", 7),   # cold comfort food
    ("taco.png",           5),   # portable and greasy
    ("burger.png",         9),   # double-patty royale
    ("spaghetti.png",      3),   # SPAGHET
    ("fish-and-chips.png", 8),   # battered and fried
    ("steak.png",          11),  # prime cut bloat
    ("cheese.png",         7),   # dairy density
    ("salmon.png",          2),   # grilled and lean — practically a diet food
    ("hot-dog.png",         6), # classic, lol 
    ("strawberry-cake.png",15),  # THE MOST FATTENING ITEM — the big one
]

STRAWBERRY_CAKE_FAT = 15                        # base fat points for the cake
FAT_EXPLODE_THRESHOLD = STRAWBERRY_CAKE_FAT * 20  # 300 — explode at this total

# Build runtime list: only keep entries whose image file actually exists
FOOD_CATALOG = [(os.path.join(SCRIPT_DIR, name), pts)
                for name, pts in FOOD_CATALOG
                if os.path.isfile(os.path.join(SCRIPT_DIR, name))]

# Legacy flat list for any code that just needs paths
FOOD_IMAGES = [path for path, _ in FOOD_CATALOG]

# Quick lookup: path → fat points
FOOD_FAT_POINTS = {path: pts for path, pts in FOOD_CATALOG}

FOOD_DISPLAY_SIZE = 180  # food shown at 180×180 when placed/dragged
DINNER_MACHINE_SIZE = 200  # dinner machine display size

BASE_W, BASE_H = 268, 230
SPEED    = 3
TICK_MS  = 16        # ~60 fps

# How often the King might speak: check every N ticks, probability P
VOICE_CHECK_EVERY = 300   # ~5 seconds at 60 fps
VOICE_CHANCE      = 0.55  # 55 % chance when the timer fires


class KingPet:
    def __init__(self):
        self.base_pixbuf = GdkPixbuf.Pixbuf.new_from_file(PNG_PATH)

        # ── Alpha map for hit-testing ─────────────────────────────────────────
        # Build a flat bytearray of alpha values (one byte per pixel) so we can
        # quickly check whether the cursor is over an opaque part of the sprite
        # rather than the transparent bounding-box corners.
        #   Layout: alpha[y * sprite_w + x]  (matches pixbuf row order)
        self._alpha_w   = self.base_pixbuf.get_width()    # 268
        self._alpha_h   = self.base_pixbuf.get_height()   # 230
        self._alpha_map = self._build_alpha_map(self.base_pixbuf)
        self._ALPHA_THRESHOLD = 30   # pixels below this are "transparent"

        # Scaled-pixbuf cache — updated only when size changes, not every frame
        self._scaled_pixbuf = self.base_pixbuf
        self._cached_img_w  = -1   # sentinel: force first rescale
        self._cached_img_h  = -1

        # Current render geometry (set by _render, read by _on_draw)
        self._cur_img_w    = BASE_W
        self._cur_img_h    = BASE_H
        self._cur_canvas_w = BASE_W
        self._cur_canvas_h = BASE_H
        self._die_alpha    = 1.0

        # ── Window ────────────────────────────────────────────────────────────
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_decorated(False)
        self.win.set_app_paintable(True)
        self.win.set_keep_above(True)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_accept_focus(False)

        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.win.set_visual(visual)

        self.win.connect("draw", self._on_draw)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                            Gdk.EventMask.POINTER_MOTION_MASK)
        self.win.connect("button-press-event", self._on_click)
        self.win.connect("motion-notify-event", self._on_king_motion)

        self.image_widget = Gtk.DrawingArea()
        self.win.add(self.image_widget)

        # ── Desktop size ──────────────────────────────────────────────────────
        disp    = Gdk.Display.get_default()
        monitor = disp.get_monitor(0)
        geo     = monitor.get_geometry()
        self.desk_w = geo.width
        self.desk_h = geo.height

        # ── Animation state ───────────────────────────────────────────────────
        self.x  = float(random.randint(0, self.desk_w - BASE_W))
        self.y  = float(random.randint(0, self.desk_h - BASE_H))
        self.vx = SPEED * random.choice([-1, 1])
        self.vy = SPEED * random.choice([-1, 1])

        self.tick         = 0
        self.anim         = "walk"
        self.anim_timer   = 0
        self.squish_x     = 1.0
        self.squish_y     = 1.0
        self.angle        = 0.0
        self.bounce_phase = 0.0
        self.facing       = 1   # +1 = right (default), -1 = left

        # Per-animation scratch state
        self._creep_frozen  = 0    # ticks remaining in freeze phase
        self._glitch_sx     = 1.0  # locked random values for current glitch frame
        self._glitch_sy     = 1.0
        self._glitch_ang    = 0.0
        self._glitch_next   = 0    # tick when we next re-roll the glitch

        # -- Death animation state
        self._dying     = False
        self._die_tick  = 0

        # ── Audio state ───────────────────────────────────────────────────────
        self._audio_playing  = False   # guard: don't overlap clips
        self._voice_counter  = VOICE_CHECK_EVERY  # count down to first check
        self._voice_channel  = None    # pygame Channel for current voice line (pygame only)
        self._voice_proc     = None    # subprocess.Popen for current voice line (aplay only)

        # ── Tickle state ──────────────────────────────────────────────────────
        self._tickle_active      = False   # currently being tickled?
        self._tickle_recovery    = False   # playing the "stop tickle" wind-down?
        self._tickle_tick        = 0       # frame counter within tickle anim
        self._tickle_recovery_t  = 0       # frame counter within recovery anim
        # Cursor velocity tracking for swipe detection
        self._last_cursor_x      = -9999.0
        self._last_cursor_y      = -9999.0
        self._cursor_vx_prev     = 0.0     # previous frame cursor Δx
        self._cursor_reversals   = 0       # how many direction flips recently
        self._reversal_decay     = 0       # ticks since last reversal (cool-down)
        self._saved_anim_tickle  = "walk"
        self._saved_vx_tickle    = SPEED
        self._saved_vy_tickle    = SPEED
        # Configurable thresholds
        self._TICKLE_MIN_SPEED   = 18      # px/tick cursor must move to count
        self._TICKLE_REV_NEEDED  = 4       # reversals within window to trigger
        self._REVERSAL_WINDOW    = 20      # ticks a reversal stays "fresh"
        self._TICKLE_STOP_TICKS  = 30      # ticks of no-reversal before stop

        # ── Hit Mode state ────────────────────────────────────────────────────
        self._hit_mode           = False   # Is Hit Mode currently active?
        self._fist_pixbuf        = None    # Loaded fist image
        self._fist_win           = None    # Transparent overlay window for fist
        self._fist_x             = 0.0    # Current fist centre x (screen)
        self._fist_y             = 0.0    # Current fist centre y (screen)
        self._fist_angle         = 0.0    # Current rotation angle (degrees)
        self._fist_prev_x        = 0.0    # Previous cursor x for swipe detection
        self._fist_prev_y        = 0.0    # Previous cursor y for swipe detection
        self._fist_cursor_vx     = 0.0    # Running cursor velocity x
        self._fist_cursor_vy     = 0.0    # Running cursor velocity y
        self._hit_active         = False   # King currently flying from a hit
        self._hit_tick           = 0
        self._hit_vx             = 0.0    # Physics velocity x at moment of hit
        self._hit_vy             = 0.0    # Physics velocity y at moment of hit
        self._hit_angular_v      = 0.0    # Spin speed from hit
        self._hit_sound_cooldown = 0       # ticks remaining before hit.mp3 can play again
        self._HIT_SOUND_COOLDOWN = 14      # ~230ms minimum between hit sounds (~3 overlaps max at 60fps)
        self._oh_sound_cooldown  = 0       # ticks remaining before king-oah can play again (hit mode only)
        self._OH_SOUND_COOLDOWN  = 22      # ~370ms minimum between oh sounds in hit mode
        self._hit_recovering     = False  # Playing the indignant recovery anim
        self._hit_recover_tick   = 0
        self._HIT_RECOVER_TICKS  = 44    # ~700ms at 60fps
        self._FIST_SIZE          = 96     # Display size of the fist cursor
        self._HIT_SWIPE_SPEED    = 20     # px/tick minimum to register a hit
        self._fist_alpha_w       = 1
        self._fist_alpha_h       = 1
        self._fist_alpha_map     = None
        self._FIST_ALPHA_THR     = 30

        # ── Food / Dinner Machine state ───────────────────────────────────────
        self._food_dragging    = False   # food currently bound to cursor?
        self._food_pixbuf      = None    # pixbuf of food being dragged / placed
        self._food_placed      = False   # food has been placed on desktop
        self._food_x           = 0.0    # placed food top-left x
        self._food_y           = 0.0    # placed food top-left y
        self._eating           = False   # King is in eat sequence?
        self._eat_phase        = ""      # "run" | "eat" | "burp"
        self._eat_tick         = 0
        self._eat_target_x     = 0.0    # x the King runs toward
        self._eat_target_y     = 0.0
        self._eat_food_devour  = 0      # wobble tick for food while being eaten
        self._saved_anim       = "walk" # restore after eating
        self._saved_vx         = SPEED
        self._saved_vy         = SPEED
        self._food_alpha       = 1.0    # opacity of food window (fades out when eaten)
        self._food_scale       = 1.0    # shrink scale during eating (1.0 → 0.0)

        # ── Fat / Explode state ───────────────────────────────────────────────
        self._fat_points        = 0      # accumulated fat points across all meals
        self._fat_scale         = 1.0    # visual size multiplier from fatness (1.0 → up to ~1.8)
        self._explode_armed     = False  # True only while a genuine explode is pending/active
        self._exploding         = False  # King is in the explode sequence
        self._explode_tick      = 0
        self._explode_hidden    = False  # True during the 5-second disappear window
        self._explode_hide_t    = 0      # ticks elapsed while hidden
        self._EXPLODE_HIDE_TICKS = 300   # 5 seconds @ 60fps
        self._explode_walk_in   = False  # True while King is walking in from edge
        self._explode_walk_tick = 0      # tick counter within walk-in phase
        self._explode_walk_side = 1      # +1 = from right edge, -1 = from left edge
        self._explode_recovery  = False  # True during piece-of-shit recovery after walk-in
        self._explode_recover_t = 0

        # ── Combo score state ─────────────────────────────────────────────────
        # Score only counts hits while ALREADY airborne (2nd punch onward).
        # _combo_score   : current airborne hit count (resets when new combo starts)
        # _combo_locked  : score from the last completed combo, shown until next one
        # _combo_visible : True when the counter window should be displayed
        # _combo_airborne: True once the King has been hit at least once this flight
        #                  (so the very first launch doesn't score)
        self._combo_score    = 0
        self._combo_locked   = None   # None = never scored yet, int = last score
        self._combo_visible  = False
        self._combo_airborne = False  # flips True on first hit, scores from 2nd onward

        # ── Food particle system ──────────────────────────────────────────────
        # Each particle: [x, y, vx, vy, size, r, g, b, a, age, max_age, rot, rot_v]
        self._food_particles   = []
        self._particle_win     = None   # fullscreen transparent overlay

        # ── Blood system (explosion only) ─────────────────────────────────────
        # Drops: [x, y, vx, vy, size, a, rot, rot_v]  — flying phase
        # Splatters: [x, y, size, a, age, max_age, seed]  — landed, fades over 10 s
        self._blood_drops      = []
        self._blood_splatters  = []
        _BLOOD_SPLATTER_TICKS  = 600   # 10 s @ 60 fps
        self._BLOOD_SPLATTER_TICKS = _BLOOD_SPLATTER_TICKS

        self._pick_new_behaviour()
        self._build_tray()
        self._build_dinner_machine()
        self._build_food_window()
        self._build_particle_window()
        self._build_hit_mode_button()
        self._build_fist_window()
        self._build_score_window()

        self.win.resize(BASE_W, BASE_H)
        self.win.move(int(self.x), int(self.y))
        self.win.show_all()

        # Announce arrival — play Mah-Boi once immediately on launch
        mah_boi = os.path.join(SCRIPT_DIR, "Mah-Boi.mp3")
        if os.path.isfile(mah_boi):
            self._play_voice(mah_boi)

        GLib.timeout_add(TICK_MS, self._tick)

    # ── Audio ──────────────────────────────────────────────────────────────────
    def _play_voice(self, path):
        """Fire-and-forget audio in a daemon thread so GTK isn't blocked.

        Only voice lines go through this path; SFX use _play_sfx_nonblocking /
        _play_sfx_blocking.
        """
        if self._audio_playing or not path:
            return
        self._audio_playing = True

        def _worker():
            try:
                if AUDIO == "pygame":
                    sound = pygame.mixer.Sound(path)
                    ch = sound.play()
                    self._voice_channel = ch
                    import time
                    while ch.get_busy():
                        time.sleep(0.05)
                    self._voice_channel = None
                else:
                    proc = subprocess.Popen(["aplay", path],
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
                    self._voice_proc = proc
                    proc.wait()
                    self._voice_proc = None
            finally:
                self._audio_playing = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _stop_voice(self):
        """Immediately cut off any currently-playing voice line."""
        if AUDIO == "pygame":
            ch = self._voice_channel
            if ch is not None:
                ch.stop()
                self._voice_channel = None
        else:
            proc = self._voice_proc
            if proc is not None:
                proc.terminate()
                self._voice_proc = None
        self._audio_playing = False

    def _start_goodbye(self):
        """Fire king-oah.mp3 immediately at the start of the death animation."""
        path = GOODBYE_CLIP
        if not os.path.isfile(path):
            return
        if AUDIO == "pygame":
            try:
                sound = pygame.mixer.Sound(path)
                sound.play()
            except Exception:
                pass
        else:
            subprocess.Popen(["aplay", path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def _play_goodbye(self):
        """Wait for the goodbye clip to finish, then quit."""
        import time
        if AUDIO == "pygame":
            while pygame.mixer.get_busy():
                time.sleep(0.05)
        # aplay was Popen'd; it runs to completion on its own
        Gtk.main_quit()

    # ── Dinner Machine ────────────────────────────────────────────────────────
    def _build_dinner_machine(self):
        """Create the always-on-top dinner machine window anchored bottom-right."""
        if not os.path.isfile(DINNER_MACHINE_PNG):
            self.dm_win = None
            return

        self.dm_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            DINNER_MACHINE_PNG, DINNER_MACHINE_SIZE, DINNER_MACHINE_SIZE)

        self.dm_win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.dm_win.set_decorated(False)
        self.dm_win.set_app_paintable(True)
        self.dm_win.set_keep_above(True)
        self.dm_win.set_skip_taskbar_hint(True)
        self.dm_win.set_skip_pager_hint(True)
        self.dm_win.set_accept_focus(False)

        screen = self.dm_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.dm_win.set_visual(visual)

        self.dm_win.connect("draw", self._draw_dinner_machine)
        self.dm_win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.dm_win.connect("button-press-event", self._on_dinner_machine_click)

        self.dm_win.resize(DINNER_MACHINE_SIZE, DINNER_MACHINE_SIZE)
        # Place 40px from right, 60px from bottom (avoids taskbar)
        dm_x = self.desk_w - DINNER_MACHINE_SIZE - 40
        dm_y = self.desk_h - DINNER_MACHINE_SIZE - 60
        self.dm_win.move(dm_x, dm_y)
        self.dm_win.show_all()

    def _draw_dinner_machine(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)   # CLEAR
        cr.paint()
        cr.set_operator(2)   # OVER
        Gdk.cairo_set_source_pixbuf(cr, self.dm_pixbuf, 0, 0)
        cr.paint()
        return False

    def _on_dinner_machine_click(self, widget, event):
        """Left-click on the machine → pick a random food and bind it to cursor."""
        if event.button != 1:
            return
        if self._food_dragging or self._food_placed or self._eating:
            return  # already mid-sequence
        if not FOOD_IMAGES:
            return

        food_path = random.choice(FOOD_IMAGES)
        self._current_food_path = food_path   # remember for fat-point lookup
        self.dm_win.get_window().set_cursor(
            Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR))
        self._food_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            food_path, FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE)
        self._food_dragging = True
        self._food_drag_x = int(event.x_root) - FOOD_DISPLAY_SIZE // 2
        self._food_drag_y = int(event.y_root) - FOOD_DISPLAY_SIZE // 2
        self.food_win.move(self._food_drag_x, self._food_drag_y)
        self.food_win.show_all()

    # ── Food drag window ──────────────────────────────────────────────────────
    def _build_food_window(self):
        """Transparent window that follows the cursor while dragging food."""
        self.food_win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.food_win.set_decorated(False)
        self.food_win.set_app_paintable(True)
        self.food_win.set_keep_above(True)
        self.food_win.set_skip_taskbar_hint(True)
        self.food_win.set_skip_pager_hint(True)
        self.food_win.set_accept_focus(False)

        screen = self.food_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.food_win.set_visual(visual)

        self.food_win.connect("draw", self._draw_food_window)
        self.food_win.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK)
        self.food_win.connect("button-press-event", self._on_food_click)
        self.food_win.connect("motion-notify-event", self._on_food_motion)

        self._food_canvas_size = FOOD_DISPLAY_SIZE
        self.food_win.resize(FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE)
        # Don't show yet — shown when dragging starts

    def _draw_food_window(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        cr.set_operator(2)
        if self._food_pixbuf:
            # Wobble + shrink animation while being eaten
            if self._eating and self._eat_phase == "eat":
                t = self._eat_food_devour
                # Wobble on top of the overall shrink scale
                wobble_sx = 1.0 + 0.18 * math.sin(t * 0.8)
                wobble_sy = 1.0 - 0.18 * math.sin(t * 0.8)
                ang = 15 * math.sin(t * 0.6)
                scale = self._food_scale   # shrinks 1.0 → 0.0 as King eats
                # Canvas is sized to the diagonal (see _tick_eat_sequence), so
                # anchor transforms around the canvas centre, not the image corner
                cx = self._food_canvas_size / 2
                cy = self._food_canvas_size / 2
                cr.translate(cx, cy)
                cr.rotate(math.radians(ang))
                cr.scale(wobble_sx * scale, wobble_sy * scale)
                # Draw image centred on the canvas centre
                cr.translate(-FOOD_DISPLAY_SIZE / 2, -FOOD_DISPLAY_SIZE / 2)
            else:
                # Static (placed / dragging) — image fills the window exactly
                cr.translate(self._food_canvas_size / 2 - FOOD_DISPLAY_SIZE / 2,
                             self._food_canvas_size / 2 - FOOD_DISPLAY_SIZE / 2)
            Gdk.cairo_set_source_pixbuf(cr, self._food_pixbuf, 0, 0)
            cr.paint_with_alpha(self._food_alpha)
        return False

    # ── Particle window ───────────────────────────────────────────────────────
    def _build_particle_window(self):
        """Fullscreen transparent overlay that draws all food particles."""
        self._particle_win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._particle_win.set_decorated(False)
        self._particle_win.set_app_paintable(True)
        self._particle_win.set_keep_above(True)
        self._particle_win.set_skip_taskbar_hint(True)
        self._particle_win.set_skip_pager_hint(True)
        self._particle_win.set_accept_focus(False)

        screen = self._particle_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._particle_win.set_visual(visual)

        self._particle_win.connect("draw", self._draw_particles)
        self._particle_win.resize(self.desk_w, self.desk_h)
        self._particle_win.move(0, 0)

        # Make fully click-through so it never steals input
        self._particle_win.connect("realize", self._make_particle_click_through)
        # Don't show yet — shown only when particles are active

    def _make_particle_click_through(self, widget):
        import cairo
        gdk_win = widget.get_window()
        if gdk_win:
            gdk_win.input_shape_combine_region(cairo.Region(), 0, 0)

    def _draw_particles(self, widget, cr):
        """Draw all live particles onto the fullscreen overlay."""
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)   # CLEAR
        cr.paint()
        cr.set_operator(2)   # OVER

        for p in self._food_particles:
            px, py, vx, vy, size, r, g, b, a, age, max_age, rot, rot_v = p
            if a <= 0:
                continue
            cr.save()
            cr.translate(px, py)
            cr.rotate(math.radians(rot))
            # Draw a chunky little square pixel-chunk
            half = size / 2
            cr.set_source_rgba(r, g, b, a)
            cr.rectangle(-half, -half, size, size)
            cr.fill()
            # Tiny dark outline for the "pixel chunk" look
            cr.set_source_rgba(r * 0.5, g * 0.5, b * 0.5, a * 0.6)
            cr.set_line_width(1.0)
            cr.rectangle(-half, -half, size, size)
            cr.stroke()
            cr.restore()

        # ── Blood drops (flying) ──────────────────────────────────────────────
        for d in self._blood_drops:
            bx, by, vx, vy, size, a, rot, rot_v = d
            if a <= 0:
                continue
            cr.save()
            cr.translate(bx, by)
            cr.rotate(math.radians(rot))
            # Teardrop: elongated ellipse with a pointed tail in the direction of travel
            speed = math.hypot(vx, vy)
            stretch = min(2.6, 1.0 + speed / 14.0)
            rx = size * 0.45
            ry = size * 0.45 * stretch
            # Main drop — deep crimson
            cr.scale(rx, ry)
            cr.arc(0, 0, 1.0, 0, 2 * math.pi)
            cr.restore()   # restore before set_source so scale doesn't affect colour
            cr.save()
            cr.translate(bx, by)
            cr.rotate(math.radians(rot))
            cr.scale(rx, ry)
            cr.arc(0, 0, 1.0, 0, 2 * math.pi)
            cr.set_source_rgba(0.72, 0.04, 0.04, a)
            cr.fill()
            # Bright highlight — tiny ellipse offset toward 10-o'clock
            cr.arc(-0.28, -0.28, 0.22, 0, 2 * math.pi)
            cr.set_source_rgba(1.0, 0.35, 0.35, a * 0.55)
            cr.fill()
            cr.restore()

        # ── Blood splatters (landed, persistent) ──────────────────────────────
        for s in self._blood_splatters:
            sx, sy, size, a, age, max_age, seed = s
            if a <= 0:
                continue
            rng = random.Random(seed)   # deterministic per-splatter shape

            # Central pool — flattened ellipse hugging the floor
            cr.save()
            cr.translate(sx, sy)
            cr.scale(1.0, 0.38)   # squash vertically — it's on a floor
            cr.arc(0, 0, size * 0.5, 0, 2 * math.pi)
            cr.set_source_rgba(0.55, 0.02, 0.02, a)
            cr.fill()
            cr.restore()

            # Darker core
            cr.save()
            cr.translate(sx, sy)
            cr.scale(1.0, 0.38)
            cr.arc(0, 0, size * 0.28, 0, 2 * math.pi)
            cr.set_source_rgba(0.30, 0.0, 0.0, a)
            cr.fill()
            cr.restore()

            # Spatter arms — 5-9 irregular blobs radiating outward
            n_arms = rng.randint(5, 9)
            for i in range(n_arms):
                arm_angle  = rng.uniform(0, 2 * math.pi)
                arm_dist   = rng.uniform(size * 0.45, size * 1.05)
                blob_r     = rng.uniform(size * 0.07, size * 0.22)
                blobx      = sx + math.cos(arm_angle) * arm_dist
                bloby      = sy + math.sin(arm_angle) * arm_dist * 0.38
                cr.save()
                cr.translate(blobx, bloby)
                cr.scale(1.0, 0.38)
                cr.arc(0, 0, blob_r, 0, 2 * math.pi)
                cr.set_source_rgba(0.60, 0.03, 0.03, a * rng.uniform(0.7, 1.0))
                cr.fill()
                cr.restore()

                # Thin streak connecting arm blob to pool
                cr.save()
                cr.set_source_rgba(0.55, 0.02, 0.02, a * 0.55)
                cr.set_line_width(max(1.0, blob_r * 0.6))
                cr.move_to(sx, sy)
                cr.line_to(blobx, bloby)
                cr.stroke()
                cr.restore()

            # Tiny satellite droplets
            n_dots = rng.randint(4, 8)
            for _ in range(n_dots):
                dot_angle = rng.uniform(0, 2 * math.pi)
                dot_dist  = rng.uniform(size * 0.9, size * 1.6)
                dot_r     = rng.uniform(size * 0.03, size * 0.09)
                dotx      = sx + math.cos(dot_angle) * dot_dist
                doty      = sy + math.sin(dot_angle) * dot_dist * 0.38
                cr.save()
                cr.translate(dotx, doty)
                cr.scale(1.0, 0.38)
                cr.arc(0, 0, dot_r, 0, 2 * math.pi)
                cr.set_source_rgba(0.65, 0.05, 0.05, a * rng.uniform(0.5, 0.9))
                cr.fill()
                cr.restore()

        return False

    def _spawn_food_particles(self, count=35):
        """Sample opaque pixels from the food pixbuf and launch them as particles."""
        pb = self._food_pixbuf
        if pb is None:
            return

        # Build pixel data at display size
        scaled = pb.scale_simple(FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE,
                                 GdkPixbuf.InterpType.BILINEAR)
        has_alpha  = scaled.get_has_alpha()
        n_ch       = scaled.get_n_channels()
        rowstride  = scaled.get_rowstride()
        raw        = scaled.get_pixels()
        w          = scaled.get_width()
        h          = scaled.get_height()

        # Collect all opaque pixel positions + their colours
        opaque = []
        step = max(1, (w * h) // 800)   # sample at most ~800 candidates for speed
        for i in range(0, w * h, step):
            px_x = i % w
            px_y = i // w
            off  = px_y * rowstride + px_x * n_ch
            if has_alpha:
                alpha_val = raw[off + n_ch - 1]
                if alpha_val < 30:
                    continue
            r = raw[off]     / 255.0
            g = raw[off + 1] / 255.0
            b = raw[off + 2] / 255.0
            opaque.append((px_x, px_y, r, g, b))

        if not opaque:
            return

        # Food window's current screen position (centre of the food image)
        food_screen_x = int(self._food_x) + FOOD_DISPLAY_SIZE // 2
        food_screen_y = int(self._food_y) + FOOD_DISPLAY_SIZE // 2

        for _ in range(count):
            src_x, src_y, r, g, b = random.choice(opaque)
            # Map pixel coords to screen coords
            world_x = float(int(self._food_x) + src_x)
            world_y = float(int(self._food_y) + src_y)

            # Random outward velocity with a heavy upward bias (food flies!)
            angle   = random.uniform(-math.pi, math.pi)
            speed   = random.uniform(3, 14)
            vx      = math.cos(angle) * speed
            vy      = math.sin(angle) * speed - random.uniform(2, 8)  # upward kick

            size    = random.uniform(5, 16)   # chunky pixel chunks, very low-fi
            max_age = random.randint(35, 75)
            rot     = random.uniform(0, 360)
            rot_v   = random.uniform(-12, 12)

            self._food_particles.append(
                [world_x, world_y, vx, vy, size, r, g, b, 1.0, 0, max_age, rot, rot_v]
            )

    def _tick_particles(self):
        """Advance all particles: gravity, fade, cull dead ones."""
        GRAVITY = 0.55
        alive = []
        for p in self._food_particles:
            p[3] += GRAVITY      # vy += gravity
            p[0] += p[2]         # x  += vx
            p[1] += p[3]         # y  += vy
            p[2] *= 0.96         # drag on vx
            p[9]  += 1           # age++
            p[11] += p[12]       # rot += rot_v
            # Fade out over last 40% of life
            fade_start = p[10] * 0.6
            if p[9] > fade_start:
                p[8] = max(0.0, 1.0 - (p[9] - fade_start) / (p[10] - fade_start))
            if p[9] < p[10] and p[1] < self.desk_h + 50:
                alive.append(p)
        self._food_particles = alive

        # ── Blood drops ───────────────────────────────────────────────────────
        BLOOD_GRAVITY = 0.7
        still_flying = []
        for d in self._blood_drops:
            d[3] += BLOOD_GRAVITY   # vy += gravity
            d[0] += d[2]            # x  += vx
            d[1] += d[3]            # y  += vy
            d[2] *= 0.97            # gentle air drag on vx
            d[6] += d[7]            # rot += rot_v
            # Convert to splatter when it hits the screen floor (or goes off-screen)
            if d[1] >= self.desk_h - d[5] * 0.5:
                splat_size = d[4] * random.uniform(2.8, 4.5)  # splatters spread out
                seed       = random.randint(0, 0xFFFF)
                # [x, y, size, a, age, max_age, seed]
                self._blood_splatters.append(
                    [d[0], self.desk_h - 2, splat_size, 1.0, 0, self._BLOOD_SPLATTER_TICKS, seed]
                )
            elif d[0] > -60 and d[0] < self.desk_w + 60:
                still_flying.append(d)
        self._blood_drops = still_flying

        # ── Blood splatters — age and fade ────────────────────────────────────
        FADE_START_FRAC = 0.75   # solid for first 75 %, then fade over last 25 %
        alive_splatters = []
        for s in self._blood_splatters:
            s[4] += 1   # age++
            fade_start = s[5] * FADE_START_FRAC
            if s[4] > fade_start:
                s[3] = max(0.0, 1.0 - (s[4] - fade_start) / (s[5] - fade_start))
            if s[4] < s[5]:
                alive_splatters.append(s)
        self._blood_splatters = alive_splatters

        any_active = bool(alive or still_flying or alive_splatters)
        if any_active:
            if not self._particle_win.get_visible():
                self._particle_win.show_all()
            self._particle_win.queue_draw()
        else:
            self._particle_win.hide()

    def _on_food_motion(self, widget, event):
        if self._food_dragging:
            self._food_drag_x = int(event.x_root) - FOOD_DISPLAY_SIZE // 2
            self._food_drag_y = int(event.y_root) - FOOD_DISPLAY_SIZE // 2
            self.food_win.move(self._food_drag_x, self._food_drag_y)

    def _on_food_click(self, widget, event):
        """Left-click while dragging → place food if not on the King."""
        if event.button != 1 or not self._food_dragging:
            return
        fx = int(event.x_root) - FOOD_DISPLAY_SIZE // 2
        fy = int(event.y_root) - FOOD_DISPLAY_SIZE // 2
        # Collision check with King
        king_rect = (int(self.x), int(self.y), BASE_W, BASE_H)
        food_rect = (fx, fy, FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE)
        if self._rects_overlap(king_rect, food_rect):
            return  # Can't place on the King

        # Place the food
        self._food_dragging = False
        self._food_placed   = True
        self._food_x        = float(fx)
        self._food_y        = float(fy)
        self._food_alpha    = 1.0
        self.food_win.move(fx, fy)
        self.food_win.queue_draw()
        # Restore cursor
        if self.dm_win:
            self.dm_win.get_window().set_cursor(None)

        # Start the King's eat sequence
        self._start_eat_sequence()

    @staticmethod
    def _rects_overlap(r1, r2):
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2
        return not (x1 + w1 <= x2 or x2 + w2 <= x1 or
                    y1 + h1 <= y2 or y2 + h2 <= y1)

    # ── Eat sequence ──────────────────────────────────────────────────────────
    def _start_eat_sequence(self):
        """king-hoa.mp3, King flips toward food, runs to it, eats, burps."""
        self._eating = True
        self._eat_phase = "run"
        self._eat_tick  = 0
        self._eat_food_devour = 0
        self._food_alpha = 1.0
        self._food_scale = 1.0
        self._food_particles = []   # clear any leftover particles

        # Save current behaviour
        self._saved_anim = self.anim
        self._saved_vx   = self.vx
        self._saved_vy   = self.vy

        # Cut off any voice line so the excited HOA can be heard clearly
        self._stop_voice()
        # Play king-hoa (non-blocking, doesn't block other audio)
        self._play_sfx_nonblocking(FOOD_EXCITED_CLIP)

        # Determine which side of the food to run to
        food_cx = self._food_x + FOOD_DISPLAY_SIZE / 2
        king_cx = self.x + BASE_W / 2
        if king_cx < food_cx:
            # King is left of food → run to left side, face right
            self._eat_target_x = self._food_x - BASE_W + 20
            self.facing = 1
        else:
            # King is right of food → run to right side, face left
            self._eat_target_x = self._food_x + FOOD_DISPLAY_SIZE - 20
            self.facing = -1
        self._eat_target_y = self._food_y + FOOD_DISPLAY_SIZE / 2 - BASE_H / 2

        # Clamp target to desktop
        self._eat_target_x = max(0.0, min(float(self.desk_w - BASE_W), self._eat_target_x))
        self._eat_target_y = max(0.0, min(float(self.desk_h - BASE_H), self._eat_target_y))

    def _play_sfx_nonblocking(self, path):
        """Play a sound effect without blocking the audio_playing guard."""
        if not path or not os.path.isfile(path):
            return
        def _worker():
            try:
                if AUDIO == "pygame":
                    sound = pygame.mixer.Sound(path)
                    sound.play()
                else:
                    subprocess.Popen(["aplay", path],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _play_sfx_blocking(self, path, done_cb):
        """Play a sound effect and call done_cb (via GLib.idle_add) when done."""
        if not path or not os.path.isfile(path):
            GLib.idle_add(done_cb)
            return
        def _worker():
            try:
                if AUDIO == "pygame":
                    sound = pygame.mixer.Sound(path)
                    ch = sound.play()
                    import time
                    while ch.get_busy():
                        time.sleep(0.05)
                else:
                    subprocess.run(["aplay", path],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
            except Exception:
                pass
            GLib.idle_add(done_cb)
        threading.Thread(target=_worker, daemon=True).start()

    def _tick_eat_sequence(self):
        """Called from _tick when self._eating is True."""
        t = self._eat_tick
        self._eat_tick += 1

        if self._eat_phase == "run":
            # Flip animation for first 15 ticks (spin in place)
            if t < 15:
                self.angle    = (t / 15.0) * 360 * (1 if self.facing == 1 else -1)
                self.squish_x = self._fat_scale
                self.squish_y = self._fat_scale
                return

            # Then run toward the food target
            self.angle = 0.0
            dx = self._eat_target_x - self.x
            dy = self._eat_target_y - self.y
            dist = math.hypot(dx, dy)

            if dist > 6:
                RUN_SPEED = 9
                ratio = RUN_SPEED / dist
                self.x += dx * ratio
                self.y += dy * ratio
                # Funny run animation — rapid stomp squish (fat scale preserved)
                run_t = t - 15
                self.squish_x = (1.0 + 0.3 * math.sin(run_t * 0.7)) * self._fat_scale
                self.squish_y = (1.0 - 0.3 * math.sin(run_t * 0.7)) * self._fat_scale
                self.angle    = 10 * math.sin(run_t * 0.9)
            else:
                # Arrived at food
                self.x = self._eat_target_x
                self.y = self._eat_target_y
                self.squish_x = self._fat_scale
                self.squish_y = self._fat_scale
                self.angle    = 0.0
                self._eat_phase = "eat"
                self._eat_tick  = 0
                self._eat_food_devour = 0
                # Expand food window to diagonal so rotation never clips corners
                diag = math.ceil(math.hypot(FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE))
                self._food_canvas_size = diag
                # Recentre window so the food image stays in the same visual spot
                offset = (diag - FOOD_DISPLAY_SIZE) // 2
                self.food_win.resize(diag, diag)
                self.food_win.move(int(self._food_x) - offset,
                                   int(self._food_y) - offset)
                # Start eating sound (blocking; triggers burp on finish)
                self._play_sfx_blocking(EATING_SFX, self._on_eating_done)

        elif self._eat_phase == "eat":
            self._eat_food_devour += 1
            # King chomping animation — rapid open-close squish (fat scale preserved)
            self.squish_x = (1.0 + 0.25 * math.sin(t * 1.1)) * self._fat_scale
            self.squish_y = (1.0 - 0.25 * math.sin(t * 1.1)) * self._fat_scale
            self.angle    = 5 * math.sin(t * 0.8)

            # Food gradually shrinks as it gets eaten — driven by eating SFX duration.
            # We don't know the clip length, so we just tick the scale down ourselves;
            # _on_eating_done fires when the clip ends and overrides to 0.
            shrink_rate = 0.012   # ~83 ticks to fully disappear at 60fps ≈ 1.4 s
            self._food_scale = max(0.0, self._food_scale - shrink_rate)

            # Spray a small burst of particles on each chomp peak (~every 6 ticks)
            chomp_phase = t % 6
            if chomp_phase == 0 and self._food_scale > 0.05:
                # Burst size scales with remaining food so it tapers off naturally
                burst = max(2, int(8 * self._food_scale))
                self._spawn_food_particles(count=burst)

            self.food_win.queue_draw()

        elif self._eat_phase == "burp":
            # King shudders with satisfaction
            if t < 30:
                self.squish_x = (1.0 + 0.4 * math.sin(t * 0.5)) * self._fat_scale
                self.squish_y = (1.0 - 0.2 * math.sin(t * 0.5)) * self._fat_scale
                self.angle    = 15 * math.sin(t * 0.4)
            else:
                # All done — restore normal behaviour
                self.squish_x   = self._fat_scale
                self.squish_y   = self._fat_scale
                self.angle      = 0.0
                self._eating    = False
                self._food_placed = False
                self._food_pixbuf = None
                self.food_win.hide()
                self.anim = self._saved_anim
                self.vx   = self._saved_vx
                self.vy   = self._saved_vy
                self._pick_new_behaviour()

    def _on_eating_done(self):
        """Callback when eating.mp3 finishes — explode remaining food into particles, play burp."""
        # Force scale to zero and fire a big final explosion of whatever's left
        self._food_scale = 0.0
        if self._food_pixbuf is not None:
            remaining = max(5, int(25 * max(0.0, self._food_scale)))
            self._spawn_food_particles(count=remaining + 15)  # always a satisfying final pop

        # Accumulate fat points for this meal
        fat_pts = FOOD_FAT_POINTS.get(getattr(self, "_current_food_path", ""), 5)
        self._fat_points += fat_pts
        # Recompute visual fat scale: maps 0..threshold to 1.0..1.8
        ratio = min(1.0, self._fat_points / FAT_EXPLODE_THRESHOLD)
        self._fat_scale = 1.0 + 0.8 * ratio

        # Hide the food window now — particles carry the visual from here
        self._food_canvas_size = FOOD_DISPLAY_SIZE
        self.food_win.resize(FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE)
        self.food_win.hide()

        self._eat_phase = "burp"
        self._eat_tick  = 0
        self._play_sfx_blocking(BURP_SFX, self._on_burp_done)
        return False  # GLib.idle_add must return False

    def _on_burp_done(self):
        """Called when burp finishes; check if King has eaten enough to explode."""
        if self._fat_points >= FAT_EXPLODE_THRESHOLD and not self._explode_armed:
            self._explode_armed = True
            self._start_explode_sequence()
        return False

    # ── Explode sequence ─────────────────────────────────────────────────────
    # Tick-based phases — NO GLib timers inside the sequence itself, everything
    # is driven purely by _explode_tick so nothing can race or double-fire.
    #
    # _EXPL_OAH_TICK   = 0    → play OAH immediately on tick 0
    # _EXPL_SWELL_END  = 36   → OAH ends at ~600ms (36 ticks); swelling starts
    # _EXPL_BOOM_TICK  = 234  → 36 + 198 ticks (3300ms) → explode.mp3 + vanish
    # hidden phase     = 300 ticks (5 s) counted by _explode_hide_t
    # walk-in / recovery driven by position / _explode_recover_t

    _EXPL_SWELL_END = 36    # ticks of OAH before swelling jiggle starts
    _EXPL_BOOM_TICK = 234   # tick at which King vanishes + explode.mp3 plays

    def _start_explode_sequence(self):
        """King has hit the fat threshold — begin the explode sequence."""
        # Guard: stale GLib timeout may call this after state was already reset
        if not self._explode_armed or self._exploding:
            return False
        self._exploding        = True
        self._explode_tick     = 0
        self._explode_hidden   = False
        self._explode_walk_in  = False
        self._explode_recovery = False
        # Interrupt any other active state
        self._eating         = False
        self._hit_active     = False
        self._hit_recovering = False
        self._tickle_active  = False
        self._tickle_recovery = False
        return False

    def _tick_explode(self):
        """Called from _tick when self._exploding is True."""
        t = self._explode_tick
        self._explode_tick += 1

        # ── Tick 0: play OAH ─────────────────────────────────────────────────
        if t == 0:
            self._play_sfx_nonblocking(GOODBYE_CLIP)

        # ── Ticks 0-35: hold current fat pose while OAH plays ────────────────
        if t < self._EXPL_SWELL_END:
            self.squish_x = self._fat_scale
            self.squish_y = self._fat_scale
            self.angle    = 0.0

        # ── Ticks 36-233: goofy swelling jiggle ─────────────────────────────
        elif t < self._EXPL_BOOM_TICK:
            swell_t = t - self._EXPL_SWELL_END
            swell_dur = self._EXPL_BOOM_TICK - self._EXPL_SWELL_END  # 198
            swell = self._fat_scale + 0.6 * (swell_t / swell_dur)
            self.squish_x = swell + 0.35 * math.sin(swell_t * 1.1)
            self.squish_y = swell - 0.35 * math.sin(swell_t * 1.1)
            self.angle    = 25 * math.sin(swell_t * 0.9)
            self.x += 8 * math.sin(swell_t * 2.7)
            self.y += 6 * math.sin(swell_t * 2.1)
            self.x = max(0.0, min(float(self.desk_w - BASE_W * self.squish_x), self.x))
            self.y = max(0.0, min(float(self.desk_h - BASE_H * self.squish_y), self.y))

        # ── Tick 234: BOOM — play explode.mp3, spawn particles, vanish ───────
        elif t == self._EXPL_BOOM_TICK:
            self._play_sfx_nonblocking(EXPLODE_SFX)
            self._spawn_king_explosion_particles()
            self._spawn_blood_explosion()
            self._die_alpha      = 0.0
            self.squish_x        = 0.01
            self.squish_y        = 0.01
            self.angle           = 0.0
            self._explode_hidden = True
            self._explode_hide_t = 0
            # Reset fat state right here so nothing downstream can re-trigger
            self._fat_points    = 0
            self._fat_scale     = 1.0
            self._explode_armed = False

        # ── Hidden phase: invisible for 5 seconds ────────────────────────────
        elif self._explode_hidden:
            self._explode_hide_t += 1
            if self._explode_hide_t >= self._EXPLODE_HIDE_TICKS:
                self._explode_hidden    = False
                self._explode_walk_in   = True
                self._explode_walk_tick = 0
                self._explode_walk_side = random.choice([-1, 1])
                if self._explode_walk_side == 1:
                    self.x      = float(-BASE_W - 20)
                    self.facing = 1
                else:
                    self.x      = float(self.desk_w + 20)
                    self.facing = -1
                self.y          = float(self.desk_h - BASE_H - 10)
                self._die_alpha = 1.0
                self.squish_x   = 1.0
                self.squish_y   = 1.0
                self.angle      = 0.0

        # ── Walk-in phase ─────────────────────────────────────────────────────
        elif self._explode_walk_in:
            self._explode_walk_tick += 1
            wt = self._explode_walk_tick
            WALK_SPEED = 4
            if self._explode_walk_side == 1:
                self.x += WALK_SPEED
                done = (self.x >= 80)
            else:
                self.x -= WALK_SPEED
                done = (self.x <= self.desk_w - BASE_W - 80)
            self.squish_x   = 1.0 + 0.06 * math.sin(wt * 0.35)
            self.squish_y   = 1.0 - 0.06 * math.sin(wt * 0.35)
            self.angle      = 8 * math.sin(wt * 0.45)
            self._die_alpha = 1.0
            if done:
                self._explode_walk_in   = False
                self._explode_recovery  = True
                self._explode_recover_t = 0
                self.squish_x = 1.0
                self.squish_y = 1.0
                self.angle    = 0.0
                self._play_sfx_nonblocking(PIECE_SFX)

        # ── Recovery: hit-recovery animation, yelling piece-of-shit ──────────
        elif self._explode_recovery:
            t2 = self._explode_recover_t
            self._explode_recover_t += 1
            p = t2 / self._HIT_RECOVER_TICKS
            if p < 0.25:
                lp = p / 0.25
                self.angle    = 18 * math.sin(lp * math.pi * 5) * (1.0 - lp)
                self.squish_x = 1.0 + 0.30 * math.sin(lp * math.pi * 6)
                self.squish_y = 1.0 - 0.20 * math.sin(lp * math.pi * 6)
            elif p < 0.65:
                lp = (p - 0.25) / 0.40
                scale = 1.0 + 0.35 * math.sin(lp * math.pi)
                self.squish_x = scale + 0.12 * math.sin(lp * math.pi * 7)
                self.squish_y = scale - 0.08 * math.sin(lp * math.pi * 7)
                self.angle    = 20 * math.sin(lp * math.pi * 4)
            else:
                lp = (p - 0.65) / 0.35
                damp = (1.0 - lp) ** 2
                self.angle    = 15 * math.sin(lp * math.pi * 3) * damp
                self.squish_x = 1.0 + 0.10 * math.cos(lp * math.pi * 4) * damp
                self.squish_y = 1.0 - 0.10 * math.cos(lp * math.pi * 4) * damp
            if t2 >= self._HIT_RECOVER_TICKS:
                self.squish_x          = 1.0
                self.squish_y          = 1.0
                self.angle             = 0.0
                self._die_alpha        = 1.0
                self._exploding        = False
                self._explode_recovery = False
                self.anim = self._saved_anim
                self.vx   = self._saved_vx
                self.vy   = self._saved_vy
                self._pick_new_behaviour()

    def _spawn_king_explosion_particles(self):
        """Spawn a huge burst of particles centred on the King for the explosion."""
        centre_x = self.x + BASE_W / 2
        centre_y = self.y + BASE_H / 2
        # Use the King's sprite colours — orange/yellow/brown palette
        colours = [
            (1.0, 0.55, 0.0),  # orange
            (1.0, 0.85, 0.1),  # yellow
            (0.8, 0.3,  0.0),  # dark orange
            (0.9, 0.9,  0.9),  # white flash
            (1.0, 0.1,  0.1),  # red
        ]
        for _ in range(120):
            r, g, b = random.choice(colours)
            angle   = random.uniform(-math.pi, math.pi)
            speed   = random.uniform(5, 30)
            vx      = math.cos(angle) * speed
            vy      = math.sin(angle) * speed - random.uniform(3, 12)
            size    = random.uniform(8, 28)
            max_age = random.randint(40, 90)
            rot     = random.uniform(0, 360)
            rot_v   = random.uniform(-18, 18)
            self._food_particles.append(
                [centre_x, centre_y, vx, vy, size, r, g, b, 1.0, 0, max_age, rot, rot_v]
            )

    def _spawn_blood_explosion(self):
        """Spawn blood drops flying outward from the King's centre.

        Each drop is a dark-red teardrop that obeys gravity, lands on the
        screen floor (or any y >= desk_h - 2), and converts into a splatter
        mark that persists for 10 seconds before fading away.
        """
        centre_x = self.x + BASE_W / 2
        centre_y = self.y + BASE_H / 2

        for _ in range(90):
            angle = random.uniform(-math.pi, math.pi)
            speed = random.uniform(4, 26)
            vx    = math.cos(angle) * speed
            # Strong upward bias so drops arc nicely before falling
            vy    = math.sin(angle) * speed - random.uniform(6, 18)
            size  = random.uniform(7, 22)
            rot   = random.uniform(0, 360)
            rot_v = random.uniform(-14, 14)
            # [x, y, vx, vy, size, a, rot, rot_v]
            self._blood_drops.append(
                [centre_x, centre_y, vx, vy, size, 1.0, rot, rot_v]
            )

    # ── Combo score window ────────────────────────────────────────────────────
    def _build_score_window(self):
        """Top-left transparent overlay that shows the airborne combo counter."""
        self._score_win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._score_win.set_decorated(False)
        self._score_win.set_app_paintable(True)
        self._score_win.set_keep_above(True)
        self._score_win.set_skip_taskbar_hint(True)
        self._score_win.set_skip_pager_hint(True)
        self._score_win.set_accept_focus(False)

        screen = self._score_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._score_win.set_visual(visual)

        self._score_win.connect("draw", self._draw_score_window)

        # Fixed size — big enough for 3-digit scores + label
        self._SCORE_W = 220
        self._SCORE_H = 110
        self._score_win.resize(self._SCORE_W, self._SCORE_H)
        self._score_win.move(30, 30)   # top-left with a bit of breathing room

        # Make click-through so it never interferes with the fist
        self._score_win.connect("realize", self._make_score_click_through)
        # Hidden by default

    def _make_score_click_through(self, widget):
        import cairo
        gdk_win = widget.get_window()
        if gdk_win:
            gdk_win.input_shape_combine_region(cairo.Region(), 0, 0)

    def _draw_score_window(self, widget, cr):
        w = self._SCORE_W
        h = self._SCORE_H

        # Clear
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        cr.set_operator(2)

        # Determine what to display
        if self._combo_visible and self._combo_score > 0:
            # Live counter — pulsing gold border
            score_text  = str(self._combo_score)
            label_text  = "COMBO HIT!"
            pulse       = 0.5 + 0.5 * math.sin(self.tick * 0.35)
            bg_alpha    = 0.82
            border_r, border_g, border_b = 1.0, 0.85 - 0.15 * pulse, 0.0
            text_r, text_g, text_b       = 1.0, 1.0, 0.1 + 0.3 * pulse
        elif self._combo_locked is not None and not self._combo_visible:
            # Locked score after landing — dimmer, static
            score_text  = str(self._combo_locked)
            label_text  = "FINAL COMBO"
            pulse       = 0.0
            bg_alpha    = 0.65
            border_r, border_g, border_b = 0.7, 0.7, 0.7
            text_r, text_g, text_b       = 0.9, 0.9, 0.9
        else:
            return   # nothing to draw

        r = 14  # corner radius for rounded rect

        # Background — dark translucent panel
        cr.set_source_rgba(0.05, 0.05, 0.05, bg_alpha)
        cr.arc(r,     r,     r, math.pi,       3 * math.pi / 2)
        cr.arc(w - r, r,     r, 3 * math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0,              math.pi / 2)
        cr.arc(r,     h - r, r, math.pi / 2,   math.pi)
        cr.close_path()
        cr.fill()

        # Border
        cr.set_source_rgba(border_r, border_g, border_b, 0.95)
        cr.set_line_width(3)
        cr.arc(r,     r,     r, math.pi,       3 * math.pi / 2)
        cr.arc(w - r, r,     r, 3 * math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0,              math.pi / 2)
        cr.arc(r,     h - r, r, math.pi / 2,   math.pi)
        cr.close_path()
        cr.stroke()

        # Label (small, top)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(15)
        cr.set_source_rgba(border_r, border_g, border_b, 0.95)
        ext = cr.text_extents(label_text)
        cr.move_to((w - ext.width) / 2 - ext.x_bearing, 28)
        cr.show_text(label_text)

        # Score number (big, centred)
        cr.set_font_size(58)
        cr.set_source_rgba(text_r, text_g, text_b, 1.0)
        ext = cr.text_extents(score_text)
        cr.move_to((w - ext.width) / 2 - ext.x_bearing,
                   28 + 8 + ext.height)
        cr.show_text(score_text)

        return False

    def _show_score(self):
        if not self._score_win.get_visible():
            self._score_win.show_all()
        self._score_win.queue_draw()

    def _hide_score(self):
        self._score_win.hide()

    # ── Hit Mode ──────────────────────────────────────────────────────────────
    def _build_hit_mode_button(self):
        """Create a red 'Hit Mode' button on the opposite side from the Dinner Machine."""
        self.hit_btn_win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.hit_btn_win.set_decorated(False)
        self.hit_btn_win.set_app_paintable(True)
        self.hit_btn_win.set_keep_above(True)
        self.hit_btn_win.set_skip_taskbar_hint(True)
        self.hit_btn_win.set_skip_pager_hint(True)
        self.hit_btn_win.set_accept_focus(False)

        screen = self.hit_btn_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.hit_btn_win.set_visual(visual)

        self.hit_btn_win.connect("draw", self._draw_hit_button)
        self.hit_btn_win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                     Gdk.EventMask.ENTER_NOTIFY_MASK |
                                     Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.hit_btn_win.connect("button-press-event", self._on_hit_button_click)
        self.hit_btn_win.connect("enter-notify-event", self._on_hit_button_enter)
        self.hit_btn_win.connect("leave-notify-event", self._on_hit_button_leave)

        self._hit_btn_hover = False
        self._HIT_BTN_W = 130
        self._HIT_BTN_H = 50

        # Place on the LEFT side bottom (opposite the dinner machine which is bottom-right)
        btn_x = 40
        btn_y = self.desk_h - self._HIT_BTN_H - 60
        self.hit_btn_win.resize(self._HIT_BTN_W, self._HIT_BTN_H)
        self.hit_btn_win.move(btn_x, btn_y)
        self.hit_btn_win.show_all()

    def _draw_hit_button(self, widget, cr):
        w = self._HIT_BTN_W
        h = self._HIT_BTN_H
        r = 10  # corner radius

        # Clear
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        cr.set_operator(2)

        # Rounded rect fill
        if self._hit_mode:
            # Active: dark red / pulsing
            pulse = 0.5 + 0.5 * math.sin(self.tick * 0.18)
            cr.set_source_rgba(0.7 + 0.2 * pulse, 0.0, 0.0, 0.95)
        elif self._hit_btn_hover:
            cr.set_source_rgba(0.9, 0.1, 0.1, 0.95)
        else:
            cr.set_source_rgba(0.75, 0.05, 0.05, 0.90)

        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.arc(w - r, r, r, 3 * math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.close_path()
        cr.fill()

        # Border
        cr.set_source_rgba(1.0, 0.3, 0.3, 1.0)
        cr.set_line_width(2)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.arc(w - r, r, r, 3 * math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.close_path()
        cr.stroke()

        # Text
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.select_font_face("Sans", 0, 1)  # bold
        cr.set_font_size(14)
        label = "HIT MODE" if not self._hit_mode else "STOP HIT"
        extents = cr.text_extents(label)
        tx = (w - extents.width) / 2 - extents.x_bearing
        ty = (h - extents.height) / 2 - extents.y_bearing
        cr.move_to(tx, ty)
        cr.show_text(label)
        return False

    def _on_hit_button_enter(self, widget, event):
        self._hit_btn_hover = True
        self.hit_btn_win.queue_draw()

    def _on_hit_button_leave(self, widget, event):
        self._hit_btn_hover = False
        self.hit_btn_win.queue_draw()

    def _on_hit_button_click(self, widget, event):
        if event.button != 1:
            return
        self._toggle_hit_mode()

    def _toggle_hit_mode(self):
        self._hit_mode = not self._hit_mode
        if self._hit_mode:
            # Disable dinner machine visually (hide it)
            if self.dm_win:
                self.dm_win.hide()
            # Show fist window and attach fist to cursor
            self._fist_win.show_all()
            # Set blank cursor on the main King window and fist window
            blank = Gdk.Cursor.new_for_display(Gdk.Display.get_default(),
                                                Gdk.CursorType.BLANK_CURSOR)
            self.win.get_window().set_cursor(blank) if self.win.get_window() else None
            self._fist_win.get_window().set_cursor(blank) if self._fist_win.get_window() else None
            # Cancel any ongoing food drag/eat/tickle
            if self._food_dragging:
                self._food_dragging = False
                self.food_win.hide()
                if self.dm_win:
                    self.dm_win.get_window().set_cursor(None)
            # Reset swipe tracking
            self._fist_prev_x = -9999.0
            self._fist_prev_y = -9999.0
            self._fist_cursor_vx = 0.0
            self._fist_cursor_vy = 0.0
            self._hit_active = False
        else:
            # Re-enable dinner machine
            if self.dm_win:
                self.dm_win.show_all()
            self._fist_win.hide()
            # Hide score counter and wipe all combo state — hit mode is over
            self._combo_visible  = False
            self._combo_airborne = False
            self._combo_score    = 0
            self._combo_locked   = None
            self._hide_score()
            # Restore cursors
            self.win.get_window().set_cursor(None) if self.win.get_window() else None
            # End hit flying/recovery if active
            if self._hit_active or self._hit_recovering:
                self._hit_active     = False
                self._hit_recovering = False
                self.squish_x = 1.0
                self.squish_y = 1.0
                self.angle    = 0.0
                self.anim = self._saved_anim
                self.vx   = self._saved_vx
                self.vy   = self._saved_vy
                self._pick_new_behaviour()
        self.hit_btn_win.queue_draw()

    def _build_fist_window(self):
        """Build the fist cursor overlay window."""
        if not os.path.isfile(FIST_PNG):
            self._fist_win = Gtk.Window(type=Gtk.WindowType.POPUP)
            self._fist_win.set_decorated(False)
            self._fist_win.set_accept_focus(False)
            return

        self._fist_pixbuf_orig = GdkPixbuf.Pixbuf.new_from_file(FIST_PNG)
        self._fist_alpha_w = self._fist_pixbuf_orig.get_width()
        self._fist_alpha_h = self._fist_pixbuf_orig.get_height()
        self._fist_alpha_map = self._build_alpha_map(self._fist_pixbuf_orig)

        self._fist_win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._fist_win.set_decorated(False)
        self._fist_win.set_app_paintable(True)
        self._fist_win.set_keep_above(True)
        self._fist_win.set_skip_taskbar_hint(True)
        self._fist_win.set_skip_pager_hint(True)
        self._fist_win.set_accept_focus(False)

        screen = self._fist_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._fist_win.set_visual(visual)

        self._fist_win.connect("draw", self._draw_fist_window)
        # Only track motion — NO button events so clicks pass through to
        # windows underneath (e.g. the Hit Mode stop button).
        self._fist_win.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self._fist_win.connect("motion-notify-event", self._on_fist_motion)
        # Apply an empty input shape after realise so clicks pass through entirely.
        self._fist_win.connect("realize", self._make_fist_click_through)

        # Diagonal canvas for rotation
        diag = math.ceil(math.hypot(self._FIST_SIZE, self._FIST_SIZE))
        self._fist_canvas = diag
        self._fist_win.resize(diag, diag)
        # Don't show yet

    def _make_fist_click_through(self, widget):
        """Set an empty input shape on the fist window so all clicks fall through."""
        gdk_win = widget.get_window()
        if gdk_win is None:
            return
        # A cairo region with no rectangles = empty = no input area at all.
        import cairo
        empty_region = cairo.Region()
        gdk_win.input_shape_combine_region(empty_region, 0, 0)

    def _draw_fist_window(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        cr.set_operator(2)

        if not self._fist_pixbuf_orig:
            return False

        # Scale fist
        pb = self._fist_pixbuf_orig.scale_simple(
            self._FIST_SIZE, self._FIST_SIZE, GdkPixbuf.InterpType.BILINEAR)

        cx = self._fist_canvas / 2
        cy = self._fist_canvas / 2
        cr.translate(cx, cy)
        cr.rotate(math.radians(self._fist_angle))
        cr.translate(-self._FIST_SIZE / 2, -self._FIST_SIZE / 2)
        Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
        cr.paint()
        return False

    def _on_fist_motion(self, widget, event):
        """Track fist/cursor motion for swipe velocity and fist rotation."""
        if not self._hit_mode:
            return

        cx = event.x_root
        cy = event.y_root
        self._update_fist(cx, cy, hit_detect=True)

    def _cursor_over_hit_button(self, cx, cy):
        """Return True if (cx, cy) is within the Hit Mode button bounds."""
        bx = 40
        by = self.desk_h - self._HIT_BTN_H - 60
        return (bx <= cx <= bx + self._HIT_BTN_W and
                by <= cy <= by + self._HIT_BTN_H)

    def _update_fist(self, cx, cy, hit_detect=True):
        """Move fist to cursor, update rotation to face the King, detect swipe hits."""
        # Hide fist while hovering over the stop button so it stays clickable
        if self._cursor_over_hit_button(cx, cy):
            self._fist_win.hide()
            self._fist_prev_x = -9999.0  # reset velocity so no accidental hit on re-entry
            self._fist_prev_y = -9999.0
            self._fist_cursor_vx = 0.0
            self._fist_cursor_vy = 0.0
            return
        else:
            if not self._fist_win.get_visible():
                self._fist_win.show_all()

        # Centre the fist canvas on cursor
        half = self._fist_canvas // 2
        self._fist_win.move(int(cx) - half, int(cy) - half)
        self._fist_x = cx
        self._fist_y = cy

        # Compute direction from fist to King centre
        king_cx = self.x + BASE_W / 2
        king_cy = self.y + BASE_H / 2
        dx = king_cx - cx
        dy = king_cy - cy
        if abs(dx) > 0.1 or abs(dy) > 0.1:
            # Angle so fist "points toward" King — top of fist image aims at him
            # atan2 gives angle from positive X; we want 0° = pointing up → subtract 90°
            self._fist_angle = math.degrees(math.atan2(dy, dx)) + 90.0

        self._fist_win.queue_draw()

        # Velocity tracking and hit detection — only from real motion events,
        # not the per-tick position poll (which would double-count every hit).
        if hit_detect:
            if self._fist_prev_x != -9999.0:
                dvx = cx - self._fist_prev_x
                dvy = cy - self._fist_prev_y
                # Exponential smoothing for velocity
                alpha = 0.5
                self._fist_cursor_vx = alpha * dvx + (1 - alpha) * self._fist_cursor_vx
                self._fist_cursor_vy = alpha * dvy + (1 - alpha) * self._fist_cursor_vy

                speed = math.hypot(self._fist_cursor_vx, self._fist_cursor_vy)
                # Check if fist is over opaque King pixels
                if speed >= self._HIT_SWIPE_SPEED and self._cursor_on_sprite(int(cx), int(cy)):
                    self._trigger_hit(self._fist_cursor_vx, self._fist_cursor_vy, speed)

            self._fist_prev_x = cx
            self._fist_prev_y = cy

    def _trigger_hit(self, vx, vy, speed):
        """Launch or redirect the King with physics based on cursor velocity."""
        if self._dying:
            return

        magnitude = min(speed, 80) / 80.0
        # Heavier Kings are harder to fling — launch speed and spin scale down
        # with fatness.  At max fat (scale 1.8) he gets ~60 % of normal launch speed.
        fat_resistance = 1.0 / (0.4 + 0.6 * self._fat_scale)   # 1.0→0.625 over 1.0→1.8
        launch_speed = (8 + magnitude * 22) * fat_resistance
        norm = speed if speed > 0 else 1
        new_vx = (vx / norm) * launch_speed
        new_vy = (vy / norm) * launch_speed
        new_angular = (magnitude * 18 * fat_resistance) * random.choice([-1, 1])

        if self._hit_active:
            # Already airborne — add the new impulse on top of existing velocity
            # so rapid combos fling him harder and harder
            self._hit_vx = self._hit_vx * 0.5 + new_vx
            self._hit_vy = self._hit_vy * 0.5 + new_vy
            self._hit_angular_v = new_angular
            # ── Combo scoring: only count when the hit sound cooldown is zero ──
            # _trigger_hit fires on every motion event exceeding the speed
            # threshold, which is many times per swipe. The sound cooldown is
            # already the "this is a new distinct hit" gate, so piggyback on it.
            if self._hit_sound_cooldown <= 0:
                self._combo_score   += 1
                self._combo_visible  = True
                self._show_score()
        elif self._hit_recovering:
            # Interrupt recovery — he gets hit again mid-sulk.
            # Treat this as starting a brand-new combo (score resets).
            self._hit_recovering = False
            self._hit_active     = True
            self._hit_tick       = 0
            self._hit_vx         = new_vx
            self._hit_vy         = new_vy
            self._hit_angular_v  = new_angular
            # Reset combo — this first re-launch punch doesn't score yet
            self._combo_score    = 0
            self._combo_visible  = False
            self._combo_airborne = True   # next hit while airborne will score
            self._hide_score()
        else:
            self._hit_active = True
            self._hit_tick   = 0
            self._hit_vx     = new_vx
            self._hit_vy     = new_vy
            self._hit_angular_v = new_angular
            # Save normal state only on first hit
            self._saved_anim = self.anim
            self._saved_vx   = self.vx
            self._saved_vy   = self.vy
            # ── First launch from ground — no score yet, just arm the system ──
            self._combo_score    = 0
            self._combo_visible  = False
            self._combo_airborne = True   # next hit while airborne will score
            self._hide_score()

        # Play hit.mp3 with cooldown guard — allows a bit of overlap but prevents stacking madness
        if self._hit_sound_cooldown <= 0:
            self._play_sfx_nonblocking(HIT_SFX)
            self._hit_sound_cooldown = self._HIT_SOUND_COOLDOWN
        if self._oh_sound_cooldown <= 0:
            GLib.timeout_add(200, lambda: (self._play_sfx_nonblocking(GOODBYE_CLIP), False)[1])
            self._oh_sound_cooldown = self._OH_SOUND_COOLDOWN

    def _tick_hit_flight(self):
        """Physics tick while King is flying from a hit."""
        t = self._hit_tick
        self._hit_tick += 1
        if self._hit_sound_cooldown > 0:
            self._hit_sound_cooldown -= 1
        if self._oh_sound_cooldown > 0:
            self._oh_sound_cooldown -= 1

        # Heavier Kings fall faster and bounce less.
        # At fat_scale 1.0: gravity=0.7, bounce=0.45 (baseline)
        # At fat_scale 1.8: gravity≈1.05 (+50%), bounce≈0.30 (−33%)
        fat_t     = (self._fat_scale - 1.0) / 0.8   # 0.0 → 1.0
        GRAVITY   = 0.7  + 0.35 * fat_t
        BOUNCE    = 0.45 - 0.15 * fat_t
        FRICTION  = 0.85   # slow down on ground
        MAX_TICKS = 240    # ~4 seconds, then settle

        # Apply gravity
        self._hit_vy += GRAVITY

        # Move King
        self.x += self._hit_vx
        self.y += self._hit_vy

        # Spin
        self.angle = (self.angle + self._hit_angular_v) % 360

        # Floor bounce
        eff_h = BASE_H * abs(self.squish_y)
        if self.y + eff_h >= self.desk_h:
            self.y = self.desk_h - eff_h
            self._hit_vy = -abs(self._hit_vy) * BOUNCE
            self._hit_vx *= FRICTION
            self._hit_angular_v *= FRICTION
            # Fun squish on impact (scaled by fatness)
            self.squish_x = 1.6 * self._fat_scale
            self.squish_y = 0.4 * self._fat_scale
        else:
            # Recover squish gradually toward fat baseline
            self.squish_x += (self._fat_scale - self.squish_x) * 0.15
            self.squish_y += (self._fat_scale - self.squish_y) * 0.15

        # Wall bounces
        eff_w = BASE_W * abs(self.squish_x)
        if self.x < 0:
            self.x = 0
            self._hit_vx = abs(self._hit_vx) * BOUNCE
        if self.x + eff_w > self.desk_w:
            self.x = self.desk_w - eff_w
            self._hit_vx = -abs(self._hit_vx) * BOUNCE

        # Ceiling
        if self.y < 0:
            self.y = 0
            self._hit_vy = abs(self._hit_vy) * BOUNCE

        # End conditions — recovery only allowed when actually touching the floor
        total_v = math.hypot(self._hit_vx, self._hit_vy)
        grounded = (self.y + eff_h >= self.desk_h - 2)
        if grounded and (total_v < 1.5 and abs(self._hit_angular_v) < 1.0 or t >= MAX_TICKS):
            self._end_hit_flight()

    def _end_hit_flight(self):
        """Transition from hit-flight into the indignant recovery animation."""
        self._hit_active     = False
        self._hit_recovering = True
        self._hit_recover_tick = 0
        self.squish_x = self._fat_scale
        self.squish_y = self._fat_scale
        self.angle    = 0.0
        self._hit_vx  = 0.0
        self._hit_vy  = 0.0
        self._hit_angular_v = 0.0
        self._fist_cursor_vx = 0.0
        self._fist_cursor_vy = 0.0
        # Play piece-of-shit.mp3 — he's furious
        self._play_sfx_nonblocking(PIECE_SFX)
        # ── Lock the combo score ──────────────────────────────────────────────
        # Only lock if we actually scored (i.e. the King was hit at least twice
        # — once to launch, once while airborne).
        if self._combo_score > 0:
            self._combo_locked  = self._combo_score
            self._combo_visible = False   # switch to "locked" display mode
            self._show_score()            # keep the window visible with locked style
        else:
            # No combo achieved — hide entirely
            self._combo_visible  = False
            self._combo_airborne = False
            self._hide_score()
        self._combo_score    = 0
        self._combo_airborne = False

    def _tick_hit_recovery(self):
        """~700ms indignant rage animation synced to piece-of-shit.mp3."""
        t = self._hit_recover_tick
        self._hit_recover_tick += 1
        p = t / self._HIT_RECOVER_TICKS   # 0.0 → 1.0 over the clip

        # Phase 1 (0–25%): snap upright with an angry shudder — dusting himself off
        if p < 0.25:
            lp = p / 0.25
            self.angle    = 18 * math.sin(lp * math.pi * 5) * (1.0 - lp)
            self.squish_x = (1.0 + 0.30 * math.sin(lp * math.pi * 6)) * self._fat_scale
            self.squish_y = (1.0 - 0.20 * math.sin(lp * math.pi * 6)) * self._fat_scale

        # Phase 2 (25–65%): indignant puffed-up looming — he's LIVID
        elif p < 0.65:
            lp = (p - 0.25) / 0.40
            # Grows large and leans side to side like a furious king
            scale = 1.0 + 0.35 * math.sin(lp * math.pi)
            self.squish_x = (scale + 0.12 * math.sin(lp * math.pi * 7)) * self._fat_scale
            self.squish_y = (scale - 0.08 * math.sin(lp * math.pi * 7)) * self._fat_scale
            self.angle    = 20 * math.sin(lp * math.pi * 4)

        # Phase 3 (65–100%): settles back down, one final huffy shake
        else:
            lp = (p - 0.65) / 0.35
            damp = (1.0 - lp) ** 2
            self.angle    = 15 * math.sin(lp * math.pi * 3) * damp
            self.squish_x = (1.0 + 0.10 * math.cos(lp * math.pi * 4) * damp) * self._fat_scale
            self.squish_y = (1.0 - 0.10 * math.cos(lp * math.pi * 4) * damp) * self._fat_scale

        if t >= self._HIT_RECOVER_TICKS:
            # All done — snap clean and resume normal roaming
            self.angle    = 0.0
            self.squish_x = self._fat_scale
            self.squish_y = self._fat_scale
            self._hit_recovering = False
            self.anim = self._saved_anim
            self.vx   = self._saved_vx
            self.vy   = self._saved_vy
            self._pick_new_behaviour()

    def _quit(self, *_):
        """Trigger death animation; audio + actual quit fire at its end."""
        if self._dying:
            return
        self._dying   = True
        self._die_tick = 0

    def _maybe_speak(self):
        """Called periodically; randomly picks and plays a voice line."""
        if not VOICE_LINES:
            return
        if not self._audio_playing and random.random() < VOICE_CHANCE:
            self._play_voice(random.choice(VOICE_LINES))

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _build_tray(self):
        if HAS_INDICATOR:
            from gi.repository import AppIndicator3
            self.indicator = AppIndicator3.Indicator.new(
                "king-harkinian-pet", PNG_PATH,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            menu = Gtk.Menu()
            for label, cb in [("Toggle King Harkinian", self._toggle),
                               ("Speak!", lambda *_: self._play_voice(random.choice(VOICE_LINES)) if VOICE_LINES else None),
                               ("Quit",   self._quit)]:
                item = Gtk.MenuItem(label=label)
                item.connect("activate", cb)
                menu.append(item)
            menu.show_all()
            self.indicator.set_menu(menu)
        else:
            self.tray = Gtk.StatusIcon.new_from_file(PNG_PATH)
            self.tray.set_tooltip_text("King Harkinian – right-click to control")
            self.tray.connect("popup-menu", self._tray_menu)

    def _tray_menu(self, icon, button, time):
        menu = Gtk.Menu()
        for label, cb in [("Toggle King Harkinian", self._toggle),
                           ("Speak!", lambda *_: self._play_voice(random.choice(VOICE_LINES)) if VOICE_LINES else None),
                           ("Quit",   self._quit)]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, None, button, time)

    def _toggle(self, *_):
        if self.win.get_visible():
            self.win.hide()
        else:
            self.win.show_all()

    # ── Alpha hit-testing ─────────────────────────────────────────────────────
    @staticmethod
    def _build_alpha_map(pixbuf):
        """Extract a flat bytearray of alpha values from a pixbuf.

        GdkPixbuf stores pixels as contiguous rows of (n_channels) bytes each.
        Rows are padded to `rowstride` bytes, which may be wider than
        width * n_channels — we must skip the padding on every row.
        If the pixbuf has no alpha channel every pixel is treated as opaque.
        """
        has_alpha  = pixbuf.get_has_alpha()
        n_channels = pixbuf.get_n_channels()   # 3 (RGB) or 4 (RGBA)
        rowstride  = pixbuf.get_rowstride()
        width      = pixbuf.get_width()
        height     = pixbuf.get_height()
        raw        = pixbuf.get_pixels()       # bytes / bytearray

        if not has_alpha:
            # No alpha channel → every pixel is fully opaque
            return bytearray(b'\xff' * (width * height))

        alpha_ch = n_channels - 1              # alpha is always the last channel
        out = bytearray(width * height)
        for y in range(height):
            row_start = y * rowstride
            for x in range(width):
                out[y * width + x] = raw[row_start + x * n_channels + alpha_ch]
        return out

    def _cursor_on_sprite(self, screen_x, screen_y):
        """Return True if (screen_x, screen_y) lands on an opaque sprite pixel.

        Takes squish/facing into account so the hit-map scales with the King's
        current visual size — but ignores rotation (close enough for tickle
        detection and avoids the trig overhead every motion event).
        """
        # Effective rendered size (may differ from BASE_W/H when squished)
        eff_w = max(1, int(BASE_W * abs(self.squish_x)))
        eff_h = max(1, int(BASE_H * abs(self.squish_y)))

        # self.x / self.y is the top-left of the *image* (not the canvas).
        local_x = screen_x - int(self.x)
        local_y = screen_y - int(self.y)

        if not (0 <= local_x < eff_w and 0 <= local_y < eff_h):
            return False   # outside bounding box entirely

        # Account for horizontal flip (facing == -1)
        if self.facing == -1:
            local_x = eff_w - 1 - local_x

        # Map rendered pixel → original sprite pixel
        src_x = int(local_x * self._alpha_w / eff_w)
        src_y = int(local_y * self._alpha_h / eff_h)

        # Clamp (shouldn't be needed but rounding can nudge us 1px over)
        src_x = min(src_x, self._alpha_w  - 1)
        src_y = min(src_y, self._alpha_h - 1)

        alpha = self._alpha_map[src_y * self._alpha_w + src_x]
        return alpha > self._ALPHA_THRESHOLD

    # ── Tickle detection ──────────────────────────────────────────────────────
    def _on_king_motion(self, widget, event):
        """Track cursor velocity over the King sprite; detect rapid rubbing."""
        # Don't interfere with eating/dying/hit mode
        if self._dying or self._eating or self._hit_mode:
            return

        cx = event.x_root
        cy = event.y_root

        # Only count motion that lands on an opaque sprite pixel —
        # rubbing the transparent corners shouldn't tickle anyone 👑
        if not self._cursor_on_sprite(int(cx), int(cy)):
            self._last_cursor_x = cx
            self._last_cursor_y = cy
            return

        if self._last_cursor_x == -9999.0:
            self._last_cursor_x = cx
            self._last_cursor_y = cy
            return

        dvx = cx - self._last_cursor_x
        dvy = cy - self._last_cursor_y
        speed = math.hypot(dvx, dvy)

        # Only care about fast swipes
        if speed >= self._TICKLE_MIN_SPEED:
            # Direction reversal on X axis (dominant axis for rubbing)
            if self._cursor_vx_prev != 0 and math.copysign(1, dvx) != math.copysign(1, self._cursor_vx_prev):
                self._cursor_reversals = min(self._cursor_reversals + 1,
                                             self._TICKLE_REV_NEEDED + 3)
                self._reversal_decay = self._TICKLE_STOP_TICKS   # reset idle timer
            self._cursor_vx_prev = dvx

        self._last_cursor_x = cx
        self._last_cursor_y = cy

        # Trigger tickle if threshold met
        if (self._cursor_reversals >= self._TICKLE_REV_NEEDED
                and not self._tickle_active
                and not self._tickle_recovery):
            self._start_tickle()

    def _start_tickle(self):
        self._tickle_active    = True
        self._tickle_recovery  = False
        self._tickle_tick      = 0
        self._saved_anim_tickle = self.anim
        self._saved_vx_tickle   = self.vx
        self._saved_vy_tickle   = self.vy
        # Cut off any voice line that was playing so the tickle scream interrupts it
        self._stop_voice()
        # First scream immediately, then let _tick_tickle spam more
        self._play_sfx_nonblocking(GOODBYE_CLIP)

    def _stop_tickle(self):
        """Transition from active tickle → recovery jiggle."""
        self._tickle_active    = False
        self._tickle_recovery  = True
        self._tickle_recovery_t = 0
        self._cursor_reversals  = 0
        self._cursor_vx_prev    = 0.0

    def _tick_tickle(self):
        """Called from _tick when tickle is active."""
        t = self._tickle_tick
        self._tickle_tick += 1

        # Decay reversal idle timer; stop if cursor has calmed down
        self._reversal_decay -= 1
        if self._reversal_decay <= 0:
            self._cursor_reversals = max(0, self._cursor_reversals - 1)
        if self._cursor_reversals < 2 and t > 10:
            self._stop_tickle()
            return

        # Spam king-oah every ~18 frames (overlapping, non-blocking)
        if t % 18 == 0:
            self._play_sfx_nonblocking(GOODBYE_CLIP)

        # Wild squirming animation: rapid alternating lean + squish + bounce
        phase = t * 0.55
        lean_amp  = 22 + 10 * math.sin(t * 0.08)   # lean gets wilder over time
        squish_f  = 0.28 + 0.10 * abs(math.sin(t * 0.06))

        self.angle    = lean_amp * math.sin(phase)
        self.squish_x = (1.0 + squish_f * math.cos(phase * 1.3)) * self._fat_scale
        self.squish_y = (1.0 - squish_f * math.cos(phase * 1.3)) * self._fat_scale

        # Micro-jitter position so he wriggles in place
        self.x += 5 * math.sin(t * 1.7)
        self.y += 3 * math.sin(t * 2.1 + 1.0)
        # Keep on screen
        self.x = max(0.0, min(float(self.desk_w - BASE_W), self.x))
        self.y = max(0.0, min(float(self.desk_h - BASE_H), self.y))

    def _tick_tickle_recovery(self):
        """Brief dignity-restoration jiggle after tickling stops."""
        t = self._tickle_recovery_t
        self._tickle_recovery_t += 1

        RECOVERY_DUR = 40
        if t >= RECOVERY_DUR:
            # All done — snap back to normal
            self.angle    = 0.0
            self.squish_x = self._fat_scale
            self.squish_y = self._fat_scale
            self._tickle_recovery = False
            self.anim = self._saved_anim_tickle
            self.vx   = self._saved_vx_tickle
            self.vy   = self._saved_vy_tickle
            return

        # Exponentially damped wobble — like he's shaking it off
        p = t / RECOVERY_DUR
        damp = (1.0 - p) ** 2
        self.angle    = 18 * math.sin(t * 0.45) * damp
        self.squish_x = (1.0 + 0.18 * math.cos(t * 0.55) * damp) * self._fat_scale
        self.squish_y = (1.0 - 0.18 * math.cos(t * 0.55) * damp) * self._fat_scale

    def _on_click(self, widget, event):
        if event.button == 1:   # left-click → speak immediately
            self._play_voice(random.choice(VOICE_LINES)) if VOICE_LINES else None
        elif event.button == 3: # right-click → quit
            self._quit()

    # ── Behaviour scheduler ───────────────────────────────────────────────────
    BEHAVIOURS = [
        ("walk",      120),
        ("bounce",     90),
        ("spin",       60),
        ("squish",     80),
        ("shake",      50),
        ("zoom",       70),
        ("tilt",       100),  # slow seasick rocking side to side
        ("stomp",       60),  # rapid vertical pounding like he's throwing a tantrum
        ("panic",       80),  # erratic zigzag sprinting, very fast
        ("nod",         70),  # enthusiastic vertical squash-and-stretch
        ("moonwalk",    90),  # slides backwards while facing forwards
        ("vibrate",     45),  # extremely fast tiny jitter like a broken appliance
        ("warp",        75),  # VHS bad-tape horizontal/vertical distortion flicker
        ("chalice",     90),  # leans forward and looms large — presenting the chalice
        ("flatline",   100),  # squashes pancake-flat and creeps along the ground
        ("dizzy",       80),  # figure-8 wobble like he got bonked on the head
        ("creep",      110),  # freezes then SNAPS to a new spot like low-budget horror
        ("glitch",      55),  # corrupted CD-i data — random scale/angle snaps
        ("royalwave",   80),  # grows tall and regal then wobbles side to side blessing the crowd
        ("teleport",    60),  # vanishes and reappears across the screen like a broken powerpoint
        ("stretch",     90),  # gets incredibly tall and thin then snaps back to normal
        ("helicopter",  70),  # spins while drifting sideways like a very confused king
        ("hiccup",      75),  # random sharp jolts like he's absolutely hammered at dinner
        ("microwave",   65),  # rotates slowly while pulsing in size like he's being reheated
    ]

    def _pick_new_behaviour(self):
        name, duration = random.choice(self.BEHAVIOURS)
        self.anim       = name
        self.anim_timer = duration
        self.angle      = 0.0
        self.bounce_phase = 0.0
        self._creep_frozen = 0          # reset so creep starts with a freeze
        self._glitch_next  = self.tick  # reset so glitch rolls immediately
        if random.random() < 0.3: self.vx *= -1
        if random.random() < 0.3: self.vy *= -1

    # ── Main tick ─────────────────────────────────────────────────────────────
    def _tick(self):
        if self._dying:
            self._tick_death()
            return True

        self.tick += 1

        # Redraw Hit Mode button if active (for pulse animation)
        if self._hit_mode:
            self.hit_btn_win.queue_draw()

        # Redraw score window every tick so the pulse animation runs smoothly
        if self._score_win.get_visible():
            self._score_win.queue_draw()

        # Poll global pointer for fist tracking when in Hit Mode.
        # hit_detect=False: only update fist position/rotation, no swipe detection —
        # that runs exclusively from the motion event so hits aren't counted twice.
        if self._hit_mode:
            disp = Gdk.Display.get_default()
            seat = disp.get_default_seat()
            ptr  = seat.get_pointer()
            scr, px, py = ptr.get_position()
            self._update_fist(float(px), float(py), hit_detect=False)

        # Update food drag position by polling the global pointer
        if self._food_dragging:
            disp = Gdk.Display.get_default()
            seat = disp.get_default_seat()
            ptr  = seat.get_pointer()
            scr, px, py = ptr.get_position()
            nx = px - FOOD_DISPLAY_SIZE // 2
            ny = py - FOOD_DISPLAY_SIZE // 2
            if nx != self._food_drag_x or ny != self._food_drag_y:
                self._food_drag_x = nx
                self._food_drag_y = ny
                self.food_win.move(nx, ny)

        # Tick food particles every frame regardless of other state
        if self._food_particles or self._blood_drops or self._blood_splatters:
            self._tick_particles()

        # Explode sequence takes top priority
        if self._exploding:
            self._tick_explode()
            self._render()
            return True

        # Hit flight physics takes priority in Hit Mode
        if self._hit_active:
            self._tick_hit_flight()
            self._render()
            return True

        # Indignant recovery after being hit
        if self._hit_recovering:
            self._tick_hit_recovery()
            self._render()
            return True

        if self._eating:
            self._tick_eat_sequence()
            self._render()
            return True

        # Tickle is disabled in Hit Mode
        if not self._hit_mode:
            if self._tickle_active:
                self._tick_tickle()
                self._render()
                return True

            if self._tickle_recovery:
                self._tick_tickle_recovery()
                self._render()
                return True

        self.anim_timer -= 1
        if self.anim_timer <= 0:
            self._pick_new_behaviour()

        # Voice line timer
        self._voice_counter -= 1
        if self._voice_counter <= 0:
            self._voice_counter = VOICE_CHECK_EVERY + random.randint(-60, 60)
            self._maybe_speak()

        self._update_animation()
        # Apply fatness scale on top of whatever the animation set
        if self._fat_scale != 1.0:
            self.squish_x *= self._fat_scale
            self.squish_y *= self._fat_scale
        self._move()
        self._render()
        return True

    def _tick_death(self):
        # 3-phase death: 0-20 shocked flail, 20-50 spin+shrink, 50-80 fade out
        d = self._die_tick
        self._die_tick += 1

        if d == 0:
            self._start_goodbye()  # fire audio immediately, animation plays over it

        if d < 20:
            self.squish_x   = 1.0 + 0.55 * math.sin(d * 1.9)
            self.squish_y   = 1.0 - 0.55 * math.sin(d * 1.9)
            self.angle      = 30 * math.sin(d * 1.4)
            self._die_alpha = 1.0
            self.x += 9 * math.sin(d * 2.3)
            self.y += 6 * math.sin(d * 1.8)

        elif d < 50:
            p = (d - 20) / 30.0
            scale = 1.0 - 0.85 * p
            self.squish_x   = scale
            self.squish_y   = scale
            self.angle      = (d * 18) % 360
            self._die_alpha = 1.0 - 0.5 * p

        elif d < 80:
            p = (d - 50) / 30.0
            scale = 0.15 - 0.13 * p
            self.squish_x   = max(0.01, scale)
            self.squish_y   = max(0.01, scale)
            self.angle      = (d * 22) % 360
            self._die_alpha = max(0.0, 0.5 - 0.5 * p)

        else:
            # Animation done -- wait for audio to finish, then quit
            self.squish_x   = 0.01
            self.squish_y   = 0.01
            self._die_alpha = 0.0
            self._render()
            t = threading.Thread(target=self._play_goodbye, daemon=True)
            t.start()
            return

        self._render()

    def _update_animation(self):
        t = self.tick
        a = self.anim

        if a == "walk":
            self.squish_x = 1.0 + 0.04 * math.sin(t * 0.25)
            self.squish_y = 1.0 - 0.04 * math.sin(t * 0.25)
            self.angle = 0.0

        elif a == "bounce":
            self.bounce_phase = (t % 30) / 30.0
            if self.bounce_phase < 0.5:
                p = self.bounce_phase * 2
                self.squish_x = 1.0 - 0.25 * math.sin(p * math.pi)
                self.squish_y = 1.0 + 0.25 * math.sin(p * math.pi)
            else:
                p = (self.bounce_phase - 0.5) * 2
                self.squish_x = 1.0 + 0.35 * math.sin(p * math.pi)
                self.squish_y = 1.0 - 0.35 * math.sin(p * math.pi)
            self.angle = 0.0

        elif a == "spin":
            self.angle    = (t * 12) % 360
            self.squish_x = 1.0
            self.squish_y = 1.0

        elif a == "squish":
            freq = 0.18
            self.squish_x = 1.0 + 0.4 * math.sin(t * freq)
            self.squish_y = 1.0 - 0.3 * math.sin(t * freq)
            self.angle = 0.0

        elif a == "shake":
            self.squish_x = 1.0
            self.squish_y = 1.0
            self.angle    = 20 * math.sin(t * 0.6)

        elif a == "zoom":
            scale         = 1.0 + 0.5 * math.sin(t * 0.12)
            self.squish_x = scale
            self.squish_y = scale
            self.angle    = 0.0

        elif a == "tilt":
            # Slow seasick rocking — leans far left and right like he's on a ship
            self.angle    = 35 * math.sin(t * 0.08)
            self.squish_x = 1.0
            self.squish_y = 1.0

        elif a == "stomp":
            # Rapid vertical pounding — squashes hard on the beat like a tantrum
            phase = (t % 10) / 10.0
            impact = math.pow(math.sin(phase * math.pi), 3)  # sharp hit, soft release
            self.squish_x = 1.0 + 0.45 * impact
            self.squish_y = 1.0 - 0.45 * impact
            self.angle    = 0.0

        elif a == "panic":
            # Frantic zigzag — slight lean in travel direction, wobbles wildly
            self.squish_x = 1.0 + 0.06 * math.sin(t * 0.9)
            self.squish_y = 1.0 - 0.06 * math.sin(t * 0.9)
            self.angle    = -12 * math.sin(t * 0.7)  # frantic leaning

        elif a == "nod":
            # Enthusiastic vertical squash — tall-thin, short-wide, tall-thin
            phase = (t % 20) / 20.0
            nod = math.sin(phase * 2 * math.pi)
            self.squish_x = 1.0 - 0.2 * nod
            self.squish_y = 1.0 + 0.3 * nod
            self.angle    = 0.0

        elif a == "moonwalk":
            # Slides in the direction OPPOSITE to facing — cool guy energy
            self.squish_x = 1.0 + 0.03 * math.sin(t * 0.3)
            self.squish_y = 1.0 - 0.03 * math.sin(t * 0.3)
            self.angle    = 0.0

        elif a == "vibrate":
            # Extremely fast tiny jitter — like he touched an electric fence
            self.squish_x = 1.0 + 0.08 * math.sin(t * 2.8)
            self.squish_y = 1.0 - 0.08 * math.sin(t * 2.8)
            self.angle    = 8 * math.sin(t * 3.1)

        elif a == "warp":
            # Bad VHS tape — alternates between squashing wide and squashing tall
            # with a rapid flicker so it looks like corrupted video signal
            warp_phase = (t % 8) / 8.0
            if warp_phase < 0.5:
                warp = math.sin(warp_phase * 2 * math.pi)
                self.squish_x = 1.0 + 0.6 * warp
                self.squish_y = 1.0 - 0.4 * warp
            else:
                warp = math.sin((warp_phase - 0.5) * 2 * math.pi)
                self.squish_x = 1.0 - 0.3 * warp
                self.squish_y = 1.0 + 0.55 * warp
            self.angle = 0.0

        elif a == "chalice":
            # Leans forward and dramatically LOOMS, growing towards the viewer
            # like he's personally shoving the chalice in your face
            phase = (t % 60) / 60.0
            loom  = math.sin(phase * 2 * math.pi)
            scale = 1.0 + 0.55 * max(0.0, loom)   # only grows, snaps back
            self.squish_x = scale
            self.squish_y = scale
            self.angle    = 8 * math.sin(t * 0.07)  # slight proud lean

        elif a == "flatline":
            # Pancakes completely flat to the floor then slowly creeps around
            # like a condemned royal trying to escape under a door
            squash_cycle = (t % 80) / 80.0
            if squash_cycle < 0.15:        # rapid squash-down
                p = squash_cycle / 0.15
                self.squish_y = 1.0 - 0.82 * p
                self.squish_x = 1.0 + 0.7 * p
            elif squash_cycle < 0.85:      # stays flat and creeps
                self.squish_y = 0.18
                self.squish_x = 1.7
            else:                          # pops back up
                p = (squash_cycle - 0.85) / 0.15
                self.squish_y = 0.18 + 0.82 * p
                self.squish_x = 1.7  - 0.7  * p
            self.angle = 0.0

        elif a == "dizzy":
            # Figure-8 shaped wobble on both axes — like he got smacked with a frying pan
            # X wobble and Y wobble are 90° out of phase so it traces an ellipse
            self.angle    = 25 * math.sin(t * 0.11)
            self.squish_x = 1.0 + 0.15 * math.sin(t * 0.22)
            self.squish_y = 1.0 + 0.15 * math.cos(t * 0.22)

        elif a == "creep":
            # Completely still for ~2 seconds, then INSTANTLY snaps several pixels
            # in a random direction — like a low-budget haunted portrait
            self.squish_x = 1.0
            self.squish_y = 1.0
            self.angle    = 0.0
            if self._creep_frozen <= 0:
                self._creep_frozen = random.randint(50, 90)   # freeze duration
            # movement is handled in _move(); just count down here
            self._creep_frozen -= 1

        elif a == "glitch":
            # Corrupted CD-i disc — holds a random distorted pose for a few frames
            # then snaps to a completely different one with no interpolation
            if t >= self._glitch_next:
                self._glitch_sx  = random.uniform(0.4, 1.8)
                self._glitch_sy  = random.uniform(0.4, 1.8)
                self._glitch_ang = random.choice([0, 0, 0, 15, -15, 30, -30, 45, 90, 180])
                self._glitch_next = t + random.randint(3, 12)  # hold for 3-12 frames
            self.squish_x = self._glitch_sx
            self.squish_y = self._glitch_sy
            self.angle    = float(self._glitch_ang)

        elif a == "royalwave":
            # Grows impressively tall and regal, then sways side to side
            # like he's personally blessing the entire kingdom
            phase = (t % 100) / 100.0
            if phase < 0.25:        # rise up majestically
                p = phase / 0.25
                self.squish_y = 1.0 + 0.55 * p
                self.squish_x = 1.0 - 0.20 * p
            elif phase < 0.75:      # sway side to side at full height
                lp = (phase - 0.25) / 0.50
                self.squish_y = 1.55
                self.squish_x = 0.80
                self.angle    = 22 * math.sin(lp * 2 * math.pi * 2.5)
            else:                   # deflate back to normal
                p = (phase - 0.75) / 0.25
                self.squish_y = 1.55 - 0.55 * p
                self.squish_x = 0.80 + 0.20 * p
                self.angle    = 22 * math.sin(p * math.pi) * (1.0 - p)

        elif a == "teleport":
            # Rapidly squashes to nothing, then re-expands at a completely random
            # spot on screen — like a very cheap PowerPoint "appear" effect
            phase = (t % 30) / 30.0
            if phase < 0.30:        # squash down to invisible
                p = phase / 0.30
                self.squish_x = 1.0 + 0.8 * p   # squishes wide before vanishing
                self.squish_y = max(0.02, 1.0 - p)
                self.angle    = 0.0
            elif phase < 0.35:      # TELEPORT — handled in _move()
                self.squish_x = 0.02
                self.squish_y = 0.02
                self.angle    = 0.0
            elif phase < 0.65:      # re-expand with a pop at the new spot
                p = (phase - 0.35) / 0.30
                pop = math.sin(p * math.pi)      # overshoot then settle
                self.squish_x = 0.02 + 1.6 * p - 0.4 * pop
                self.squish_y = 0.02 + 1.4 * p + 0.3 * pop
                self.angle    = 15 * math.sin(p * math.pi * 3) * (1.0 - p)
            else:                   # settle back to normal
                p = (phase - 0.65) / 0.35
                self.squish_x = 1.2 - 0.2 * p
                self.squish_y = 1.3 - 0.3 * p
                self.angle    = 0.0

        elif a == "stretch":
            # Gets FREAKISHLY tall and noodle-thin, wavers like a wet noodle,
            # then suddenly snaps back — deeply unsettling King energy
            phase = (t % 80) / 80.0
            if phase < 0.20:        # rapid stretch upward
                p = phase / 0.20
                self.squish_y = 1.0 + 1.6 * p     # up to 2.6× tall
                self.squish_x = 1.0 - 0.55 * p    # down to 0.45× wide
                self.angle    = 0.0
            elif phase < 0.65:      # noodle-wave at max stretch
                lp = (phase - 0.20) / 0.45
                self.squish_y = 2.6
                self.squish_x = 0.45
                # Sine wave ripple along the height axis (faked via angle oscillation)
                self.angle    = 12 * math.sin(lp * math.pi * 5)
            else:                   # SNAP back
                p = (phase - 0.65) / 0.35
                # Over-corrects (briefly wide+short) then normalises
                bounce = math.exp(-p * 6) * math.cos(p * math.pi * 4)
                self.squish_y = 1.0 + 0.4 * bounce
                self.squish_x = 1.0 - 0.15 * bounce
                self.angle    = 8 * bounce

        elif a == "helicopter":
            # Full 360° spin while drifting horizontally — the King has ascended
            # and is now an autonomous airborne unit
            self.angle    = (t * 15) % 360    # spin fast like rotor blades
            # Scale pulses slightly so it looks like he's bouncing in the air
            self.squish_x = 1.0 + 0.08 * math.sin(t * 0.4)
            self.squish_y = 1.0 - 0.08 * math.sin(t * 0.4)

        elif a == "hiccup":
            # Random sharp jolts upward at irregular intervals — like he drank
            # too much of whatever's in that chalice, which, honestly, fair enough
            # Base idle pose
            self.angle    = 3 * math.sin(t * 0.08)   # gentle sway between hiccups
            self.squish_x = 1.0
            self.squish_y = 1.0
            # Sharp jolt every ~22 ticks with some randomness
            hiccup_phase = t % 22
            if hiccup_phase == 0 and random.random() < 0.70:   # 70% chance each beat
                self._hiccup_active = getattr(self, "_hiccup_active", 0) + 1
            active = getattr(self, "_hiccup_active", 0)
            if active > 0:
                jolt_t = active
                self._hiccup_active -= 1
                # Sharp upward squash
                self.squish_y = 1.0 + 0.55 * math.exp(-jolt_t * 0.4)
                self.squish_x = 1.0 - 0.30 * math.exp(-jolt_t * 0.4)
                self.angle    = 12 * math.sin(jolt_t * 1.8) * math.exp(-jolt_t * 0.3)

        elif a == "microwave":
            # Rotates smoothly and slowly like he's on a microwave turntable
            # while pulsing in and out — DINNER is being prepared
            self.angle    = (t * 2.5) % 360           # slow dignified rotation
            pulse = 1.0 + 0.20 * math.sin(t * 0.22)  # gentle in-out pulse
            self.squish_x = pulse
            self.squish_y = pulse

    def _move(self):
        if self.anim == "spin":
            self.x += self.vx * 0.3
            self.y += self.vy * 0.3
        elif self.anim == "shake":
            self.x += 6 * math.sin(self.tick * 0.8)
        elif self.anim == "stomp":
            self.x += self.vx * 0.1   # pounds almost in place
            self.y += self.vy * 0.1
        elif self.anim == "panic":
            self.x += self.vx * 2.2   # sprints at double speed
            self.y += self.vy * 2.2 + 4 * math.sin(self.tick * 0.5)  # zigzag
        elif self.anim == "tilt":
            self.x += self.vx * 0.4   # dignified slow drift
            self.y += self.vy * 0.4
        elif self.anim == "vibrate":
            self.x += self.vx * 0.15 + 3 * math.sin(self.tick * 3.3)  # rattles on spot
            self.y += self.vy * 0.15 + 3 * math.cos(self.tick * 2.9)
        elif self.anim == "moonwalk":
            self.x -= self.vx          # moves BACKWARDS relative to facing
            self.y += self.vy * 0.3
        elif self.anim == "warp":
            self.x += self.vx * 0.5   # drifts slowly while distorting
            self.y += self.vy * 0.5
        elif self.anim == "chalice":
            self.x += self.vx * 0.2   # barely moves — he's busy looming at YOU
            self.y += self.vy * 0.2
        elif self.anim == "flatline":
            # Only moves while actually flat (mid-cycle)
            cycle = (self.tick % 80) / 80.0
            if 0.15 <= cycle < 0.85:
                self.x += self.vx * 0.8   # creeps along the ground
                self.y += self.vy * 0.3
        elif self.anim == "dizzy":
            self.x += self.vx * 0.35  # stumbles slowly
            self.y += self.vy * 0.35
        elif self.anim == "creep":
            if self._creep_frozen <= 0:
                # Snap! Teleport a chunky random distance
                self.x += random.choice([-1, 1]) * random.randint(40, 120)
                self.y += random.choice([-1, 1]) * random.randint(20, 80)
        elif self.anim == "glitch":
            # Teleports randomly every few frames like corrupted position data
            if self.tick >= self._glitch_next - 1:   # same frame as the re-roll
                self.x += random.choice([-1, 1]) * random.randint(0, 30)
                self.y += random.choice([-1, 1]) * random.randint(0, 20)
        elif self.anim == "royalwave":
            self.x += self.vx * 0.25   # barely moves — he's busy being majestic
            self.y += self.vy * 0.25
        elif self.anim == "teleport":
            phase = (self.tick % 30) / 30.0
            if 0.30 <= phase < 0.35:
                # The teleport frame — snap to a random spot on screen
                self.x = float(random.randint(0, max(0, self.desk_w - BASE_W)))
                self.y = float(random.randint(0, max(0, self.desk_h - BASE_H)))
            # No movement otherwise — the teleport IS the movement
        elif self.anim == "stretch":
            self.x += self.vx * 0.15   # barely drifts while being a noodle
            self.y += self.vy * 0.15
        elif self.anim == "helicopter":
            self.x += self.vx * 1.6    # drifts quickly sideways — he's flying!
            self.y += self.vy * 0.4    # minimal vertical drift
        elif self.anim == "hiccup":
            # Staggers slightly on each hiccup
            active = getattr(self, "_hiccup_active", 0)
            self.x += self.vx * 0.3 + (3 * random.choice([-1, 0, 0, 1]) if active else 0)
            self.y += self.vy * 0.3 - (8 if active else 0)   # lurches upward on jolt
        elif self.anim == "microwave":
            self.x += self.vx * 0.18   # slow dignified revolution around the desktop
            self.y += self.vy * 0.18
        else:
            self.x += self.vx
            self.y += self.vy

        # Track facing -- some anims lock or ignore facing
        if self.anim not in ("shake", "vibrate", "stomp", "moonwalk",
                             "flatline", "creep", "glitch",
                             "helicopter", "microwave", "teleport") and self.vx != 0:
            self.facing = 1 if self.vx > 0 else -1

        eff_w = BASE_W * abs(self.squish_x)
        eff_h = BASE_H * abs(self.squish_y)
        if self.x < 0:                    self.x = 0;                   self.vx =  abs(self.vx)
        if self.x + eff_w > self.desk_w:  self.x = self.desk_w - eff_w; self.vx = -abs(self.vx)
        if self.y < 0:                    self.y = 0;                   self.vy =  abs(self.vy)
        if self.y + eff_h > self.desk_h:  self.y = self.desk_h - eff_h; self.vy = -abs(self.vy)

    # ── Render ────────────────────────────────────────────────────────────────
    def _render(self):
        img_w = max(10, int(BASE_W * abs(self.squish_x)))
        img_h = max(10, int(BASE_H * abs(self.squish_y)))

        # Only rescale when the size actually changed — avoids a full CPU pixbuf
        # scale operation every single frame (the old hottest path in profiling).
        if img_w != self._cached_img_w or img_h != self._cached_img_h:
            self._scaled_pixbuf = self.base_pixbuf.scale_simple(
                img_w, img_h, GdkPixbuf.InterpType.NEAREST)
            self._cached_img_w = img_w
            self._cached_img_h = img_h

        # If we're rotating, the window must be big enough to hold the full
        # diagonal so no corners get clipped.  We use the diagonal of the
        # *current* (possibly squished) image as the canvas size and centre
        # the image inside it.
        if self.angle != 0.0:
            diag = math.ceil(math.hypot(img_w, img_h))
            canvas_w = diag
            canvas_h = diag
        else:
            canvas_w = img_w
            canvas_h = img_h

        # Offset the window so the *visual centre* of the King stays where
        # self.x / self.y says it should be (top-left of the image rect).
        offset_x = (canvas_w - img_w) // 2
        offset_y = (canvas_h - img_h) // 2
        win_x = int(self.x) - offset_x
        win_y = int(self.y) - offset_y

        self.win.resize(canvas_w, canvas_h)
        self.win.move(win_x, win_y)
        self._cur_img_w  = img_w
        self._cur_img_h  = img_h
        self._cur_canvas_w = canvas_w
        self._cur_canvas_h = canvas_h
        self.win.queue_draw()

    def _on_draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)  # CLEAR
        cr.paint()
        cr.set_operator(2)  # OVER

        img_w    = self._cur_img_w
        img_h    = self._cur_img_h
        canvas_w = self._cur_canvas_w
        canvas_h = self._cur_canvas_h

        scaled = self._scaled_pixbuf

        # Centre of the canvas — this is where we anchor all transforms
        cx = canvas_w / 2
        cy = canvas_h / 2

        cr.save()

        if self.angle != 0.0:
            # Rotate around the canvas centre; image is drawn centred there too.
            # Apply horizontal flip (facing) before rotation so the King faces
            # the right direction even while spinning / wobbling.
            cr.translate(cx, cy)
            if self.facing == -1:
                cr.scale(-1, 1)
            cr.rotate(math.radians(self.angle))
            cr.translate(-img_w / 2, -img_h / 2)
        else:
            # No rotation — image sits at canvas offset so it's still centred
            offset_x = (canvas_w - img_w) // 2
            offset_y = (canvas_h - img_h) // 2
            cr.translate(offset_x, offset_y)
            if self.facing == -1:
                # Mirror horizontally around the image centre
                cr.translate(img_w, 0)
                cr.scale(-1, 1)

        Gdk.cairo_set_source_pixbuf(cr, scaled, 0, 0)
        cr.paint_with_alpha(self._die_alpha)
        cr.restore()
        return False


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import signal

    def _signal_quit(signum, frame):
        # Schedule the goodbye on the GTK main loop so it's safe to call GTK APIs
        GLib.idle_add(pet._quit)

    # pet isn't defined yet; we'll re-register after construction below

    if not VOICE_LINES:
        print("⚠  No voice MP3s found next to the script – running silent.")
    else:
        print(f"🎙  Loaded {len(VOICE_LINES)} voice line(s). Audio backend: {AUDIO}")

    pet = KingPet()
    signal.signal(signal.SIGINT,  _signal_quit)
    signal.signal(signal.SIGTERM, _signal_quit)
    Gtk.main()
