![image](https://github.com/user-attachments/assets/b15993a2-0aed-4332-9036-cb0ec12e07b5)


**Hold your Plex libraries hostage until users watch a specific movie.**

Someone on your server keeps ignoring your movie recommendations? Plextortion lets you lock their access to specific libraries until they watch a percentage of a movie you choose. They'll see a ransom message every time they try to watch something from the locked library.

---

## ✨ Features

- **Soft Lock** - Library stays visible, but playback is blocked with a custom message
- **Custom Messages** - Personalized lock and unlock messages with placeholders
- **Progress Tracking** - Automatically unlocks when they hit the watch threshold
- **Multiple Thresholds** - 10% quick taste to 100% full commitment
- **Live Preview** - See exactly what your victim will see before creating the ransom
- **Ransom History** - Track your extortion empire
- **Most Ransomed Movies** - Leaderboard of your go-to punishment films

---

## 🚀 Quick Start

### Windows

1. Download `Plextortion.exe` from [Releases](https://github.com/honkbadonk/plextortion/releases)
2. Double-click to run (Windows SmartScreen may warn - click "More info" → "Run anyway")
3. Browser opens automatically to setup wizard
4. Enter your Plex server URL and token
5. Configure webhooks in Plex (see below)
6. Start extorting!

### Linux / Mac

```bash
# Clone the repo
git clone https://github.com/honkbadonk/plextortion.git
cd plextortion

# Install dependencies
pip3 install -r requirements.txt

# Run
python3 plextortion_app.py
```

Open `http://localhost:5555` in your browser.

---

## 🔧 Plex Webhook Setup (Required)

Plextortion needs Plex webhooks to track viewing progress. **Webhooks require Plex Pass.**

1. Open Plex Web → Settings (wrench icon)
2. Click **Webhooks** in the left sidebar
3. Click **Add Webhook**
4. Enter: `http://YOUR_IP:5555/webhook`
5. Click **Save Changes**

Replace `YOUR_IP` with your computer's local IP address (shown in the Plextortion console on startup).

---

## 📖 How It Works

1. **Create a Ransom** - Pick a victim, a movie they must watch, and a library to lock
2. **They Try to Watch** - When they play something from the locked library, playback stops and your message appears
3. **They Watch the Prerequisite** - Progress is tracked via webhooks (updates on pause/stop)
4. **Threshold Met** - Library automatically unlocks, optional freedom message appears

---

## 💬 Custom Messages

Use placeholders to personalize your messages:

**Lock Message** (when they try to watch locked content):
- `{movie}` - The prerequisite movie title
- `{threshold}` - The percentage required
- `{library}` - The locked library name

Example: `"No {library} until you watch {threshold}% of {movie}. You know what you did."`

**Unlock Message** (when they complete the prerequisite):
- `{movie}` - The prerequisite movie title
- `{progress}` - The percentage they watched
- `{library}` - The unlocked library name

Example: `"Fine. You suffered through {movie}. {library} is yours again."`

---

## 📺 Device Compatibility

| Device | Lock Message | Unlock Message |
|--------|-------------|----------------|
| Apple TV | ✅ | ✅ |
| Fire Stick | ✅ | ❌ |
| Chrome Browser | ✅ | ❌ |
| Samsung TV | Testing | Testing |
| Google TV | Testing | Testing |

Lock messages work on all devices. Unlock messages depend on how the device handles session termination.

---

## ❓ FAQ

**Why does progress only update when they pause or stop?**
Plex webhooks only fire on play, pause, stop, and resume events - not during continuous playback. This is a Plex limitation, not Plextortion.

**Can I lock specific movies instead of whole libraries?**
Not yet. V1 locks entire libraries. Granular locking is planned for V2.

**Can the same user have multiple ransoms?**
Currently one active ransom per user. When it's completed, you can create another.

**What if the prerequisite movie is in the locked library?**
Plextortion prevents this - you can't lock the library that contains the prerequisite movie.

**Do I need Plex Pass?**
Yes, webhooks require Plex Pass.

---

## 🛠️ Tech Stack

- Python 3
- Flask
- PlexAPI
- SQLite

---

## 📁 Project Structure

```
plextortion/
├── plextortion_app.py   # Main application
├── database.py          # SQLite database functions
├── requirements.txt     # Python dependencies
└── plextortion.db       # Database (created on first run)
```

---

## 🗺️ Roadmap

### V1 (Current)
- ✅ Soft lock with ransom messages
- ✅ Custom lock/unlock messages
- ✅ Progress tracking
- ✅ Auto-unlock at threshold
- ✅ Web dashboard

### V2 (Planned)
- TV episode prerequisites
- Lock specific movies (not just libraries)
- Beer fund / payment bypass
- Docker support
- Multiple simultaneous ransoms per user

---

## 🤝 Contributing

Found a bug? Have a feature idea? Open an issue or submit a PR!

---

## 📜 License

MIT License - do whatever you want with it.

---

## 🍺 Support

If Plextortion made you laugh or improved your friendships through coercion, consider starring the repo!
https://github.com/sponsors/honkbadonk
Built with ❤️ and spite.
