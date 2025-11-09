🌙 HoYoLab → Slack Daily Notes Bot

A fully automated bot that fetches your Genshin Impact Daily Notes and sends clean, concise status reports directly into Slack. Built for players who want resin alerts, expedition updates, and teapot coin tracking — without opening HoYoLab.

⸻

✅ Features

🔄 Automated Daily Notes (Every 5 Hours)

The bot pulls your latest Genshin Impact account status and posts it to Slack:
	•	Resin (current, max, ETA to full)
	•	Expedition status (completed vs. total)
	•	Teapot coin capacity + time until cap
	•	Weekly boss discount timer
	•	Commission progress
	•	Abyss reset timer
	•	Server time + UID displayed clearly

All outputs are formatted using Slack blocks for clean readability.

⸻

🔔 Smart Resin Alerts

You get instant alerts when Resin crosses key thresholds:
	•	120
	•	160 (or full)

Messages are formatted and sent as real-time Slack notifications.

⸻

🚫 No More Errors

This bot removes unstable features and avoids API problems:
	•	✅ No Parametric Transformer (causes API issues)
	•	✅ No Character Summary (genshin.py error-prone)
	•	✅ No deprecated check-in functions
	•	✅ Timezones handled correctly
	•	✅ Client errors auto-suppressed

Everything runs clean, silently, and stable.

⸻

🕒 Timezone-Safe Resin ETA

The bot converts recovery timestamps properly and shows:
	•	“ready to full”
	•	or “in ~32h 4m to cap”

No offset errors.

⸻

🔧 Built for Docker

Simple to deploy:

docker build -t hoyo-bot .
docker run -d --env-file .env hoyo-bot

Runs in a self-contained loop every 5 hours.

⸻

🧩 Configurable via Environment Variables

Your .env controls everything:

HOYO_TOKEN=xxx
GENSHIN_UID=xxxxxxxxx
GENSHIN_SERVER=NA
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxxx


⸻

🎯 Why This Bot Exists

Because opening HoYoLab every day is annoying.
Slack is instant.
This bot keeps you updated automatically so you never cap resin again.

⸻

🚀 Future Upgrades (Planned)
	•	Multi-account support (Genshin + Star Rail)
	•	Custom resin alert thresholds
	•	Discord version
	•	Web dashboard endpoint

⸻
