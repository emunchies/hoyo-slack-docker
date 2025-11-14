import os
import json
import time
import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
import genshin
import warnings

# ──────────────────────────────────────────────────────────────────────────────
# Suppress noisy character/extdb warnings from genshin.py
# ──────────────────────────────────────────────────────────────────────────────
warnings.filterwarnings(
    "ignore",
    message=r"Failed to update characters: .*",
    category=UserWarning,
    module="genshin.client.components.chronicle.base",
)

logging.getLogger("genshin.utility.extdb").setLevel(logging.CRITICAL)
logging.getLogger("genshin.client.components.chronicle.base").setLevel(logging.CRITICAL)

# Load .env if present (Docker env vars still work fine even if this file is missing)
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# ENV / CONFIG
# ──────────────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
LTOKEN_V2 = os.getenv("LTOKEN_V2")
LTUID_V2  = os.getenv("LTUID_V2")
GENSHIN_UID = int(os.getenv("GENSHIN_UID", "0"))

# run cadence (hours) – default 1 hour
SCHEDULE_HOURS = int(os.getenv("SCHEDULE_HOURS", "1"))
POST_ON_START = os.getenv("POST_ON_START", "true").lower() in ("1", "true", "yes")

# resin alert thresholds (once per day per threshold)
RESIN_ALERTS = [
    int(x) for x in os.getenv("RESIN_ALERT_THRESHOLDS", "120,160").split(",")
    if x.strip()
]

# simple state persistence
DATA_DIR = os.getenv("DATA_DIR", "/data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

# Abyss reset is tied to NA server (04:00 America/New_York on 1st & 16th)
NA_TZ = ZoneInfo("America/New_York")

# ──────────────────────────────────────────────────────────────────────────────
# UTIL / STATE / SLACK
# ──────────────────────────────────────────────────────────────────────────────
def _ensure_dir(p: str):
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        pass

def load_state():
    _ensure_dir(DATA_DIR)
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    _ensure_dir(DATA_DIR)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)

def today_na_str():
    return dt.datetime.now(NA_TZ).strftime("%Y-%m-%d")

def post_slack_text(text: str):
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError("Missing SLACK_WEBHOOK_URL")
    r = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=20)
    r.raise_for_status()

def post_slack_blocks(blocks: list, fallback: str = "Update"):
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError("Missing SLACK_WEBHOOK_URL")
    payload = {"blocks": blocks, "text": fallback}
    r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=20)
    r.raise_for_status()

