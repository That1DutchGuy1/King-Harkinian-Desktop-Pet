# 👑 King Harkinian Desktop Pet

> *"Mah boi, this desktop pet is what all true Linux users strive for!"*

---

<img src="./king-pet/King-Harkinian-CD-i.png" alt="King Harkinian" width="180" />

---

A gloriously low-effort GTK desktop pet that plops the King himself right onto your Linux desktop. He roams around, squishes, spins, bounces, shakes, and randomly yells his iconic CD-i voice lines at you when you least expect it. Just like real royalty. 👑
You also have to feed him with the food dispensed from the iconic Dinner Machine! Bro, if you haven't watched the iconic <a href="https://www.youtube.com/watch?v=5k6lu1ynsBk" target="_blank">"The King gets a Dinner Machine"</a> by Nin10Guy, then go fucking watch it, you uncultured swine!

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
duke-onkled-under-attack.mp3
enough.mp3
im-going-to-gamelon.mp3
hmm.mp3
piece-of-shit.mp3
triforce-of-courage.mp3
ship-sails.mp3
wonder-whats-for-dinner.mp3
you-saved-me.mp3
king-oh.mp3
eating.mp3
burp.mp3
dinner-machine.png
pizza.png
panini.png
happy-meal.png
chicken-bucket.png
```

The food images and dinner machine are optional — if they're not there, the Dinner Machine simply won't appear. The King will still roam your desktop like a normal unstable monarch.

The script will silently skip any MP3s it can't find, so you won't get an error if you're missing some. You'll just get a less unhinged experience, which is your loss honestly.

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
| **Left-click** the Dinner Machine | Picks a random food and sticks it to your cursor. You are now responsible for feeding the King. |
| **Left-click** to place food | Drops the food on the desktop. The King will handle the rest. He always handles dinner. |

---

## 👑 ANIMATIONS

The King is a man of many talents. Here's what he gets up to:

* **Walk** — A dignified stroll across your desktop, facing whichever way he's actually going like a normal person
* **Bounce** — Squishes on impact like the royalty he is
* **Spin** — Absolutely unhinged 360° rotation
* **Squish** — Chaotic stretching in all directions
* **Shake** — Full-body trembling, probably excited about dinner
* **Zoom** — Grows and shrinks like he's having a moment
* **Tilt** — Slow, seasick rocking back and forth. He's on a ship. His ship sails in the morning. You know this.
* **Stomp** — Rapid vertical pounding like he found out Link failed to save Zelda *again*
* **Panic** — Frantic zigzag sprinting at double speed. Something has gone very wrong in Hyrule.
* **Nod** — Enthusiastic squash-and-stretch bobbing. He agrees with whatever you're doing. He doesn't, but he's being polite.
* **Moonwalk** — Slides backwards while facing forwards. The King has swag. Undeniable, inexplicable swag.
* **Vibrate** — Extremely fast tiny jitter, like he touched an electric fence or read the royal tax return
* **Warp** — Bad VHS tape energy. Corrupted video signal. Probably from a scratched CD-i disc, shocking.
* **Chalice** — Looms directly at you, growing larger, personally shoving the chalice in your face. You cannot escape the chalice.
* **Flatline** — Pancakes completely flat to the floor and creeps around like a condemned royal trying to escape under a door. Haunting.
* **Dizzy** — Figure-8 wobble like he got smacked with a frying pan. He has been smacked with a frying pan.
* **Creep** — Freezes completely still for a couple seconds, then SNAPS to a new location with no warning whatsoever. Low-budget horror movie. Do not look away.
* **Glitch** — Corrupted CD-i disc. Random scale and angle snaps with no interpolation. He is broken. We are all a little broken.

He switches between these randomly. Eighteen possible states of unhinged royalty. Watch him become a gaaaawd!

---

## 🎙️ VOICE LINES

Every ~5 seconds, there's a **55% chance** the King decides to open his mouth. The available clips are:

* *"Dinner!"* — he's hungry!
* *"Mah boi!"* — you're his boi now, motherfucker.
* *"OAHAHAHAHAHAHAHAAA!!"* — he's probably laughing at you.
* *"This peace is what all true warriors strive for!"* — he thinks that... but Link doesn't.
* *"Scrub all the floors in Hyrule!"* — used to be Duke Onkled's punishment. Now it's yours.
* *"Duke Onkled is under attack by the evil forces!"* — urgent news delivery, zero context provided
* *"Enough!"* — he's had it. With what? Everything. All of it.
* *"I'm going to Gamelon!"* — he is going. He has decided. There is nothing you can do.
* *"Hmm."* — profound. Weighty. He is thinking about dinner.
* *"Piece of shit!"* — yeah, he's talking about you, dickhead.
* *"The Triforce of Courage!"* — he says this with the energy of a man who has never held the Triforce of Courage
* *"My ship sails in the morning!"* — it does. It always does. He says this at 3pm.
* *"I wonder what's for dinner?"* — an eternal question. A philosophical inquiry. He already knows. It's dinner.
* *"You saved me!"* — said with genuine surprise, as if he didn't hire you specifically for this

Voice lines will not overlap. The King has dignity. Barely, but still. The script only loads clips that are actually present on disk, so it won't crash just because you forgot to download `piece-of-shit.mp3`. Good for you.

And when you try to kill him? He gets the last word. `king-oh.mp3` plays in full before the program exits, whether you right-click him, use the tray menu, or hit `Ctrl+C` in the terminal. You can't silence royalty. 👑

---

## 🍕 THE DINNER MACHINE

The King is hungry. He is always hungry. That is his entire personality and you will respect it.

In the bottom-right corner of your screen, you'll find the **Dinner Machine** — a mysterious appliance of unknown origin that dispenses food directly onto your desktop. Left-click it and a random meal will attach itself to your cursor like a cursed gift. You are now the delivery guy. Congratulations on your new job.

**Left-click anywhere on the desktop** to drop the food. Don't place it on top of the King — he's not ready yet and he will simply refuse, because royalty has standards about plating.

Once the food is placed, the following chain of events will occur whether you want them to or not:

1. **The King notices.** He plays a sound clip. He is very pleased.
2. **He spins on the spot** to face the food — a full 360° rotation of pure regal anticipation.
3. **He runs toward it** at approximately the speed of a man who has been told it's dinnertime. He wobbles. He stomps. He leans. It's undignified and perfect.
4. **He eats it.** Chomping squish animation, food wobbling in protest, full eating sound effects. The meal doesn't stand a chance.
5. **He burps.** Loudly. With his whole body. The King shudders with satisfaction.
6. **He resumes his normal behaviour**, presumably thinking about his next meal.

The food choices are: pizza, panini, happy meal, and a bucket of chicken. The machine picks randomly. You don't get a say. You never get a say. This is his kitchen now.

**The King always faces the food correctly.** If the food is to his left, he mirrors to face left. If it's to his right, he faces right. He has spatial awareness. More than you, probably. 👑

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

## 🐛 FIXES & CHANGES

### What's new in this update, you impatient person:

**9 new voice lines** — The King has more to say now. He always had more to say. You just weren't listening.

**6 new animations** — tilt, stomp, panic, nod, moonwalk, vibrate, warp, chalice, flatline, dizzy, creep, glitch. That's twelve. Twelve. The man contains multitudes.

**The Dinner Machine** — A mysterious food-dispensing appliance now lives in the bottom-right of your screen. Click it, get food, place food, watch the King sprint across your entire desktop to devour it and then burp at you. Full eat sequence with run animation, chomping squish, food wobble, eating SFX, and a burp that shakes his whole body. He then resumes roaming as if nothing happened. Because for him, nothing did. Dinner is not an event. Dinner is a lifestyle.

**Facing fix for the eat sequence** — The King now correctly mirrors to face the food during the entire run animation, including while he's mid-wobble and mid-squish. Previously he'd always face right while running regardless of where the food actually was, which was embarrassing for everyone involved. Fixed. His spatial awareness is now fully restored. 👑

**Clipping fix** — Rotating animations used to clip the corners of the King's head off because the window wasn't big enough to hold the full diagonal of a rotated image. This was unacceptable. It has been fixed. The script now calculates the diagonal of the current (possibly squished) frame and sizes the canvas accordingly, then offsets the window position so the King appears to stay exactly where he should be. His crown is intact. As it should be. 👑

---

## 💬 Q & A

> **Q: Does this work on Windows or Mac?**
> **A:** No. GTK desktop pets are a Linux thing. Get a real operating system. 😁

> **Q: The King isn't making any sounds!**
> **A:** Install `pygame` or make sure `aplay` is on your system. Also check that the MP3 files are in the same folder as the script. The King cannot speak if you don't give him his voice lines.

> **Q: Can I add my own voice lines?**
> **A:** Yes! Drop any MP3 into the script folder and add the filename to the `VOICE_LINES` list in `king_harkinian_pet.py`. The King will add it to his repertoire immediately. 🎙️

> **Q: Why does he face left sometimes?**
> **A:** Because he's walking left, genius. He mirrors automatically depending on which direction he's moving. The spin, shake, vibrate, stomp, moonwalk, flatline, creep, and glitch animations are exempt from mirroring because they either don't travel, look stupid flipped, or are already chaotic enough that nobody's checking. The King has standards. Variable standards, but standards.

> **Q: Why is he moonwalking in the wrong direction??**
> **A:** He's not. That IS the moonwalk. He faces one way and slides the other. That's the whole bit. Michael Jackson invented it, the King borrowed it, and now it's on your desktop. You're welcome.

> **Q: He just froze completely still and it's been like 5 seconds, is he broken?**
> **A:** That's the creep animation. He's about to snap to a new location with zero warning. Stop staring at him. That's what he wants.

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
