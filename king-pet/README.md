# 👑 King Harkinian Desktop Pet

> *"Mah boi, this desktop pet is what all true Linux users strive for!"*

---

<img src="./king-pet/King-Harkinian-CD-i.png" alt="King Harkinian" width="180" />

---

A gloriously low-effort GTK desktop pet that plops the King himself right onto your Linux desktop. He roams around, squishes, spins, bounces, shakes, and randomly yells his iconic CD-i voice lines at you when you least expect it. Just like real royalty. 👑

---

## 🚨 REQUIREMENTS

Before you dare run this, make sure you have the necessary garbage installed:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 gir1.2-appindicator3-0.1
```

**Optional (but strongly recommended for better audio):**

```bash
pip install pygame
```

If you don't have `pygame`, the script falls back to `aplay` which ships with `alsa-utils` and is probably already on your machine. If you have neither, the King will roam your desktop in absolute silence like a cursed ghost. Your choice. 🤷🏻‍♂️

---

## 📁 FILE STRUCTURE

Make sure all of these are sitting in the **same directory** together, or the King won't show up and you'll have only yourself to blame motherfucker:

```
king_harkinian_pet.py
King-Harkinian-CD-i.png
Dinner.mp3
Mah-Boi.mp3
King-Harkinian-Laugh.mp3
This-Peace-Is-What-All-True-Warriors-Strive-For.mp3
scrub-all-the-floors-in-hyrule.mp3
king-oh.mp3
```

---

## 🎮️ HOW TO RUN

```bash
python3 king_harkinian_pet.py
```

That's it. The King appears. You're welcome, bitch.

---

## 🕹️ CONTROLS

| Action | What it does |
|---|---|
| **Left-click** the King | Forces him to speak immediately. Rude, but effective. |
| **Right-click** the King | Kills him. He'll have something to say about it. |
| **Tray icon** (right-click) | Toggle visibility, make him speak, or quit |

---

## 👑 ANIMATIONS

The King is a man of many talents. Here's what he gets up to:

* **Walk** — A dignified stroll across your desktop, facing whichever way he's actually going like a normal person
* **Bounce** — Squishes on impact like the royalty he is
* **Spin** — Absolutely unhinged 360° rotation
* **Squish** — Chaotic stretching in all directions
* **Shake** — Full-body trembling, probably excited about dinner
* **Zoom** — Grows and shrinks like he's having a moment

He switches between these randomly. Watch him become a gaaaawd!

---

## 🎙️ VOICE LINES

Every ~5 seconds, there's a **55% chance** the King decides to open his mouth. The available clips are:

* *"Dinner!"*
* *"Mah boi!"*
* His iconic laugh
* *"This peace is what all true warriors strive for!"*
* *"Scrub all the floors in Hyrule!"*

Voice lines will not overlap. The King has dignity. Barely, but still.

And when you try to kill him? He gets the last word. `king-oh.mp3` plays in full before the program exits, whether you right-click him, use the tray menu, or hit `Ctrl+C` in the terminal. You can't silence royalty. 👑

---

## 🚀 AUTOSTART (Optional)

Want the King to bless your desktop every single time you log in? Of course you do.

1. Edit `king-harkinian-autostart.desktop` and replace `YOUR_USERNAME` with your actual username:

```ini
Exec=python3 /home/YOUR_USERNAME/king_harkinian_pet.py
```

2. Drop it in your autostart folder:

```bash
cp king-harkinian-autostart.desktop ~/.config/autostart/
```

The King will now report for duty every login. You asked for this, idiot. 👍🏻

---

## 🖥️ ADD A DESKTOP SHORTCUT (Optional)

If you want to launch the King from your application menu or desktop:

```bash
cp king-harkinian-pet.desktop ~/Desktop/
chmod +x ~/Desktop/king-harkinian-pet.desktop
```

Update the `Exec` path inside the file to match wherever you actually put the script.

---

## 💬 Q & A

> **Q: Does this work on Windows or Mac?**
> **A:** No. GTK desktop pets are a Linux thing. Get a real operating system. 😁

> **Q: The King isn't making any sounds!**
> **A:** Install `pygame` or make sure `aplay` is on your system. Also check that the MP3 files are in the same folder as the script. The King cannot speak if you don't give him his voice lines.

> **Q: Can I add my own voice lines?**
> **A:** Yes! Drop any MP3 into the script folder and add the filename to the `VOICE_LINES` list in `king_harkinian_pet.py`. The King will add it to his repertoire immediately. 🎙️

> **Q: Why does he face left sometimes?**
> **A:** Because he's walking left, genius. He mirrors automatically depending on which direction he's moving. The spin animation is exempt because flipping during a 360° looks stupid, and the King has standards.

> **Q: I get a bunch of pygame warnings in the terminal!**
> **A:** You don't anymore. The script suppresses pygame's startup spam automatically. You're welcome.

> **Q: This is stupid.**
> **A:** Correct. 🙃

---

## 🛠️ TESTED ON

* **Linux Mint 22 Cinnamon** — works perfectly, obviously
* Probably works on Ubuntu, Debian, and anything else GTK-friendly

---

(Note: This download includes a free desktop background made by super fabulous yours truly, That One Dutch Guy!)

---

> *"Enough! My ship sails in the morning!"* 👑🍷
