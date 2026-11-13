#!/usr/bin/env python3
"""
Social uploader agent (free stack) - runs on a Windows PC or on an always-on server, controlled from Telegram.

How a post happens:
  1. Save a video into the inbox folder (it can be a Google Drive / OneDrive folder, see INBOX_DIR).
  2. The agent messages you on Telegram: "Where should this video be posted?"
     You reply with the places for THIS video, for example:  yt fb   or   ig2   or   all
  3. It asks for the title and caption. You paste them in ONE message (first line = title, the rest = caption).
  4. It shows the final text + date + times for the chosen places only. You reply:
       ok  |  date 21 Oct  |  ig2 8:30pm  |  pages yt fb  |  edit  |  cancel
  5. On "ok":  YouTube (private, auto-public at the set time, added to the Shorts playlist) and
               Facebook (native schedule) are uploaded right away, if chosen.  Instagram posts are published by
               this agent at the set times, so the agent must be running then (on a server it always is).

Telegram commands (when the agent is running):  /help   /status   /jobs   /cancel   /restart   /stop

Commands:
  python agent.py --auth    one-time YouTube login (opens a browser)
  python agent.py --check   shows what is still missing in your setup
  python agent.py --version prints the version (compare it with the server's to see if the files are current)
  python agent.py --chatid  finds your Telegram chat id (after you send your bot a message)
  python agent.py --cover video.mp4 [seconds]   saves the cover frame so you can look at it
  python agent.py           run the agent (keep it running)
"""
import functools
import http.server
import json
import logging
import os
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import captions

VERSION = "1.1.0"

for _s in (sys.stdout, sys.stderr):  # Marathi/emoji safe on Windows consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

BASE = Path(__file__).parent
S = captions.load_settings()
TZ = ZoneInfo(S.get("timezone", "Asia/Kolkata"))
INBOX = Path(os.getenv("INBOX_DIR") or (BASE / "inbox"))
SCHEDULED, DONE, SKIPPED = BASE / "scheduled", BASE / "done", BASE / "skipped"
JOBS_FILE = BASE / "schedule.json"
PUBLIC_TMP = BASE / ".public_tmp"
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
PLATFORMS = {p.strip().lower() for p in os.getenv("PLATFORMS", "youtube,facebook,instagram").split(",") if p.strip()}
IG_ACCOUNTS = {a.strip().lower() for a in os.getenv("IG_ACCOUNTS", "").split(",") if a.strip()}  # empty = all accounts
GRAPH_VER = os.getenv("GRAPH_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VER}"
TUNNEL_PORT = int(os.getenv("TUNNEL_PORT", "8765"))
TG_TOKEN, TG_CHAT = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
IG_PREPARE_HOURS = 20  # Instagram containers expire after 24h, so prepare at most 20h ahead

YT_SCOPES = ["https://www.googleapis.com/auth/youtube"]  # upload + add to playlist
YT_TOKEN, YT_SECRET = BASE / "token.json", BASE / "client_secret.json"

def redact(text) -> str:
    """Hide tokens in anything that is logged or sent to Telegram (error messages can contain URLs with tokens)."""
    text = str(text)
    for name in ("META_PAGE_TOKEN_1", "META_PAGE_TOKEN_2", "TELEGRAM_BOT_TOKEN"):
        value = os.getenv(name)
        if value:
            text = text.replace(value, "***")
    return re.sub(r"(access_token=)[^&\s'\"]+", r"\1***", text)


class _RedactFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


_handlers = [logging.StreamHandler(), logging.FileHandler(BASE / "agent.log", encoding="utf-8")]
for _h in _handlers:
    _h.setFormatter(_RedactFormatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=_handlers)
log = logging.getLogger("agent")


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
_tg_offset = None
_tg_last_warning = 0.0


def tg_send(text: str):
    text = redact(text)
    for i in range(0, len(text), 3900):
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          data={"chat_id": TG_CHAT, "text": text[i:i + 3900]}, timeout=30)
        except requests.RequestException as e:
            log.error("Telegram send failed: %s", e)


def tg_poll(timeout: int = 5) -> list:
    """New text messages from YOUR chat only."""
    global _tg_offset, _tg_last_warning
    params = {"timeout": timeout}
    if _tg_offset:
        params["offset"] = _tg_offset
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", params=params, timeout=timeout + 15).json()
    except (requests.RequestException, ValueError):
        time.sleep(5)
        return []
    if not r.get("ok", False):  # wrong/revoked token, or another agent reading the same bot: wait, do not hammer Telegram
        code = r.get("error_code")
        if time.time() - _tg_last_warning > 60:
            if code == 401:
                log.error("Telegram refused the bot token (wrong or revoked). Fix TELEGRAM_BOT_TOKEN in .env and restart the agent.")
            elif code == 409:
                log.error("Another program is reading this bot's messages. Is the agent still running on another computer?")
            else:
                log.error("Telegram error %s: %s", code, r.get("description"))
            _tg_last_warning = time.time()
        time.sleep(10)
        return []
    out = []
    for u in r.get("result", []):
        _tg_offset = u["update_id"] + 1
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) == str(TG_CHAT) and m.get("text"):
            out.append(m["text"])
    return out


