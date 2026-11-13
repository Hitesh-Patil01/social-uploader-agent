"""
Title / caption handling (needs no internet).

You send ONE message with the title and the caption:
    first line = title, everything after it = caption
or labelled:   "Title: ..."  and  "Caption: ..."   (also "Tittle:", "शीर्षक (Title):", "कॅप्शन (Caption):", with or
without bold ** marks, with the text on the same line or on the lines below the heading)

The agent then adds your fixed @mention, hashtags and YouTube tags from settings.json and builds
the text for each platform:
    YouTube   : Title box = title | Description = caption + CTA + @mention + hashtags | Tags box = fixed tags
    Facebook  : title + caption + CTA + page mention + hashtags
    Instagram : title + caption + CTA + @mention + hashtags   (one text per Instagram account)

If you paste a full finished post (with the CTA line, @mention and hashtags at the end) it is fine:
trailing hashtags/mentions are removed and re-added in the right way, and the CTA line is only
added when it is missing.

Try it offline:   python captions.py             (built-in sample)
                  python captions.py post.txt    (your own UTF-8 text file)
"""
import json
import re
import sys
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent / "settings.json"

def _label_re(words):
    """A heading line: optional emoji/markdown in front, the label word, an optional translation in brackets
    ("शीर्षक (Title):") or after a slash, an optional colon or dash, then the text on the same line (may be empty)."""
    return re.compile(
        r"^[\W_]*(?:" + "|".join(words) + r")"
        r"(?:\s*\([^)]*\)|\s*[/|]\s*[^\s:：]+)?"
        r"\s*[*_]*\s*(?:[:：\-–]\s*[*_]*\s*(.*))?\s*$", re.I)


_TITLE = _label_re(["title", "tittle", "titel", "शीर्षक", "शिर्षक", "टायटल"])
_CAPTION = _label_re(["caption", "captions", "कॅप्शन", "कॅपशन", "कैप्शन"])
_HASHTAG_LINE = re.compile(r"^\s*(?:#\S+\s*)+$")
_MENTION_LINE = re.compile(r"^\s*@?[\w.]+\s*$")


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        sys.exit("settings.json was not found. Copy settings.example.json to settings.json and fill it in (see README).")
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"settings.json has a typo near line {e.lineno} (a missing quote or comma?). Fix it and try again.")


def parse_title_caption(text: str):
    """Split a pasted message into (title, caption). Raises ValueError with a friendly message."""
    text = (text or "").strip()
    lines = text.splitlines()
    t_idx = next((i for i, l in enumerate(lines) if _TITLE.match(l)), None)
    c_idx = next((i for i, l in enumerate(lines) if _CAPTION.match(l)), None)

    def part(idx, rx, stop):
        first = rx.match(lines[idx]).group(1) or ""
        return "\n".join([first] + lines[idx + 1:stop]).strip()

    if t_idx is not None and c_idx is not None:  # both labels
        if t_idx < c_idx:
            title, caption = part(t_idx, _TITLE, c_idx), part(c_idx, _CAPTION, len(lines))
        else:
            caption, title = part(c_idx, _CAPTION, t_idx), part(t_idx, _TITLE, len(lines))
    elif c_idx is not None:  # only "Caption:" -> the text above it is the title
        title, caption = " ".join(lines[:c_idx]), part(c_idx, _CAPTION, len(lines))
    elif t_idx is not None:  # only "Title:" -> the text below it is the caption
        title = _TITLE.match(lines[t_idx]).group(1) or ""
        caption = "\n".join(lines[t_idx + 1:]).strip()
        if not title:  # heading alone on its line: the next non-empty line is the title
            rest = [l for l in lines[t_idx + 1:]]
            k = next((i for i, l in enumerate(rest) if l.strip()), None)
            if k is not None:
                title, caption = rest[k], "\n".join(rest[k + 1:]).strip()
    else:  # no labels: first non-empty line = title, rest = caption
        i = next((k for k, l in enumerate(lines) if l.strip()), None)
        if i is None:
            raise ValueError("The message is empty. Send the title on the first line and the caption below it.")
        title, caption = lines[i].strip(), "\n".join(lines[i + 1:]).strip()

    title = " ".join(title.split())
    if not title:
        raise ValueError("I could not find the title. Put the title on the first line.")
    if not caption:
        raise ValueError("I found the title but no caption. Send the title on the first line and the caption below it.")
    return title, caption


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\ufe0f", "")).strip()


def clean_caption(caption: str, known_mentions) -> str:
    """Drop trailing hashtag lines and our own @mention line, so they are not added twice."""
    known = {m.lower().lstrip("@") for m in known_mentions}
    lines = caption.rstrip().splitlines()
    while lines:
        last = lines[-1].strip()
        if not last or _HASHTAG_LINE.match(last):
            lines.pop()
        elif _MENTION_LINE.match(last) and last.lower().lstrip("@") in known:
            lines.pop()
        else:
            break
    return "\n".join(lines).strip()


def _block(*parts) -> str:
    return "\n\n".join(p for p in parts if p)


def build_posts(title: str, caption: str, settings: dict | None = None) -> dict:
    s = settings or load_settings()
    yt, fb, accounts = s["youtube"], s["facebook"], s["instagram_accounts"]
    mentions = [yt["mention"], fb["mention"]] + [a["mention"] for a in accounts]

    body = clean_caption(caption, mentions)
    cta = s.get("fixed_text", {}).get("cta", "")
    if cta and s.get("append_cta_if_missing", True) and _norm(cta) not in _norm(body):
        body = _block(body, cta)

    warnings = []
    if len(title) > 100:
        warnings.append(f"The title is {len(title)} characters; YouTube allows 100, so it will be cut.")

    def yt_safe(t):  # YouTube rejects < and > in titles/descriptions
        return t.replace("<", "").replace(">", "")

    return {
        "youtube": {
            "title": yt_safe(title)[:100],
            "description": yt_safe(_block(body, yt["mention"], " ".join(yt["hashtags"]))),
            "tags": yt["tags"],
        },
        "facebook": {"message": _block(title, body, fb["mention"], " ".join(fb["hashtags"]))},
        "instagram": {a["name"]: _block(title, body, a["mention"], " ".join(a["hashtags"])) for a in accounts},
        "warnings": warnings,
    }


SAMPLE = """My first video title 🌟

This is the caption of the video.
It can have many lines.

❤️ Please share and follow! 🔔

#example #sample"""


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    raw = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else SAMPLE
    title, caption = parse_title_caption(raw)
    posts = build_posts(title, caption)
    print(f"PARSED TITLE:\n{title}\n")
    for name, text in posts["instagram"].items():
        print(f"===== INSTAGRAM @{name} =====\n{text}\n")
    print(f"===== FACEBOOK =====\n{posts['facebook']['message']}\n")
    print(f"===== YOUTUBE =====\nTITLE: {posts['youtube']['title']}\n\nDESCRIPTION:\n{posts['youtube']['description']}\n")
    print("TAGS:", ", ".join(posts["youtube"]["tags"]))
    for w in posts["warnings"]:
        print("WARNING:", w)
