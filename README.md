# 🌙 GoodNightBot — free overnight autopilot for *TBH: Task Bar Hero*

GoodNightBot plays the **visible game window** while you sleep: it sorts loot into the
stash, opens chests, collects mail, and locks anything valuable so nothing gets touched
by mistake. Optionally it can auto-synthesize low-grade gear in the Cube (off by default).

It's **free and open-source**. If it saves you time, you can tip — but you never have to.

## How it works (and why it's safe-by-design)

It plays the game **like a person would**: it looks at the screen (template matching + OCR)
and moves the **real mouse** with natural jitter, small overshoots and varied pauses.

- **No memory editing. No server tampering. No injected code.** Just screen reading + clicks.
- Reacts to the game's own **RECORDS log** (chest dropped, stage cleared, item obtained).
- **Never merges** rings, amulets, earrings, bracelets, or anything **Immortal grade and above**.
- If it can't read an item clearly, it **locks it** instead of risking it.

> ⚠️ Automation of any kind may violate the game's Terms of Service and carry risk to your
> account. Use at your own risk. This project edits nothing in the game or its servers — it
> only reads the screen and clicks — but you are responsible for how you use it.

## Install

**Option A — installer (easiest).** Download `GoodNightBot-Setup-*.exe` from
[Releases](../../releases) and run it. No admin rights needed. First launch downloads Python
and the OCR engine (needs internet, takes a couple of minutes); after that it's instant.

**Option B — from source (no exe, full transparency).**
```powershell
git clone https://github.com/iPipen666/GoodNightBot.git
cd GoodNightBot
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe control.py
```
You'll also need Tesseract OCR (the installer bundles it automatically; from source, install
Tesseract with the `rus`+`eng` language data).

## Run

1. Open the game so its window is **visible** (it must be the foreground window for clicks).
2. Launch the panel (`TBH_Autopilot.bat`, the desktop shortcut, or `pythonw control.py`).
3. Press **START**.
4. **Stop anytime with F12**, the STOP button, or by slamming the cursor into the top-left corner.

## What it does by default

- ✅ Sorts loot into the stash · opens chests · collects mail · locks valuables
- ⛔ Does **not** synthesize anything — the Cube stays closed until you enable *Auto-synthesis*
- 🔁 Updates via **GitHub Releases** — press *check for updates* in the panel

## Updates

The client checks this repo's signed release manifest and can update itself. You can also just
`git pull` (source) or grab the newest installer from [Releases](../../releases).

## Support

The bot is free. If you want to say thanks: there's a donate option in the companion Telegram
bot (Telegram Stars for international users) and a ruble option on the site. Joining the
[Telegram community](https://t.me/taskbar_hero) helps too.

## License

[MIT](LICENSE) — do what you want, no warranty.
