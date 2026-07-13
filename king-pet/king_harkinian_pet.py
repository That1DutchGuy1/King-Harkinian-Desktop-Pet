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

        # ── Audio state ───────────────────────────────────────────────────────
        self._audio_playing = False   # guard: don't overlap clips
        self._voice_counter = VOICE_CHECK_EVERY  # count down to first check

        self._pick_new_behaviour()
        self._build_tray()

        self.win.resize(BASE_W, BASE_H)
        self.win.move(int(self.x), int(self.y))
        self.win.show_all()

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
                               ("Quit",   lambda *_: Gtk.main_quit())]:
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
                           ("Quit",   lambda *_: Gtk.main_quit())]:
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
            Gtk.main_quit()

    # ── Behaviour scheduler ───────────────────────────────────────────────────
    BEHAVIOURS = [
        ("walk",   120),
        ("bounce",  90),
        ("spin",    60),
        ("squish",  80),
        ("shake",   50),
        ("zoom",    70),
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

    def _move(self):
        if self.anim == "spin":
            self.x += self.vx * 0.3
            self.y += self.vy * 0.3
        elif self.anim == "shake":
            self.x += 6 * math.sin(self.tick * 0.8)
        else:
            self.x += self.vx
            self.y += self.vy

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

        if self.angle != 0.0:
            cr.translate(w / 2, h / 2)
            cr.rotate(math.radians(self.angle))
            cr.translate(-w / 2, -h / 2)

        Gdk.cairo_set_source_pixbuf(cr, scaled, 0, 0)
        cr.paint()
        return False


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if not VOICE_LINES:
        print("⚠  No voice MP3s found next to the script – running silent.")
    else:
        print(f"🎙  Loaded {len(VOICE_LINES)} voice line(s). Audio backend: {AUDIO}")

    pet = KingPet()
    Gtk.main()
