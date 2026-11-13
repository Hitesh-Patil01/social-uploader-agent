"""
Offline tests for the Social Uploader project.

Run from the project folder:     python tests/test_project.py          (add -v for details)

No internet, no accounts and no tokens are needed. Every call to YouTube, Facebook, Instagram, Telegram and
Google is replaced by a fake, and the tests work on a temporary copy of the project, so your own files are never touched.
"""
import builtins
import contextlib
import io
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
TMP = None
agent = captions = meta_setup = None
SENT = []  # every Telegram message the agent "sent"

HEADINGS_MESSAGE = """शीर्षक (Title):

माझा पहिला व्हिडिओ ✨

कॅप्शन (Caption):

ही माझ्या व्हिडिओची पहिली ओळ आहे...
ही दुसरी ओळ आहे. 🌼"""


def setUpModule():
    """Work on a temporary copy, with fake credentials, and import the modules from there."""
    global TMP, agent, captions, meta_setup
    TMP = Path(tempfile.mkdtemp(prefix="uploader-test-"))
    for name in ("agent.py", "captions.py", "meta_setup.py"):
        shutil.copy(ROOT / name, TMP / name)
    shutil.copy(ROOT / "settings.example.json", TMP / "settings.json")
    (TMP / "inbox").mkdir()
    os.environ.update({
        "TELEGRAM_BOT_TOKEN": "123456:TESTTOKENTESTTOKENTESTTOKENTEST12", "TELEGRAM_CHAT_ID": "42",
        "PLATFORMS": "youtube,facebook,instagram", "INBOX_DIR": str(TMP / "inbox"),
        "META_PAGE_TOKEN_1": "EAATESTPAGETOKEN1", "META_PAGE_TOKEN_2": "EAATESTPAGETOKEN2",
    })
    os.environ.pop("IG_ACCOUNTS", None)
    os.environ.pop("AGENT_LOOP", None)
    os.chdir(TMP)
    sys.path.insert(0, str(TMP))
    import agent as _agent
    import captions as _captions
    import meta_setup as _meta
    agent, captions, meta_setup = _agent, _captions, _meta
    for acc in agent.S["instagram_accounts"]:
        acc["ig_user_id"] = "1234"
    agent.S["facebook"]["page_id"] = "999"


def tearDownModule():
    os.chdir(ROOT)
    shutil.rmtree(TMP, ignore_errors=True)


class Response:
    def __init__(self, data, ok=True, code=200):
        self._d, self.ok, self.status_code, self.text = data, ok, code, json.dumps(data)

    def json(self):
        return self._d


