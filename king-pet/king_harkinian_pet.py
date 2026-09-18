#!/usr/bin/env python3
"""
King Harkinian Desktop Pet
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

GOODBYE_CLIP = os.path.join(SCRIPT_DIR, "king-oh.mp3")
EATING_SFX   = os.path.join(SCRIPT_DIR, "eating.mp3")
BURP_SFX     = os.path.join(SCRIPT_DIR, "burp.mp3")

DINNER_MACHINE_PNG = os.path.join(SCRIPT_DIR, "dinner-machine.png")
FOOD_IMAGES = [
    os.path.join(SCRIPT_DIR, "pizza.png"),
    os.path.join(SCRIPT_DIR, "panini.png"),
    os.path.join(SCRIPT_DIR, "happy-meal.png"),
    os.path.join(SCRIPT_DIR, "chicken-bucket.png"),
]
# Only keep food images that actually exist
FOOD_IMAGES = [f for f in FOOD_IMAGES if os.path.isfile(f)]

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
        self.win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.win.connect("button-press-event", self._on_click)

        self.image_widget = Gtk.DrawingArea()
        self.win.add(self.image_widget)
        self.image_widget.connect("draw", self._on_draw)

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
        self._die_alpha = 1.0

        # ── Audio state ───────────────────────────────────────────────────────
        self._audio_playing = False   # guard: don't overlap clips
        self._voice_counter = VOICE_CHECK_EVERY  # count down to first check

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

        self._pick_new_behaviour()
        self._build_tray()
        self._build_dinner_machine()
        self._build_food_window()

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
        """Fire-and-forget audio in a daemon thread so GTK isn't blocked."""
        if self._audio_playing or not path:
            return
        self._audio_playing = True

        def _worker():
            try:
                if AUDIO == "pygame":
                    sound = pygame.mixer.Sound(path)
                    ch = sound.play()
                    while ch.get_busy():
                        import time; time.sleep(0.05)
                else:
                    subprocess.run(["aplay", path],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
            finally:
                self._audio_playing = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _start_goodbye(self):
        """Fire king-oh.mp3 immediately at the start of the death animation."""
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

        self.food_win.resize(FOOD_DISPLAY_SIZE, FOOD_DISPLAY_SIZE)
        # Don't show yet — shown when dragging starts

    def _draw_food_window(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)
        cr.paint()
        cr.set_operator(2)
        if self._food_pixbuf:
            # Wobble animation while being eaten
            if self._eating and self._eat_phase == "eat":
                t = self._eat_food_devour
                sx = 1.0 + 0.18 * math.sin(t * 0.8)
                sy = 1.0 - 0.18 * math.sin(t * 0.8)
                ang = 15 * math.sin(t * 0.6)
                cx = FOOD_DISPLAY_SIZE / 2
                cy = FOOD_DISPLAY_SIZE / 2
                cr.translate(cx, cy)
                cr.rotate(math.radians(ang))
                cr.scale(sx, sy)
                cr.translate(-cx, -cy)
            Gdk.cairo_set_source_pixbuf(cr, self._food_pixbuf, 0, 0)
            cr.paint_with_alpha(self._food_alpha if hasattr(self, "_food_alpha") else 1.0)
        return False

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
        """king-oh.mp3, King flips toward food, runs to it, eats, burps."""
        self._eating = True
        self._eat_phase = "run"
        self._eat_tick  = 0
        self._eat_food_devour = 0
        self._food_alpha = 1.0

        # Save current behaviour
        self._saved_anim = self.anim
        self._saved_vx   = self.vx
        self._saved_vy   = self.vy

        # Play king-oh (non-blocking, doesn't block other audio)
        self._play_sfx_nonblocking(GOODBYE_CLIP)

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
                self.squish_x = 1.0
                self.squish_y = 1.0
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
                # Funny run animation — rapid stomp squish
                run_t = t - 15
                self.squish_x = 1.0 + 0.3 * math.sin(run_t * 0.7)
                self.squish_y = 1.0 - 0.3 * math.sin(run_t * 0.7)
                self.angle    = 10 * math.sin(run_t * 0.9)
            else:
                # Arrived at food
                self.x = self._eat_target_x
                self.y = self._eat_target_y
                self.squish_x = 1.0
                self.squish_y = 1.0
                self.angle    = 0.0
                self._eat_phase = "eat"
                self._eat_tick  = 0
                self._eat_food_devour = 0
                # Start eating sound (blocking; triggers burp on finish)
                self._play_sfx_blocking(EATING_SFX, self._on_eating_done)

        elif self._eat_phase == "eat":
            self._eat_food_devour += 1
            # King chomping animation — rapid open-close squish
            self.squish_x = 1.0 + 0.25 * math.sin(t * 1.1)
            self.squish_y = 1.0 - 0.25 * math.sin(t * 1.1)
            self.angle    = 5 * math.sin(t * 0.8)
            self.food_win.queue_draw()

        elif self._eat_phase == "burp":
            # King shudders with satisfaction
            if t < 30:
                self.squish_x = 1.0 + 0.4 * math.sin(t * 0.5)
                self.squish_y = 1.0 - 0.2 * math.sin(t * 0.5)
                self.angle    = 15 * math.sin(t * 0.4)
            else:
                # All done — restore normal behaviour
                self.squish_x   = 1.0
                self.squish_y   = 1.0
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
        """Callback when eating.mp3 finishes — hide food, play burp."""
        self.food_win.hide()
        self._eat_phase = "eat_done"  # signal to switch phase after burp starts
        self._play_sfx_blocking(BURP_SFX, self._on_burp_done)
        self._eat_phase = "burp"
        self._eat_tick  = 0
        return False  # GLib.idle_add must return False

    def _on_burp_done(self):
        """Called when burp finishes; _tick_eat_sequence handles the timer wind-down."""
        return False

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

        if self._eating:
            self._tick_eat_sequence()
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
        else:
            self.x += self.vx
            self.y += self.vy

        # Track facing -- some anims lock or ignore facing
        if self.anim not in ("shake", "vibrate", "stomp", "moonwalk",
                             "flatline", "creep", "glitch") and self.vx != 0:
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

        img_w    = self._cur_img_w    if hasattr(self, "_cur_img_w")    else BASE_W
        img_h    = self._cur_img_h    if hasattr(self, "_cur_img_h")    else BASE_H
        canvas_w = self._cur_canvas_w if hasattr(self, "_cur_canvas_w") else BASE_W
        canvas_h = self._cur_canvas_h if hasattr(self, "_cur_canvas_h") else BASE_H

        scaled = self.base_pixbuf.scale_simple(
            img_w, img_h, GdkPixbuf.InterpType.NEAREST)

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