def tg_whoami():
    """(True, '@botname') if Telegram accepts the token, (False, reason) if it refuses it, (None, reason) if unreachable."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getMe", timeout=20).json()
    except (requests.RequestException, ValueError):
        return None, "could not reach Telegram"
    if r.get("ok"):
        return True, "@" + str(r["result"].get("username", "?"))
    return False, str(r.get("description", "refused"))


def tg_drain():
    """Ignore messages sent while the agent was off."""
    global _tg_offset
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", params={"timeout": 0}, timeout=30).json()
        res = r.get("result", [])
        if res:
            _tg_offset = res[-1]["update_id"] + 1
    except (requests.RequestException, ValueError):
        pass


# --------------------------------------------------------------------------- #
# Dates, times, targets
# --------------------------------------------------------------------------- #
_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.I)


def parse_time(s: str) -> str:
    """'8' -> 08:00 (mornings by default), '8:30', '8:30pm', '20:15'."""
    m = _TIME.match(s.strip())
    if not m:
        raise ValueError(f"I could not read the time '{s}'. Use for example 8:30 or 7pm.")
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise ValueError(f"'{s}' is not a valid time.")
    return f"{h:02d}:{mi:02d}"


def parse_date(s: str, today):
    s = s.strip().lower()
    if s in ("today", "आज"):
        return today
    if s in ("tomorrow", "tmrw", "उद्या"):
        return today + timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    for fmt in ("%d/%m", "%d-%m", "%d %b", "%d %B", "%b %d", "%B %d"):
        try:
            d = datetime.strptime(s, fmt).date().replace(year=today.year)
            return d if d >= today else d.replace(year=today.year + 1)
        except ValueError:
            pass
    raise ValueError(f"I could not read the date '{s}'. Use for example: 21 Oct, 21/10, tomorrow.")


def enabled(platform: str) -> bool:
    return platform in PLATFORMS


def active_targets() -> list:
    """[(key, default_time)] for every platform that is switched on."""
    t = []
    if enabled("youtube"):
        t.append(("yt", S["youtube"]["publish_time"]))
    if enabled("facebook"):
        t.append(("fb", S["facebook"]["publish_time"]))
    if enabled("instagram"):
        t += [(f"ig{i}", a["publish_time"]) for i, a in enumerate(S["instagram_accounts"], 1)
              if not IG_ACCOUNTS or a["name"].lower() in IG_ACCOUNTS]
    return t


def label(key: str) -> str:
    if key == "yt":
        return "YouTube"
    if key == "fb":
        return "Facebook"
    return "Instagram @" + S["instagram_accounts"][int(key[2:]) - 1]["name"]


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%a %d %b, %H:%M")


# --------------------------------------------------------------------------- #
# Cover frame (7 seconds in, or the middle for very short videos)
# --------------------------------------------------------------------------- #
def video_duration(path: Path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                              str(path)], capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except Exception:
        return None


def cover_time(duration) -> float:
    t = float(S.get("cover_frame_seconds", 7))
    return max(duration / 2, 0) if duration and duration <= t else t


def make_cover(video: Path):
    out = video.with_name(video.stem + ".cover.jpg")
    t = cover_time(video_duration(video))
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)],
                       check=True, capture_output=True, timeout=120)
        return out
    except Exception as e:
        log.warning("Could not make a cover frame (is ffmpeg installed?): %s", e)
        return None


# --------------------------------------------------------------------------- #
# YouTube
# --------------------------------------------------------------------------- #
def youtube_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = Credentials.from_authorized_user_file(str(YT_TOKEN), YT_SCOPES) if YT_TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(str(YT_SECRET), YT_SCOPES).run_local_server(port=0)
        YT_TOKEN.write_text(creds.to_json())
    return creds


def youtube_add_to_playlist(yt, video_id: str):
    title = (S["youtube"].get("playlist_title") or "").strip().lower()
    if not title:
        return
    pid, page = None, None
    while True:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page).execute()
        for it in r.get("items", []):
            if it["snippet"]["title"].strip().lower() == title:
                pid = it["id"]
        page = r.get("nextPageToken")
        if pid or not page:
            break
    if not pid:
        raise RuntimeError(f'Playlist "{S["youtube"]["playlist_title"]}" not found on the channel')
    yt.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()


def youtube_upload(video: Path, post: dict, publish_at: datetime):
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    cfg = S["youtube"]
    yt = build("youtube", "v3", credentials=youtube_creds())
    status = {"privacyStatus": cfg.get("privacy", "private"), "selfDeclaredMadeForKids": False}
    if cfg.get("schedule_to_public", True):
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if cfg.get("ai_label"):
        status["containsSyntheticMedia"] = True
    body = {"snippet": {"title": post["title"], "description": post["description"], "tags": post["tags"],
                        "categoryId": os.getenv("YT_CATEGORY_ID", "22")}, "status": status}

    def run(b):
        media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
        req = yt.videos().insert(part="snippet,status", body=b, media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        return resp

    try:
        resp = run(body)
    except HttpError as e:
        if status.get("containsSyntheticMedia") and e.resp.status == 400:
            log.warning("YouTube rejected the AI-content flag; retrying without it (set it by hand in Studio)")
            status.pop("containsSyntheticMedia")
            resp = run(body)
        else:
            raise
    note = ""
    try:
        youtube_add_to_playlist(yt, resp["id"])
    except Exception as e:
        note = f" (could not add to playlist: {e})"
    return f"https://youtu.be/{resp['id']}{note}"


# --------------------------------------------------------------------------- #
# Facebook Page (native scheduling)
# --------------------------------------------------------------------------- #
def _check(r: requests.Response):
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
    return r.json()


def facebook_upload(video: Path, post: dict, publish_at: datetime, cover):
    """Chunked ('resumable') upload: works for any file size, unlike a single big request (error 413)."""
    cfg = S["facebook"]
    page_id = cfg.get("page_id")
    token = os.environ[cfg["page_token_env"]]
    url = f"https://graph-video.facebook.com/{GRAPH_VER}/{page_id}/videos"

    # 1) start: tell Facebook the file size
    s = _check(requests.post(url, data={"upload_phase": "start", "file_size": str(video.stat().st_size),
                                        "access_token": token}, timeout=120))
    session, video_id = s["upload_session_id"], s["video_id"]
    start, end = int(s["start_offset"]), int(s["end_offset"])

    # 2) transfer: send the pieces Facebook asks for, until it has everything
    with open(video, "rb") as fh:
        while start < end:
            fh.seek(start)
            chunk = fh.read(end - start)
            t = _check(requests.post(url, data={"upload_phase": "transfer", "upload_session_id": session,
                                                "start_offset": str(start), "access_token": token},
                                     files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
                                     timeout=600))
            new_start, new_end = int(t["start_offset"]), int(t["end_offset"])
            if new_start <= start and new_start < new_end:
                raise RuntimeError("Facebook did not accept the video data (upload is stuck)")
            start, end = new_start, new_end

    # 3) finish: text, schedule and cover
    finish = {"upload_phase": "finish", "upload_session_id": session, "description": post["message"],
              "published": "false", "scheduled_publish_time": str(int(publish_at.timestamp())), "access_token": token}
    r = None
    if cover:
        with open(cover, "rb") as cf:
            r = requests.post(url, data=finish, files={"thumb": cf}, timeout=600)
        if not r.ok:
            log.warning("Facebook rejected the cover (%s); finishing without it", r.status_code)
            r = None
    if r is None:
        r = requests.post(url, data=finish, timeout=600)
    _check(r)
    return video_id


# --------------------------------------------------------------------------- #
# Instagram (published by this agent at the set time)
# --------------------------------------------------------------------------- #
class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def list_directory(self, path):
        self.send_error(404)
        return None

    def log_message(self, *args):
        pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextmanager
def public_url(path: Path):
    """Temporary public link to the video through a free cloudflared tunnel."""
    PUBLIC_TMP.mkdir(exist_ok=True)
    name = secrets.token_urlsafe(16) + path.suffix.lower()
    shutil.copy2(path, PUBLIC_TMP / name)
    srv = _Server(("127.0.0.1", TUNNEL_PORT), functools.partial(_QuietHandler, directory=str(PUBLIC_TMP)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proc = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{TUNNEL_PORT}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    url, deadline = None, time.time() + 45
    while time.time() < deadline:
        line = proc.stderr.readline()
        if not line:
            break
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break
    threading.Thread(target=lambda: [None for _ in proc.stderr], daemon=True).start()
    try:
        if not url:
            raise RuntimeError("cloudflared gave no tunnel URL (is it installed?)")
        time.sleep(3)
        yield f"{url}/{name}"
    finally:
        proc.terminate()
        srv.shutdown()
        srv.server_close()
        (PUBLIC_TMP / name).unlink(missing_ok=True)


def ig_account(name: str) -> dict:
    return next(a for a in S["instagram_accounts"] if a["name"] == name)


def ig_prepare(video: Path, group: list):
    """Create + process the Instagram containers for every account of one video (one tunnel)."""
    frame_ms = int(cover_time(video_duration(video)) * 1000)
    with public_url(video) as url:
        for j in group:
            acc = ig_account(j["account"])
            try:
                r = requests.post(f"{GRAPH}/{acc['ig_user_id']}/media", data={
                    "media_type": "REELS", "video_url": url, "caption": j["caption"], "share_to_feed": "true",
                    "thumb_offset": frame_ms, "access_token": os.environ[acc["page_token_env"]]}, timeout=60)
                j["container_id"] = _check(r)["id"]
            except Exception as e:
                j["status"], j["error"] = "error", str(e)
        waiting = [j for j in group if j["status"] == "pending"]
        deadline = time.time() + 900
        while waiting and time.time() < deadline:
            for j in list(waiting):
                acc = ig_account(j["account"])
                s = requests.get(f"{GRAPH}/{j['container_id']}", params={
                    "fields": "status_code,status", "access_token": os.environ[acc["page_token_env"]]}, timeout=30).json()
                if s.get("status_code") == "FINISHED":
                    j["status"] = "ready"
                    waiting.remove(j)
                elif s.get("status_code") in ("ERROR", "EXPIRED"):
                    j["status"], j["error"] = "error", str(s)
                    waiting.remove(j)
            if waiting:
                time.sleep(10)
        for j in waiting:
            j["status"], j["error"] = "error", "Instagram took too long to process the video"


def ig_publish(j: dict) -> str:
    acc = ig_account(j["account"])
    token = os.environ[acc["page_token_env"]]
    pub = _check(requests.post(f"{GRAPH}/{acc['ig_user_id']}/media_publish",
                               data={"creation_id": j["container_id"], "access_token": token}, timeout=60))
    info = requests.get(f"{GRAPH}/{pub['id']}", params={"fields": "permalink", "access_token": token}, timeout=30).json()
    return info.get("permalink", f"media id {pub['id']}")


# --------------------------------------------------------------------------- #
# Scheduled Instagram jobs (kept in schedule.json so a restart loses nothing)
# --------------------------------------------------------------------------- #
def load_jobs() -> list:
    return json.loads(JOBS_FILE.read_text(encoding="utf-8")) if JOBS_FILE.exists() else []


def save_jobs(jobs: list):
    JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")


def archive_video(video: Path, group):
    DONE.mkdir(exist_ok=True)
    (DONE / f"{video.stem}.results.json").write_text(json.dumps(group, ensure_ascii=False, indent=2), encoding="utf-8")
    cover = video.with_name(video.stem + ".cover.jpg")
    cover.unlink(missing_ok=True)
    if os.getenv("KEEP_VIDEOS", "1") == "0":
        video.unlink(missing_ok=True)
    elif video.exists():
        shutil.move(str(video), DONE / video.name)


def run_due_jobs():
    jobs = load_jobs()
    if not jobs:
        return
    now = datetime.now(TZ)
    at = lambda j: datetime.fromisoformat(j["publish_at"])

    # 1) prepare containers (one tunnel per video)
    due = [j for j in jobs if j["status"] == "pending" and now >= at(j) - timedelta(hours=IG_PREPARE_HOURS)]
    for video in sorted({j["video"] for j in due}):
        group = [j for j in due if j["video"] == video]
        try:
            ig_prepare(Path(video), group)
        except Exception as e:
            log.exception("Instagram prepare failed")
            for j in group:
                j["status"], j["error"] = "error", str(e)
        save_jobs(jobs)
        for j in group:
            if j["status"] == "ready":
                tg_send(f"Instagram @{j['account']} is ready and will post at {fmt_dt(at(j))}. The agent must stay running until then.")
            else:
                tg_send(f"❌ Instagram @{j['account']} failed to prepare: {j.get('error')}")

    # 2) publish when the time comes
    for j in jobs:
        if j["status"] == "ready" and now >= at(j) and now >= datetime.fromisoformat(j.get("retry_at", j["publish_at"])):
            try:
                link = ig_publish(j)
                j["status"] = "published"
                tg_send(f"✅ Instagram @{j['account']} posted: {link}\nManual: hide likes/shares, check the AI label.")
            except Exception as e:
                j["attempts"] = j.get("attempts", 0) + 1
                if j["attempts"] >= 3:
                    j["status"], j["error"] = "error", str(e)
                    tg_send(f"❌ Instagram @{j['account']} failed to post: {e}")
                else:
                    j["retry_at"] = (now + timedelta(minutes=2)).isoformat()
                    log.warning("Instagram publish failed (attempt %s): %s", j["attempts"], e)
            save_jobs(jobs)

    # 3) tidy up videos whose Instagram posts are all published
    for video in sorted({j["video"] for j in jobs}):
        group = [j for j in jobs if j["video"] == video]
        if all(j["status"] == "published" for j in group):
            archive_video(Path(video), group)
            jobs = [j for j in jobs if j["video"] != video]
            save_jobs(jobs)


# --------------------------------------------------------------------------- #
# Telegram conversation (one video at a time)
# --------------------------------------------------------------------------- #
class Convo:
    def __init__(self, video: Path):
        self.video = video
        self.state = "await_targets"  # await_targets -> await_text -> await_confirm
        self.title = self.caption = None
        self.pending_text = None      # title+caption already prepared in a .txt file next to the video
        self.date = (datetime.now(TZ) + timedelta(days=1)).date()  # default: tomorrow
        self.defaults = dict(active_targets())  # the usual time for every place
        self.times = {}               # ONLY the places chosen for THIS video


convo = None


def publish_dt(c: Convo, key: str) -> datetime:
    return datetime.combine(c.date, datetime.strptime(c.times[key], "%H:%M").time(), tzinfo=TZ)


def schedule_problems(c: Convo) -> list:
    now, probs = datetime.now(TZ), []
    for key in c.times:
        dt = publish_dt(c, key)
        if dt < now + timedelta(minutes=15 if key in ("yt", "fb") else 2):
            probs.append(f"{label(key)} time ({fmt_dt(dt)}) has passed or is too close. Change it with 'date ...' or 'time {key} ...'.")
    return probs


def parse_targets(text: str) -> list:
    """'yt fb' / 'ig1' / 'all' / 'instagram' / an Instagram handle  ->  list of keys. Raises ValueError."""
    keys = [k for k, _ in active_targets()]
    ig_keys = [k for k in keys if k.startswith("ig")]
    aliases = {"all": keys, "yt": ["yt"], "youtube": ["yt"], "fb": ["fb"], "facebook": ["fb"],
               "ig": ig_keys, "instagram": ig_keys}
    for k in keys:
        aliases[k] = [k]
    for i, a in enumerate(S["instagram_accounts"], 1):
        aliases[a["name"].lower()] = aliases["@" + a["name"].lower()] = [f"ig{i}"]
    chosen = []
    for tok in re.split(r"[\s,+&/]+", text.lower().strip()):
        if not tok or tok == "and":
            continue
        if tok not in aliases:
            raise ValueError(f"I do not know '{tok}'. Use: {', '.join(keys)} or all.")
        chosen += [k for k in aliases[tok] if k in keys]
    if not chosen:
        raise ValueError("Pick at least one place, for example: " + " ".join(keys[:2]))
    return [k for k in keys if k in chosen]  # always in the usual order


def targets_menu() -> str:
    keys = [k for k, _ in active_targets()]
    example = " ".join(keys[:2])
    return ("Where should this video be posted?\n"
            f"Reply with the codes, separated by spaces. For example:  {example}   or   {keys[0]}   or   all\n\n"
            + "\n".join(f"  {k:<4} {label(k)}" for k in keys)
            + "\n\nSend 'skip' to ignore this video.")


def preview(c: Convo) -> str:
    posts = captions.build_posts(c.title, c.caption, S)
    ig_keys = [k for k in c.times if k.startswith("ig")]
    if ig_keys:
        acc = S["instagram_accounts"][int(ig_keys[0][2:]) - 1]["name"]
        body, layout = posts["instagram"][acc], "Instagram"
    elif "fb" in c.times:
        body, layout = posts["facebook"]["message"], "Facebook"
    else:
        body, layout = posts["youtube"]["description"], None
    if layout:
        where = f"Post text ({layout} layout" + ("; YouTube has the same without the title line" if "yt" in c.times else "") + "):"
    else:
        where = "YouTube description:"
    lines = ["PLEASE CHECK", "", "Posting to: " + ", ".join(label(k) for k in c.times), ""]
    if "yt" in c.times:
        lines += ["YouTube title:", posts["youtube"]["title"], ""]
    lines += [where, body, "", f"Date: {c.date.strftime('%A %d %b %Y')} (IST)  - same times as usual?"]
    lines += [f"  {key}  {label(key)}: {c.times[key]}" for key in c.times]
    for w in posts["warnings"] + schedule_problems(c):
        lines.append("⚠️ " + w)
    first = next(iter(c.times))
    lines += ["", f"Reply:  ok  |  date 21 Oct  |  pages {' '.join(list(c.times)[:2])}  |  edit  |  cancel",
              f"To change times:  {first} 8pm   or several at once:  {' 8pm, '.join(list(c.times)[:2])} 8pm   or   all 8pm"]
    return "\n".join(lines)


def start_convo(video: Path):
    global convo
    convo = Convo(video)
    dur = video_duration(video)
    sidecar = video.with_suffix(".txt")
    if sidecar.exists():  # optional: title+caption prepared in a .txt next to the video
        convo.pending_text = sidecar.read_text(encoding="utf-8")
    tg_send(f"New video: {video.name}" + (f" ({int(dur)}s)" if dur else "") + "\n\n" + targets_menu())


def ask_for_text(c: Convo):
    c.state = "await_text"
    tg_send("This video will be posted to: " + ", ".join(label(k) for k in c.times) +
            "\n\nNow send the title and caption in ONE message.\nFirst line = title, the rest = caption.\n"
            "(Or write 'Title: ...' and 'Caption: ...'.)\nChange the places any time with:  pages yt fb")


def set_targets(c: Convo, text: str):
    try:
        chosen = parse_targets(text)
    except ValueError as e:
        tg_send(str(e) + "\n\n" + targets_menu())
        return
    c.times = {k: c.times.get(k, c.defaults[k]) for k in chosen}  # keep times already changed for places that stay
    if c.title is None:
        if c.pending_text:
            text_ready, c.pending_text = c.pending_text, None
            tg_send("This video will be posted to: " + ", ".join(label(k) for k in c.times))
            set_text(c, text_ready)
        else:
            ask_for_text(c)
    else:
        c.state = "await_confirm"
        tg_send(preview(c))


def set_text(c: Convo, text: str):
    try:
        c.title, c.caption = captions.parse_title_caption(text)
    except ValueError as e:
        tg_send(str(e))
        return
    c.state = "await_confirm"
    tg_send(preview(c))


def end_convo(move_to=None):
    global convo
    if convo and move_to:
        move_to.mkdir(exist_ok=True)
        shutil.move(str(convo.video), move_to / convo.video.name)
        convo.video.with_suffix(".txt").unlink(missing_ok=True)
    convo = None


_TIMETOK = re.compile(r"^(\d{1,2}(:\d{2})?(am|pm)?|am|pm)$")


def time_changes(text: str, keys: list):
    """Read time commands in any of these styles (one or several per message):
         time yt 8pm        yt 8:30 pm        all 7am
         time yt 20:00 / time fb 20:00 (on separate lines)        yt 8pm, fb 9pm
    Returns {key: 'HH:MM'}, or None if the message is not a time command. Raises ValueError if it is a wrong one."""
    toks = [x for x in re.split(r"[\s,;]+", text.lower().strip()) if x]
    if not toks:
        return None
    starts_with_time = toks[0] == "time"
    body = [x for x in toks if x != "time"]
    names = set(keys) | {"all"}
    usage = f"Write the place and the time, for example:  {keys[0]} 8pm   or   {' 8pm, '.join(keys[:2])} 8pm   or   all 8pm"
    if not any(x in names for x in body):
        if starts_with_time:
            raise ValueError(usage + "\nPlaces for this video: " + ", ".join(keys))
        return None
    if not starts_with_time and not all(x in names or _TIMETOK.match(x) for x in body):
        return None  # ordinary text (for example a pasted new caption), not a time command
    changes, key, parts = {}, None, []

    def flush():
        if key is None:
            return
        if not parts:
            raise ValueError(f"I did not see a time for '{key}'. " + usage)
        value = parse_time(" ".join(parts))
        for k in (list(keys) if key == "all" else [key]):
            changes[k] = value

    for x in body:
        if x in names:
            flush()
            key, parts = x, []
        elif key is None:
            raise ValueError(usage)
        else:
            parts.append(x)
    flush()
    return changes


def status_text() -> str:
    lines = [f"✅ The agent is running (version {VERSION}).",
             "Places switched on: " + ", ".join(label(k) for k, _ in active_targets()),
             f"Working on: {convo.video.name}" if convo else "Not working on a video right now."]
    waiting = [p for p in INBOX.iterdir() if p.suffix.lower() in VIDEO_EXT] if INBOX.exists() else []
    lines.append(f"Videos in the inbox: {len(waiting)}")
    jobs = load_jobs()
    live = sorted((j for j in jobs if j["status"] in ("pending", "ready")), key=lambda j: j["publish_at"])
    if live:
        lines.append("Instagram posts waiting:")
        lines += [f"  @{j['account']} at {fmt_dt(datetime.fromisoformat(j['publish_at']))} ({j['status']})" for j in live]
    else:
        lines.append("No Instagram posts are waiting.")
    if live:
        lines.append("(/jobs lists them, /cancel removes them)")
    failed = [j for j in jobs if j["status"] == "error"]
    if failed:
        lines.append(f"⚠️ {len(failed)} Instagram post(s) failed earlier (see schedule.json).")
    return "\n".join(lines)


def waiting_jobs(jobs: list) -> list:
    """Instagram posts that have not been published yet, earliest first (the numbers /jobs shows)."""
    return sorted((j for j in jobs if j["status"] in ("pending", "ready", "error")), key=lambda j: j["publish_at"])


def jobs_text() -> str:
    live = waiting_jobs(load_jobs())
    if not live:
        return "No Instagram posts are waiting."
    lines = ["Instagram posts waiting:"]
    for n, j in enumerate(live, 1):
        first_line = (j.get("caption") or "").strip().splitlines()[0][:40] if (j.get("caption") or "").strip() else ""
        lines.append(f"{n}. @{j['account']}  {fmt_dt(datetime.fromisoformat(j['publish_at']))}  ({j['status']})  {first_line}")
    lines.append("")
    lines.append("Remove one with /cancel 1 (use its number), several with /cancel 1 2, or all with /cancel all.")
    lines.append("This removes Instagram posts only. YouTube and Facebook posts are held by Google and Facebook:"
                 " delete them in YouTube Studio and Meta Business Suite.")
    return "\n".join(lines)


def cancel_jobs(args: list) -> str:
    jobs = load_jobs()
    live = waiting_jobs(jobs)
    if not live:
        return "No Instagram posts are waiting."
    if not args:
        return "Which one? Send /cancel all, or /cancel 1 (the number from the list).\n\n" + jobs_text()
    if [a.lower() for a in args] == ["all"]:
        chosen = live
    else:
        try:
            numbers = sorted({int(a) for a in args})
        except ValueError:
            return "I did not understand. Use /cancel all, or /cancel 1 2 (numbers from /jobs)."
        bad = [n for n in numbers if not 1 <= n <= len(live)]
        if bad:
            return f"There is no post number {bad[0]}.\n\n" + jobs_text()
        chosen = [live[n - 1] for n in numbers]
    removed = {id(j) for j in chosen}
    keep = [j for j in jobs if id(j) not in removed]
    save_jobs(keep)
    for video in {j["video"] for j in chosen}:  # tidy up videos that no other waiting post needs
        if not any(j["video"] == video for j in keep):
            v = Path(video)
            v.with_name(v.stem + ".cover.jpg").unlink(missing_ok=True)
            if v.exists():
                SKIPPED.mkdir(exist_ok=True)
                shutil.move(str(v), SKIPPED / v.name)
    names = ", ".join(f"@{j['account']}" for j in chosen)
    return (f"Removed {len(chosen)} Instagram post(s): {names}. Nothing will be posted for them.\n"
            "YouTube and Facebook posts are not touched. Delete those in YouTube Studio and Meta Business Suite.")


def remote_command(text: str) -> bool:
    """/status, /jobs, /cancel, /restart, /stop from Telegram. Returns True if the message was one of these."""
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return False
    cmd, args = parts[0].lower().split("@")[0], parts[1:]
    if cmd in ("/start", "/help"):
        tg_send("Hello! The agent is running.\n\nTo post: save a video in the inbox folder. I will ask where it should "
                "go, then for the title and caption.\n\nCommands:\n  /status   what I am doing now\n"
                "  /jobs     list the Instagram posts that are waiting\n"
                "  /cancel   remove waiting Instagram posts (/cancel 1 or /cancel all)\n"
                "  /restart  restart the agent (when started with run_agent.bat or the server service)\n"
                "  /stop     stop the agent")
    elif cmd == "/status":
        tg_send(status_text())
    elif cmd == "/jobs":
        tg_send(jobs_text())
    elif cmd == "/cancel":
        tg_send(cancel_jobs(args))
    elif cmd == "/restart":
        if os.getenv("AGENT_LOOP") == "1":
            tg_send("Restarting the agent. It will be back in about 15 seconds. A video you were answering about "
                    "will be asked about again. Instagram posts already scheduled are kept.")
            sys.exit(0)  # run_agent.bat starts it again
        tg_send("/restart only works when the agent was started with run_agent.bat. "
                "Start it that way, or stop it and start it again by hand.")
    elif cmd == "/stop":
        tg_send("Stopping the agent. Instagram posts that are waiting will NOT go out until it runs again.")
        sys.exit(5)  # run_agent.bat does not restart after this
    else:
        return False
    return True


def handle_message(text: str):
    if remote_command(text):
        return
    return handle_conversation(text)


def handle_conversation(text: str):
    c = convo
    if c is None:
        tg_send("No video is waiting. Save a video in the inbox folder first. (Send /status to see what I am doing.)")
        return
    low = text.strip().lower()
    if low in ("cancel", "skip"):
        tg_send(f"Skipped {c.video.name}. It was moved to the 'skipped' folder.")
        end_convo(SKIPPED)
        return
    if c.state == "await_targets":
        set_targets(c, text)
        return
    if low == "pages" or low.startswith("pages "):  # change the places at any time
        set_targets(c, text[5:])
        return
    if c.state == "await_text":
        set_text(c, text)
        return
    # state == await_confirm
    try:
        changes = time_changes(text, list(c.times))
        if changes is not None:
            c.times.update(changes)
            tg_send(preview(c))
        elif low in ("ok", "yes", "y", "ok!", "okay"):
            probs = schedule_problems(c)
            if probs:
                tg_send("Cannot schedule yet:\n" + "\n".join(probs))
            else:
                execute(c)
        elif low.startswith("date "):
            c.date = parse_date(text[5:], datetime.now(TZ).date())
            tg_send(preview(c))
        elif low == "edit":
            c.state = "await_text"
            tg_send("OK, send the new title and caption in one message.")
        elif "\n" in text or len(text) > 80:  # a pasted edit
            set_text(c, text)
        else:
            tg_send("I did not understand. Reply: ok | date 21 Oct | yt 8pm | pages yt fb | edit | cancel")
    except ValueError as e:
        tg_send(str(e))


def execute(c: Convo):
    global convo
    tg_send("Working on it: " + ", ".join(label(k) for k in c.times) + "." +
            (" Instagram posts are published by the agent at their time." if any(k.startswith("ig") for k in c.times) else ""))
    SCHEDULED.mkdir(exist_ok=True)
    video = Path(shutil.move(str(c.video), SCHEDULED / f"{datetime.now():%Y%m%d-%H%M%S}_{c.video.name}"))
    c.video.with_suffix(".txt").unlink(missing_ok=True)
    posts = captions.build_posts(c.title, c.caption, S)
    pub = {key: publish_dt(c, key) for key in c.times}
    cover = make_cover(video) if ("fb" in pub or any(k.startswith("ig") for k in pub)) else None
    out = []

    if "yt" in pub:
        try:
            url = youtube_upload(video, posts["youtube"], pub["yt"])
            out.append(f"✅ YouTube uploaded as private, turns public {fmt_dt(pub['yt'])}\n   {url}")
        except Exception as e:
            log.exception("YouTube failed")
            out.append(f"❌ YouTube failed: {e}")
    if "fb" in pub:
        try:
            fid = facebook_upload(video, posts["facebook"], pub["fb"], cover)
            out.append(f"✅ Facebook scheduled for {fmt_dt(pub['fb'])} (video id {fid})")
        except Exception as e:
            log.exception("Facebook failed")
            out.append(f"❌ Facebook failed: {e}")

    jobs = load_jobs()
    ig_jobs = []
    for i, acc in enumerate(S["instagram_accounts"], 1):
        if f"ig{i}" in pub:
            ig_jobs.append({"id": secrets.token_hex(4), "video": str(video), "account": acc["name"],
                            "caption": posts["instagram"][acc["name"]], "publish_at": pub[f"ig{i}"].isoformat(),
                            "status": "pending", "container_id": None})
            out.append(f"🕒 Instagram @{acc['name']} will post at {fmt_dt(pub[f'ig{i}'])} (posted by the agent, which must be running)")
    if ig_jobs:
        save_jobs(jobs + ig_jobs)
    else:
        archive_video(video, {"title": c.title, "date": c.date.isoformat(), "results": list(out)})
    on_instagram = any(k.startswith("ig") for k in pub)
    manual = []
    if "yt" in pub:
        manual.append("YouTube: check 'Scheduled' in Studio")
    if on_instagram:
        manual.append("Instagram: hide likes/shares")
    ai_label = [name for name, chosen in (("Facebook", "fb" in pub), ("Instagram", on_instagram)) if chosen]
    if ai_label:
        manual.append(" and ".join(ai_label) + ": AI label")
    if manual:
        out.append("\nStill manual: " + "; ".join(manual) + ".")
    tg_send("\n".join(out))
    convo = None


# --------------------------------------------------------------------------- #
# Setup check, inbox watcher, main loop
# --------------------------------------------------------------------------- #
def check_setup():
    yn = lambda ok: "OK     " if ok else "MISSING"
    print("Platforms switched on:", ", ".join(sorted(PLATFORMS)))
    print(yn(TG_TOKEN and TG_CHAT), "Telegram token + chat id (.env)")
    if TG_TOKEN:
        ok, info = tg_whoami()
        print(yn(ok), "Telegram accepts the token: " + (info if ok else "NO - " + info))
    print(yn(shutil.which("ffmpeg")), "ffmpeg (cover frame)")
    print(yn(shutil.which("ffprobe")), "ffprobe (video length)")
    if enabled("youtube"):
        print(yn(YT_TOKEN.exists()), "YouTube login (run: python agent.py --auth)")
    if enabled("facebook"):
        f = S["facebook"]
        print(yn(f.get("page_id")), "Facebook page_id (settings.json)")
        print(yn(os.getenv(f["page_token_env"])), f"{f['page_token_env']} (.env)")
    if enabled("instagram"):
        print(yn(shutil.which("cloudflared")), "cloudflared (Instagram video link)")
        for a in S["instagram_accounts"]:
            if IG_ACCOUNTS and a["name"].lower() not in IG_ACCOUNTS:
                continue
            print(yn(a.get("ig_user_id")), f"ig_user_id for @{a['name']} (settings.json)")
            print(yn(os.getenv(a["page_token_env"])), f"{a['page_token_env']} for @{a['name']} (.env)")
    print("Inbox folder:", INBOX)


def scan_inbox(sizes: dict, known: set, queue: list):
    files = [p for p in sorted(INBOX.iterdir()) if p.suffix.lower() in VIDEO_EXT]
    known &= set(files)
    for p in files:
        if p in known or (convo and p == convo.video):
            continue
        size = p.stat().st_size
        if size > 0 and sizes.get(p) == size:  # same size twice = finished copying
            sizes.pop(p, None)
            known.add(p)
            queue.append(p)
        else:
            sizes[p] = size


def main():
    if "--auth" in sys.argv:
        youtube_creds()
        print("YouTube authorised. token.json saved.")
        return
    if "--chatid" in sys.argv:
        if not TG_TOKEN:
            sys.exit("Put your bot token in .env first (TELEGRAM_BOT_TOKEN=...).")
        try:
            r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", timeout=30).json()
        except (requests.RequestException, ValueError):
            sys.exit("Could not reach Telegram. Check your internet connection.")
        if not r.get("ok", False):
            sys.exit("Telegram said: " + str(r.get("description", "error")) + "  (is the token in .env correct?)")
        ids = sorted({u["message"]["chat"]["id"] for u in r.get("result", []) if "message" in u})
        if ids:
            print("Your chat id:", ", ".join(str(i) for i in ids))
            print("Put it in .env as:  TELEGRAM_CHAT_ID=" + str(ids[0]))
        else:
            print("No messages yet. Open your bot in Telegram, press Start, send 'hi', then run this again.")
        return
    if "--cover" in sys.argv:
        i = sys.argv.index("--cover")
        if len(sys.argv) <= i + 1:
            sys.exit("Usage: python agent.py --cover path\\to\\video.mp4 [seconds]")
        if len(sys.argv) > i + 2:
            S["cover_frame_seconds"] = float(sys.argv[i + 2])
        out = make_cover(Path(sys.argv[i + 1]))
        print(f"Cover frame saved: {out}" if out else "Could not make the cover (is ffmpeg installed?)")
        return
    if "--version" in sys.argv:
        print("Social uploader agent", VERSION)
        return
    if "--check" in sys.argv:
        check_setup()
        return
    if not (TG_TOKEN and TG_CHAT):
        log.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env (see README). Fix it, then start the agent again.")
        sys.exit(5)  # code 5 = do not restart automatically
    ok, info = tg_whoami()
    if ok is False:
        log.error("Telegram refused the bot token (%s). Fix TELEGRAM_BOT_TOKEN in .env, upload it, then start the agent again.", info)
        sys.exit(5)
    if ok:
        log.info("Telegram bot %s is connected", info)
    for d in (INBOX, SCHEDULED, DONE, SKIPPED):
        d.mkdir(exist_ok=True)
    tg_drain()
    log.info("Agent %s running. Inbox: %s | platforms: %s", VERSION, INBOX, ", ".join(sorted(PLATFORMS)))
    tg_send(f"Agent {VERSION} is running. Add a video to the inbox (or your Drive folder) to start. Send /help for the commands.")
    sizes, known, queue = {}, set(), []
    while True:
        try:
            scan_inbox(sizes, known, queue)
            if convo is None and queue:
                start_convo(queue.pop(0))
            for text in tg_poll(5):
                handle_message(text)
            run_due_jobs()
        except Exception:
            log.exception("Unexpected error (the agent keeps running)")
            time.sleep(10)


if __name__ == "__main__":
    main()