# --------------------------------------------------------------------------- #
class CaptionTests(unittest.TestCase):
    def test_first_line_is_title(self):
        t, c = captions.parse_title_caption("First line\n\nBody one\nBody two")
        self.assertEqual((t, c), ("First line", "Body one\nBody two"))

    def test_marathi_headings_with_english_in_brackets(self):
        t, c = captions.parse_title_caption(HEADINGS_MESSAGE)
        self.assertEqual(t, "माझा पहिला व्हिडिओ ✨")
        self.assertTrue(c.startswith("ही माझ्या व्हिडिओची"))
        for word in ("शीर्षक", "कॅप्शन", "(Title)", "(Caption)"):
            self.assertNotIn(word, t + c)

    def test_other_heading_styles(self):
        cases = {
            "Tittle: T1\n\nCaption:   C1": ("T1", "C1"),
            "**शीर्षक (Title):** T2\n**कॅप्शन (Caption):** C2": ("T2", "C2"),
            "Title (शीर्षक): T3\nCaption (कॅप्शन): C3": ("T3", "C3"),
            "शीर्षक\nT4\nकॅप्शन\nC4": ("T4", "C4"),
            "📌 Title: T5\n📝 Caption: C5": ("T5", "C5"),
            "शीर्षक/Title: T6\nकॅप्शन/Caption: C6": ("T6", "C6"),
            "My title line\n\nCaption:\n\nC7": ("My title line", "C7"),
            "Title:\n\nT8\n\nBody below": ("T8", "Body below"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(captions.parse_title_caption(text), expected)

    def test_ordinary_sentences_are_not_headings(self):
        t, c = captions.parse_title_caption("Title of my video\nTitles are shown here")
        self.assertEqual((t, c), ("Title of my video", "Titles are shown here"))

    def test_missing_parts_give_friendly_errors(self):
        for bad in ("", "   ", "only a title", "Title: x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                captions.parse_title_caption(bad)

    def test_build_posts_adds_mention_hashtags_and_cta_once(self):
        s = captions.load_settings()
        pasted = "Body text\n\n" + s["fixed_text"]["cta"] + "\n\n@your_instagram_handle\n\n#old #tags"
        posts = captions.build_posts("My title", pasted, s)
        ig = posts["instagram"]["your_instagram_handle"]
        self.assertEqual(ig.count(s["fixed_text"]["cta"]), 1)
        self.assertEqual(ig.count("@your_instagram_handle"), 1)
        self.assertNotIn("#old", ig)
        self.assertTrue(ig.startswith("My title\n\nBody text"))
        self.assertIn("#yourhashtag1", ig)
        self.assertNotIn("My title", posts["youtube"]["description"])  # the title has its own box on YouTube
        self.assertEqual(posts["youtube"]["title"], "My title")
        self.assertEqual(posts["youtube"]["tags"], s["youtube"]["tags"])
        self.assertTrue(posts["facebook"]["message"].startswith("My title"))

    def test_long_title_warns_and_youtube_rejects_angle_brackets(self):
        posts = captions.build_posts("x" * 120 + "<b>", "body", captions.load_settings())
        self.assertTrue(posts["warnings"])
        self.assertLessEqual(len(posts["youtube"]["title"]), 100)
        self.assertNotIn("<", posts["youtube"]["title"])


# --------------------------------------------------------------------------- #
class TimeAndDateTests(unittest.TestCase):
    def test_parse_time(self):
        for text, expected in {"8": "08:00", "8:30": "08:30", "7pm": "19:00", "8:00 pm": "20:00",
                               "12am": "00:00", "12pm": "12:00", "20:15": "20:15"}.items():
            with self.subTest(text=text):
                self.assertEqual(agent.parse_time(text), expected)
        for bad in ("eight", "25:00", "8:75"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                agent.parse_time(bad)

    def test_parse_date(self):
        today = datetime(2026, 10, 24).date()
        self.assertEqual(agent.parse_date("tomorrow", today), datetime(2026, 10, 25).date())
        self.assertEqual(agent.parse_date("21 Oct", today), datetime(2027, 10, 21).date())  # already passed: next year
        self.assertEqual(agent.parse_date("30 Oct", today), datetime(2026, 10, 30).date())
        self.assertEqual(agent.parse_date("2026-12-01", today), datetime(2026, 12, 1).date())
        with self.assertRaises(ValueError):
            agent.parse_date("whenever", today)

    def test_time_commands_in_every_style(self):
        keys = ["yt", "fb", "ig1", "ig2"]
        cases = {
            "Time\nyt 8pm\nfb 8pm": {"yt": "20:00", "fb": "20:00"},
            "time yt 20:00\ntime fb 20:00": {"yt": "20:00", "fb": "20:00"},
            "time yt 8:00 pm\ntime fb 8:00 pm": {"yt": "20:00", "fb": "20:00"},
            "yt 7am fb 7:45am": {"yt": "07:00", "fb": "07:45"},
            "yt 8pm, fb 9pm": {"yt": "20:00", "fb": "21:00"},
            "all 6:30am": {k: "06:30" for k in keys},
            "time ig2 8:30": {"ig2": "08:30"},
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(agent.time_changes(text, keys), expected)

    def test_normal_messages_are_not_time_commands(self):
        for text in ("ok", "edit", "date 25 Oct", "pages yt fb", "Title: A new title\nCaption: written at 6pm"):
            with self.subTest(text=text):
                self.assertIsNone(agent.time_changes(text, ["yt", "fb"]))

    def test_wrong_time_commands_explain_themselves(self):
        for text in ("time", "time yt eight", "time yt"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                agent.time_changes(text, ["yt", "fb"])


# --------------------------------------------------------------------------- #
class AgentCase(unittest.TestCase):
    """Base: fresh state and fake uploaders for each test."""

    def setUp(self):
        SENT.clear()
        agent.convo = None
        for folder in ("scheduled", "done", "skipped"):
            shutil.rmtree(TMP / folder, ignore_errors=True)
        (TMP / "schedule.json").unlink(missing_ok=True)
        for f in (TMP / "inbox").glob("*"):
            f.unlink()
        self.calls = []
        patches = [
            mock.patch.object(agent, "tg_send", lambda text: SENT.append(text)),
            mock.patch.object(agent, "youtube_upload", lambda v, p, at: self.calls.append(("yt", p["title"])) or "https://youtu.be/FAKE"),
            mock.patch.object(agent, "facebook_upload", lambda v, p, at, cv: self.calls.append(("fb", p["message"])) or "FB1"),
            mock.patch.object(agent, "make_cover", lambda v: None),
            mock.patch.object(agent, "video_duration", lambda p: 33.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def new_video(self, name="reel.mp4"):
        path = TMP / "inbox" / name
        path.write_bytes(b"video")
        agent.start_convo(path)
        SENT.clear()
        return path

    def say(self, text):
        SENT.clear()
        agent.handle_message(text)
        return "\n".join(SENT)

    def jobs(self):
        return agent.load_jobs()


class ConversationTests(AgentCase):
    def test_youtube_and_facebook_only(self):
        self.new_video()
        self.assertIn("Posting to: YouTube, Facebook", self.say("yt fb") + self.say("Title: T\nCaption: C"))
        out = self.say("date tomorrow")
        self.assertIn("Posting to: YouTube, Facebook", out)
        self.assertNotIn("Instagram", out.split("Date:")[1])  # no Instagram time lines
        result = self.say("ok")
        self.assertEqual([c[0] for c in self.calls], ["yt", "fb"])
        self.assertNotIn("❌", result)
        self.assertNotIn("Instagram", result)  # nothing is scheduled on Instagram
        self.assertEqual(self.jobs(), [])
        self.assertTrue(list((TMP / "done").glob("*.mp4")))  # archived straight away
        record = json.loads(next((TMP / "done").glob("*.results.json")).read_text(encoding="utf-8"))
        self.assertEqual(record["title"], "T")

    def test_instagram_second_account_only(self):
        self.new_video()
        self.say("your_second_instagram_handle")  # an account name works as a code
        out = self.say("Title: T\nCaption: C")
        self.assertIn("Posting to: Instagram @your_second_instagram_handle", out)
        self.assertIn("@your_second_instagram_handle", out)
        result = self.say("ok")
        self.assertEqual(self.calls, [])
        self.assertNotIn("❌", result)  # e.g. a YouTube upload attempted by mistake would show here
        self.assertNotIn("YouTube", result)
        self.assertNotIn("Facebook", result)
        self.assertIn("will post at", result)
        jobs = self.jobs()
        self.assertEqual([j["account"] for j in jobs], ["your_second_instagram_handle"])
        self.assertEqual(jobs[0]["status"], "pending")
        self.assertTrue(jobs[0]["caption"].startswith("T\n\nC"))

    def test_ig_means_all_instagram_accounts_and_all_means_everything(self):
        self.assertEqual(agent.parse_targets("ig"), ["ig1", "ig2"])
        self.assertEqual(agent.parse_targets("instagram"), ["ig1", "ig2"])
        self.assertEqual(agent.parse_targets("all"), ["yt", "fb", "ig1", "ig2"])
        self.assertEqual(agent.parse_targets("ig2, yt"), ["yt", "ig2"])  # always in the usual order

    def test_unknown_place_shows_the_menu_again(self):
        self.new_video()
        out = self.say("foo")
        self.assertIn("I do not know 'foo'", out)
        self.assertIn("Where should this video be posted?", out)
        self.assertEqual(agent.convo.state, "await_targets")

    def test_pages_command_keeps_times_already_changed(self):
        self.new_video()
        self.say("all")
        self.say("Title: T\nCaption: C")
        self.say("time ig2 9:15")
        out = self.say("pages ig2 yt")
        self.assertIn("Posting to: YouTube, Instagram @your_second_instagram_handle", out)
        self.assertIn("ig2  Instagram @your_second_instagram_handle: 09:15", out)
        self.assertIn("yt  YouTube: 08:00", out)

    def test_times_can_be_changed_with_several_styles(self):
        self.new_video()
        self.say("yt fb")
        self.say("Title: T\nCaption: C")
        self.assertIn("yt  YouTube: 20:00", self.say("Time\nyt 8pm\nfb 8pm"))
        self.assertIn("fb  Facebook: 09:30", self.say("fb 9:30 am"))

    def test_time_in_the_past_is_refused(self):
        self.new_video()
        self.say("yt")
        self.say("Title: T\nCaption: C")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.say(f"date {yesterday}")
        out = self.say("ok")
        self.assertIn("Cannot schedule yet", out)
        self.assertEqual(self.calls, [])

    def test_headings_in_a_pasted_message_never_reach_the_posts(self):
        self.new_video()
        self.say("yt fb")
        out = self.say(HEADINGS_MESSAGE)
        self.assertIn("PLEASE CHECK", out)
        self.assertNotIn("शीर्षक (Title)", out)
        self.assertNotIn("कॅप्शन (Caption)", out)
        self.say("ok")
        for _, text in self.calls:
            self.assertNotIn("(Title)", text)
            self.assertNotIn("(Caption)", text)

    def test_cancel_moves_the_video_to_skipped(self):
        path = self.new_video()
        self.say("cancel")
        self.assertIsNone(agent.convo)
        self.assertTrue((TMP / "skipped" / path.name).exists())

    def test_title_and_caption_can_come_from_a_text_file(self):
        path = TMP / "inbox" / "prepared.mp4"
        path.write_bytes(b"video")
        path.with_suffix(".txt").write_text("Title: From file\nCaption: Prepared text", encoding="utf-8")
        agent.start_convo(path)
        SENT.clear()
        out = self.say("yt")
        self.assertIn("PLEASE CHECK", out)
        self.assertIn("From file", out)

    def test_telegram_commands(self):
        self.assertIn(agent.VERSION, self.say("/status"))
        self.assertIn("agent is running", self.say("/start").lower())
        self.assertIn("only works when", self.say("/restart"))  # not started with run_agent.bat
        with mock.patch.dict(os.environ, {"AGENT_LOOP": "1"}):
            with self.assertRaises(SystemExit) as restart:
                agent.handle_message("/restart")
            self.assertEqual(restart.exception.code, 0)  # the service manager starts it again
        with self.assertRaises(SystemExit) as stop:
            agent.handle_message("/stop")
        self.assertEqual(stop.exception.code, 5)  # code 5 = stay stopped


class InstagramQueueTests(AgentCase):
    def make_job(self, hours_ahead):
        video = TMP / "scheduled" / "queued.mp4"
        video.parent.mkdir(exist_ok=True)
        video.write_bytes(b"video")
        job = {"id": "abc", "video": str(video), "account": "your_instagram_handle", "caption": "cap",
               "publish_at": (datetime.now(agent.TZ) + timedelta(hours=hours_ahead)).isoformat(),
               "status": "pending", "container_id": None}
        agent.save_jobs([job])
        return video

    def test_due_post_is_prepared_published_and_archived(self):
        video = self.make_job(hours_ahead=-0.01)

        def fake_prepare(path, group):
            for j in group:
                j["status"], j["container_id"] = "ready", "C1"

        with mock.patch.object(agent, "ig_prepare", fake_prepare), \
                mock.patch.object(agent, "ig_publish", lambda j: "https://instagram.com/p/FAKE"):
            agent.run_due_jobs()
        self.assertEqual(self.jobs(), [])
        self.assertTrue(any("posted: https://instagram.com/p/FAKE" in m for m in SENT))
        self.assertTrue((TMP / "done" / video.name).exists())

    def test_post_far_in_the_future_is_not_prepared_yet(self):
        self.make_job(hours_ahead=30)  # Instagram only keeps a prepared video for 24 hours
        prepared = []
        with mock.patch.object(agent, "ig_prepare", lambda v, g: prepared.append(v)):
            agent.run_due_jobs()
        self.assertEqual(prepared, [])
        self.assertEqual(self.jobs()[0]["status"], "pending")
        self.assertIn("@your_instagram_handle", self.say("/status"))

    def test_failed_publish_retries_then_reports(self):
        self.make_job(hours_ahead=-0.01)
        jobs = self.jobs()
        jobs[0].update(status="ready", container_id="C1")
        agent.save_jobs(jobs)
        with mock.patch.object(agent, "ig_publish", mock.Mock(side_effect=RuntimeError("boom"))):
            for _ in range(3):
                agent.run_due_jobs()
                jobs = self.jobs()
                jobs[0].pop("retry_at", None)  # pretend the two-minute wait has passed
                agent.save_jobs(jobs)
        self.assertEqual(self.jobs()[0]["status"], "error")
        self.assertTrue(any("failed to post" in m for m in SENT))


class QueueCommandTests(AgentCase):
    """/jobs and /cancel: look at, and remove, the Instagram posts that are waiting."""

    def add_jobs(self):
        jobs = []
        for n, (account, hours) in enumerate([("your_instagram_handle", 30), ("your_second_instagram_handle", 50)], 1):
            video = TMP / "scheduled" / f"q{n}.mp4"
            video.parent.mkdir(exist_ok=True)
            video.write_bytes(b"video")
            jobs.append({"id": f"id{n}", "video": str(video), "account": account, "caption": f"Caption line {n}\nmore",
                         "publish_at": (datetime.now(agent.TZ) + timedelta(hours=hours)).isoformat(),
                         "status": "pending", "container_id": None})
        agent.save_jobs(jobs)
        return [Path(j["video"]) for j in jobs]

    def test_jobs_lists_numbered_posts_earliest_first(self):
        self.add_jobs()
        out = self.say("/jobs")
        self.assertIn("1. @your_instagram_handle", out)
        self.assertIn("2. @your_second_instagram_handle", out)
        self.assertIn("Caption line 1", out)
        self.assertIn("YouTube Studio", out)  # tells you YouTube and Facebook posts are deleted elsewhere

    def test_cancel_one_removes_only_that_post(self):
        videos = self.add_jobs()
        out = self.say("/cancel 1")
        self.assertIn("Removed 1", out)
        self.assertEqual([j["account"] for j in self.jobs()], ["your_second_instagram_handle"])
        self.assertFalse(videos[0].exists())
        self.assertTrue((TMP / "skipped" / videos[0].name).exists())
        self.assertTrue(videos[1].exists())  # the other post still needs its video

    def test_cancel_all_and_bot_name_suffix(self):
        self.add_jobs()
        self.assertIn("Removed 2", self.say("/cancel@my_bot all"))
        self.assertEqual(self.jobs(), [])
        self.assertIn("No Instagram posts are waiting", self.say("/jobs"))

    def test_bad_cancel_input_changes_nothing(self):
        self.add_jobs()
        for text in ("/cancel", "/cancel 9", "/cancel x"):
            with self.subTest(text=text):
                self.assertNotIn("Removed", self.say(text))
                self.assertEqual(len(self.jobs()), 2)

    def test_a_cancelled_post_is_never_published(self):
        self.add_jobs()
        jobs = self.jobs()
        jobs[0].update(status="ready", container_id="C1",
                       publish_at=(datetime.now(agent.TZ) - timedelta(minutes=1)).isoformat())
        agent.save_jobs(jobs)
        self.say("/cancel 1")
        publish = mock.Mock(return_value="link")
        with mock.patch.object(agent, "ig_publish", publish), mock.patch.object(agent, "ig_prepare", mock.Mock()):
            agent.run_due_jobs()
        publish.assert_not_called()

    def test_a_video_shared_by_two_posts_is_kept_until_the_last_one_is_cancelled(self):
        video = TMP / "scheduled" / "shared.mp4"
        video.parent.mkdir(exist_ok=True)
        video.write_bytes(b"video")
        when = (datetime.now(agent.TZ) + timedelta(hours=30)).isoformat()
        agent.save_jobs([{"id": f"s{n}", "video": str(video), "account": acc, "caption": "c", "publish_at": when,
                          "status": "pending", "container_id": None}
                         for n, acc in enumerate(["your_instagram_handle", "your_second_instagram_handle"], 1)])
        self.say("/cancel 1")
        self.assertTrue(video.exists())  # the other account still needs this video
        self.say("/cancel 1")
        self.assertFalse(video.exists())  # nobody needs it any more
        self.assertTrue((TMP / "skipped" / "shared.mp4").exists())

    def test_unknown_slash_messages_are_not_swallowed(self):
        self.assertIn("No video is waiting", self.say("/something"))


class FacebookUploadTests(unittest.TestCase):
    def test_chunked_upload_sends_every_byte_and_schedules(self):
        data = os.urandom(100)
        video = TMP / "fbtest.mp4"
        cover = TMP / "fbtest.jpg"
        video.write_bytes(data)
        cover.write_bytes(b"JPEG")
        received, phases = bytearray(), []

        def fake_post(url, data=None, files=None, timeout=None):
            phase = data["upload_phase"]
            phases.append(phase)
            if phase == "start":
                self.assertEqual(data["file_size"], "100")
                return Response({"upload_session_id": "S", "video_id": "VID", "start_offset": "0", "end_offset": "7"})
            if phase == "transfer":
                start, chunk = int(data["start_offset"]), files["video_file_chunk"][1]
                self.assertEqual(start, len(received))
                received.extend(chunk)
                new_start = start + len(chunk)
                return Response({"start_offset": str(new_start), "end_offset": str(min(new_start + 7, 100))})
            self.assertEqual(data["published"], "false")
            self.assertTrue(data["scheduled_publish_time"].isdigit())
            self.assertEqual(data["description"], "post text")
            self.assertIn("thumb", files)
            return Response({"success": True})

        with mock.patch.object(agent.requests, "post", fake_post):
            vid = agent.facebook_upload(video, {"message": "post text"}, datetime.now(agent.TZ) + timedelta(days=1), cover)
        self.assertEqual(vid, "VID")
        self.assertEqual(bytes(received), data)
        self.assertEqual((phases[0], phases[-1]), ("start", "finish"))


class TelegramTests(unittest.TestCase):
    def test_refused_token_waits_instead_of_hammering_telegram(self):
        waits = []
        with mock.patch.object(agent.requests, "get", lambda *a, **k: Response({"ok": False, "error_code": 401, "description": "Unauthorized"})), \
                mock.patch.object(agent.time, "sleep", lambda s: waits.append(s)):
            self.assertEqual(agent.tg_poll(1), [])
        self.assertEqual(waits, [10])

    def test_only_your_own_chat_is_obeyed(self):
        updates = {"ok": True, "result": [
            {"update_id": 1, "message": {"chat": {"id": 42}, "text": "mine"}},
            {"update_id": 2, "message": {"chat": {"id": 999}, "text": "a stranger"}}]}
        with mock.patch.object(agent.requests, "get", lambda *a, **k: Response(updates)):
            self.assertEqual(agent.tg_poll(1), ["mine"])

    def test_tokens_are_hidden_in_logs_and_messages(self):
        text = f"error at https://api.telegram.org/bot{agent.TG_TOKEN}/x and ?access_token=EAAOTHERSECRET&y=1"
        hidden = agent.redact(text)
        self.assertNotIn(agent.TG_TOKEN, hidden)
        self.assertNotIn("EAAOTHERSECRET", hidden)

    def test_token_check_tells_good_from_bad_from_unreachable(self):
        with mock.patch.object(agent.requests, "get", lambda *a, **k: Response({"ok": True, "result": {"username": "my_bot"}})):
            self.assertEqual(agent.tg_whoami(), (True, "@my_bot"))
        with mock.patch.object(agent.requests, "get", lambda *a, **k: Response({"ok": False, "description": "Unauthorized"})):
            self.assertEqual(agent.tg_whoami()[0], False)
        with mock.patch.object(agent.requests, "get", mock.Mock(side_effect=agent.requests.ConnectionError())):
            self.assertIsNone(agent.tg_whoami()[0])

    def test_agent_refuses_to_start_with_a_rejected_token(self):
        with mock.patch.object(agent.requests, "get", lambda *a, **k: Response({"ok": False, "description": "Unauthorized"})), \
                mock.patch.object(sys, "argv", ["agent.py"]), self.assertRaises(SystemExit) as stop:
            agent.main()
        self.assertEqual(stop.exception.code, 5)


class MetaSetupTests(unittest.TestCase):
    def setUp(self):
        shutil.copy(ROOT / "settings.example.json", TMP / "settings.json")
        (TMP / ".env").write_text("PLATFORMS=youtube\n", encoding="utf-8")
        self.addCleanup(lambda: (TMP / ".env").unlink(missing_ok=True))

    @staticmethod
    def fake_graph(url, params=None, timeout=None):
        if url.endswith("/oauth/access_token"):
            return Response({"access_token": "LONGUSER"})
        if url.endswith("/me/accounts"):
            return Response({"data": []})  # the normal list can be empty with Facebook Login for Business
        if url.endswith("/debug_token"):
            return Response({"data": {"scopes": ["pages_show_list"],
                                      "granular_scopes": [{"scope": "pages_show_list", "target_ids": ["111", "222"]}]}})
        if url.endswith("/111"):
            return Response({"id": "111", "name": "Your Facebook Page Name", "access_token": "PAGETOK1",
                             "instagram_business_account": {"id": "9001", "username": "your_instagram_handle"}})
        if url.endswith("/222"):
            return Response({"id": "222", "name": "Second Page", "access_token": "PAGETOK2",
                             "connected_instagram_account": {"id": "9002", "username": "your_second_instagram_handle"}})
        raise AssertionError(url)

    def run_helper(self, answers):
        feed = iter(answers)
        with mock.patch.object(meta_setup.requests, "get", self.fake_graph), \
                mock.patch.object(builtins, "input", lambda prompt="": next(feed)), \
                mock.patch.object(meta_setup.os, "system", lambda cmd: 0), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            meta_setup.main()
        return out.getvalue()

    def test_full_run_saves_tokens_and_ids(self):
        out = self.run_helper(["1234567890123456", "0123456789abcdef0123456789abcdef", "EAA" + "x" * 200, "", "", ""])
        env = (TMP / ".env").read_text(encoding="utf-8")
        self.assertIn("META_PAGE_TOKEN_1=PAGETOK1", env)
        self.assertIn("META_PAGE_TOKEN_2=PAGETOK2", env)
        saved = json.loads((TMP / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["facebook"]["page_id"], "111")
        self.assertEqual([a["ig_user_id"] for a in saved["instagram_accounts"]], ["9001", "9002"])
        self.assertNotIn("PAGETOK1", out)  # tokens are never printed

    def test_swapped_secret_and_token_are_caught_before_calling_facebook(self):
        with self.assertRaises(SystemExit) as stop:
            self.run_helper(["1234567890123456", "EAA" + "x" * 200, "0123456789abcdef0123456789abcdef"])
        self.assertIn("looks like the long token", str(stop.exception))


# --------------------------------------------------------------------------- #
class ProjectFileTests(unittest.TestCase):
    """The files themselves: syntax, line endings, and that the docs match the code."""

    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_python_files_compile(self):
        for name in ("agent.py", "captions.py", "meta_setup.py", "tests/test_project.py"):
            with self.subTest(name=name):
                py_compile.compile(str(ROOT / name), doraise=True, cfile=str(TMP / "x.pyc"))

    def test_shell_scripts_have_valid_syntax(self):
        if not shutil.which("bash"):
            self.skipTest("bash is not available on this computer")
        for script in sorted((ROOT / "server").glob("*.sh")):
            with self.subTest(script=script.name):
                self.assertEqual(subprocess.run(["bash", "-n", str(script)]).returncode, 0)

    def test_line_endings(self):
        for name in ("server/setup_server.sh", "server/sync_inbox.sh", "server/social-uploader.service", "agent.py"):
            self.assertNotIn(b"\r\n", (ROOT / name).read_bytes(), f"{name} must use LF line endings")
        for name in ("run_agent.bat", "deploy_to_server.bat"):
            data = (ROOT / name).read_bytes()
            self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), f"{name} must use CRLF line endings")

    def test_service_file_template(self):
        service = self.read("server/social-uploader.service")
        for needle in ("__USER__", "__DIR__", "Restart=always", "RestartPreventExitStatus=5", "AGENT_LOOP=1"):
            self.assertIn(needle, service)

    def test_example_settings_work_for_every_platform(self):
        s = json.loads(self.read("settings.example.json"))
        posts = captions.build_posts("Title", "Caption", s)
        self.assertEqual(len(posts["instagram"]), len(s["instagram_accounts"]))
        self.assertTrue(posts["facebook"]["message"] and posts["youtube"]["description"])

    def test_every_environment_variable_is_documented(self):
        code = "\n".join(self.read(f) for f in ("agent.py", "captions.py", "meta_setup.py"))
        used = set(re.findall(r'os\.(?:getenv|environ\.get)\(\s*"([A-Z_0-9]+)"', code))
        used |= set(re.findall(r'os\.environ\[\s*"([A-Z_0-9]+)"', code))
        used -= {"AGENT_LOOP"}  # set by run_agent.bat / the service, never by the user
        example = self.read(".env.example")
        documented = set(re.findall(r"^\s*#?\s*([A-Z][A-Z_0-9]+)=", example, re.M))
        self.assertEqual(sorted(used - documented), [], "missing from .env.example")

    def test_readme_covers_every_command(self):
        readme = self.read("README.md")
        for flag in ("--auth", "--check", "--chatid", "--cover", "--version"):
            self.assertIn(f'"{flag}"', self.read("agent.py"))
            self.assertIn(flag, readme, f"README does not mention {flag}")
        for command in ("/status", "/jobs", "/cancel", "/restart", "/stop", "/help"):
            self.assertIn(command, readme)
        for name in ("agent.py", "captions.py", "meta_setup.py", "run_agent.bat", "deploy_to_server.bat",
                     "settings.example.json", ".env.example", "server/setup_server.sh", "server/sync_inbox.sh"):
            self.assertTrue((ROOT / name).exists(), f"{name} is missing")
            self.assertIn(name.split("/")[-1], readme, f"README does not mention {name}")

    def test_readme_names_the_current_version(self):
        self.assertIn(agent.VERSION, self.read("README.md"))

    def test_no_stale_wording(self):
        """The agent's own messages must not claim the PC is needed (it can run on a server). The README may say so for Track A."""
        for name in ("agent.py", "captions.py", "meta_setup.py"):
            text = self.read(name)
            for stale in ("PC must be on", "Keep the PC on", "GitHub Actions", "--once"):
                self.assertNotIn(stale, text, f"{name}: '{stale}'")
        for stale in ("GitHub Actions", "--once"):
            self.assertNotIn(stale, self.read("README.md"), f"README.md: '{stale}'")

    def test_no_secrets_or_personal_data_in_shareable_files(self):
        patterns = {
            "Telegram bot token": r"\b\d{8,10}:AA[A-Za-z0-9_-]{20,}",
            "Meta token": r"\bEAA[A-Za-z0-9]{40,}",
            "Google client secret": r"GOCSPX-[A-Za-z0-9_-]{8,}",
            "private key": r"BEGIN (?:OPENSSH |RSA )?PRIVATE KEY",
            "public IP address": r"\b(?!127\.|10\.|0\.|192\.168\.|203\.0\.113\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        }
        for name in ("agent.py", "captions.py", "meta_setup.py", "README.md", "settings.example.json", ".env.example",
                     "run_agent.bat", "deploy_to_server.bat", "server/setup_server.sh", "server/sync_inbox.sh",
                     "server/social-uploader.service", "tests/test_project.py"):
            text = self.read(name)
            for label, pattern in patterns.items():
                with self.subTest(file=name, check=label):
                    self.assertIsNone(re.search(pattern, text), f"{name} contains a {label}")

    def test_gitignore_protects_the_secrets(self):
        ignored = self.read(".gitignore")
        for entry in (".env", "token.json", "client_secret.json", "schedule.json", "settings.json", "venv/", "*.key"):
            self.assertIn(entry, ignored)
        self.assertIn("eol=lf", self.read(".gitattributes"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