# ──────────────────────────────────────────────────────────────────────────────
# TIME HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def convert_recovery(value):
    """
    Normalize HoYoLab recovery fields to seconds remaining.
    Accepts datetime (aware/naive, ready-at), dict {Day,Hour,Minute,Second},
    numeric seconds, or None.
    """
    if value is None:
        return 0

    if isinstance(value, dt.datetime):
        now = dt.datetime.now(dt.timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return max(int((value - now).total_seconds()), 0)

    if isinstance(value, dict):
        d = int(value.get("Day", 0))
        h = int(value.get("Hour", 0))
        m = int(value.get("Minute", 0))
        s = int(value.get("Second", 0))
        return max(d * 86400 + h * 3600 + m * 60 + s, 0)

    try:
        return max(int(value), 0)
    except Exception:
        return 0

def eta_str(seconds):
    seconds = convert_recovery(seconds)
    if seconds <= 0:
        return "ready"
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    return "in ~" + ("{}h ".format(h) if h else "") + ("{}m".format(m) if m else "").strip()

def next_abyss_reset_na():
    """Abyss resets on the 1st & 16th at 04:00 NA server time."""
    now = dt.datetime.now(NA_TZ)
    y, m, d = now.year, now.month, now.day

    if d < 1 or (d == 1 and now.hour < 4):
        target = dt.datetime(y, m, 1, 4, 0, tzinfo=NA_TZ)
    elif d < 16 or (d == 16 and now.hour < 4):
        target = dt.datetime(y, m, 16, 4, 0, tzinfo=NA_TZ)
    else:
        if m == 12:
            y2, m2 = y + 1, 1
        else:
            y2, m2 = y, m + 1
        target = dt.datetime(y2, m2, 1, 4, 0, tzinfo=NA_TZ)

    return target, target - now

# ──────────────────────────────────────────────────────────────────────────────
# FEATURES
# ──────────────────────────────────────────────────────────────────────────────
def maybe_fire_resin_alerts(resin_now: int, state):
    day_key = today_na_str()
    state.setdefault("resin_alerts", {})
    state["resin_alerts"].setdefault(day_key, {})
    fired_any = False

    for thr in RESIN_ALERTS:
        k = str(thr)
        already = state["resin_alerts"][day_key].get(k, False)
        if not already and resin_now >= thr:
            post_slack_text(
                f"🔔 *Resin Alert*: You’ve reached **{thr}** resin (current: {resin_now})."
            )
            state["resin_alerts"][day_key][k] = True
            fired_any = True

    if fired_any:
        save_state(state)

# ──────────────────────────────────────────────────────────────────────────────
# MAIN CYCLE
# ──────────────────────────────────────────────────────────────────────────────
async def run_once():
    state = load_state()
    client = genshin.Client(cookies={"ltoken_v2": LTOKEN_V2, "ltuid_v2": LTUID_V2})

    # Daily Notes
    notes = await client.get_genshin_notes(GENSHIN_UID)

    # Resin
    resin_now = notes.current_resin
    resin_max = notes.max_resin
    resin_eta = convert_recovery(notes.resin_recovery_time)

    # Alerts
    maybe_fire_resin_alerts(resin_now, state)

    # Commissions
    commissions_done = getattr(notes, "finished_commissions", 0) or 0
    commissions_total = getattr(notes, "max_commissions", 4) or 4
    commissions_claimed = bool(getattr(notes, "claimed_commission_reward", False))

    # Expeditions
    expeditions = notes.expeditions or []
    exp_finished = sum(1 for e in expeditions if getattr(e, "finished", False))
    exp_total = len(expeditions)

    # Teapot
    realm_currency = getattr(notes, "current_realm_currency", None)
    realm_max = getattr(notes, "max_realm_currency", None)
    realm_eta = convert_recovery(getattr(notes, "realm_currency_recovery_time", None))

    # Abyss
    abyss_target, abyss_delta = next_abyss_reset_na()
    abyss_eta = eta_str(int(abyss_delta.total_seconds())).replace("in ~", "")

    # Timestamp (UTC)
    now_utc = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Slack Blocks (no check-in, no transformer, no character summary)
    fields = [
        {
            "type": "mrkdwn",
            "text": f"*🔋 Resin*\n`{resin_now}/{resin_max}` — {eta_str(resin_eta)} to full",
        },
        {
            "type": "mrkdwn",
            "text": f"*🗺 Expeditions*\n`{exp_finished}/{exp_total}` finished",
        },
        {
            "type": "mrkdwn",
            "text": (
                f"*🫖 Teapot Coins*\n`{realm_currency}/{realm_max}` — {eta_str(realm_eta)} to cap"
                if realm_currency is not None and realm_max is not None
                else "*🫖 Teapot Coins*\n`N/A`"
            ),
        },
        {
            "type": "mrkdwn",
            "text": f"*🌙 Abyss Reset (NA)*\n`{abyss_target.strftime('%Y-%m-%d %H:%M %Z')}` — in {abyss_eta}",
        },
        {
            "type": "mrkdwn",
            "text": f"*📝 Commissions*\n`{commissions_done}/{commissions_total}`",
        },
        {
            "type": "mrkdwn",
            "text": f"*🎁 Commission Reward*\n{'✅ claimed' if commissions_claimed else '❌ not claimed'}",
        },
    ]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Genshin Daily Notes", "emoji": True},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*Time:* {now_utc}"},
                {"type": "mrkdwn", "text": "*Server:* NA"},
                {"type": "mrkdwn", "text": f"*UID:* `{GENSHIN_UID}`"},
            ],
        },
        {"type": "divider"},
        {"type": "section", "fields": fields},
    ]

    post_slack_blocks(blocks, fallback="Genshin Daily Notes")

def main_loop():
    if POST_ON_START:
        asyncio.run(run_once())

    while True:
        try:
            time.sleep(max(1, SCHEDULE_HOURS * 3600))
            asyncio.run(run_once())
        except Exception as e:
            print(f"[ERROR] {e}", flush=True)

if __name__ == "__main__":
    main_loop()