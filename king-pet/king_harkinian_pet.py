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
]
# Keep only files that actually exist next to the script
VOICE_LINES = [os.path.join(SCRIPT_DIR, f) for f in VOICE_LINES
               if os.path.isfile(os.path.join(SCRIPT_DIR, f))]

GOODBYE_CLIP = os.path.join(SCRIPT_DIR, "king-oh.mp3")

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

        # -- Death animation state
        self._dying     = False
        self._die_tick  = 0
        self._die_alpha = 1.0

        # ── Audio state ───────────────────────────────────────────────────────
        self._audio_playing = False   # guard: don't overlap clips
        self._voice_counter = VOICE_CHECK_EVERY  # count down to first check

        self._pick_new_behaviour()
        self._build_tray()

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
    ]

    def _pick_new_behaviour(self):
        name, duration = random.choice(self.BEHAVIOURS)
        self.anim       = name
        self.anim_timer = duration
        self.angle      = 0.0
        self.bounce_phase = 0.0
        if random.random() < 0.3: self.vx *= -1
        if random.random() < 0.3: self.vy *= -1

    # ── Main tick ─────────────────────────────────────────────────────────────
    def _tick(self):
        if self._dying:
            self._tick_death()
            return True

        self.tick += 1
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
        else:
            self.x += self.vx
            self.y += self.vy

        # Track facing -- moonwalk/shake/vibrate/stomp don't update it
        if self.anim not in ("shake", "vibrate", "stomp", "moonwalk") and self.vx != 0:
            self.facing = 1 if self.vx > 0 else -1

        eff_w = BASE_W * abs(self.squish_x)
        eff_h = BASE_H * abs(self.squish_y)
        if self.x < 0:                    self.x = 0;                   self.vx =  abs(self.vx)
        if self.x + eff_w > self.desk_w:  self.x = self.desk_w - eff_w; self.vx = -abs(self.vx)
        if self.y < 0:                    self.y = 0;                   self.vy =  abs(self.vy)
        if self.y + eff_h > self.desk_h:  self.y = self.desk_h - eff_h; self.vy = -abs(self.vy)

    # ── Render ────────────────────────────────────────────────────────────────
    def _render(self):
        new_w = max(10, int(BASE_W * abs(self.squish_x)))
        new_h = max(10, int(BASE_H * abs(self.squish_y)))
        self.win.resize(new_w, new_h)
        self.win.move(int(self.x), int(self.y))
        self._cur_w = new_w
        self._cur_h = new_h
        self.win.queue_draw()

    def _on_draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)  # CLEAR
        cr.paint()
        cr.set_operator(2)  # OVER

        w = self._cur_w if hasattr(self, "_cur_w") else BASE_W
        h = self._cur_h if hasattr(self, "_cur_h") else BASE_H

        scaled = self.base_pixbuf.scale_simple(
            w, h, GdkPixbuf.InterpType.NEAREST)

        cr.save()

        # Spin handles its own rotation; for everything else apply facing flip
        if self.angle != 0.0:
            cr.translate(w / 2, h / 2)
            cr.rotate(math.radians(self.angle))
            cr.translate(-w / 2, -h / 2)
        elif self.facing == -1:
            # Mirror horizontally: flip around the vertical centre line
            cr.translate(w, 0)
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
