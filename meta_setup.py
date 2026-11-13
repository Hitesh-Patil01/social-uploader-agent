#!/usr/bin/env python3
"""
One-time helper for Facebook + Instagram setup.

It asks for three things (paste each one, then press Enter; the screen is cleared afterwards):
  1. App ID                       (Meta app -> Settings -> Basic)
  2. App Secret                   (same page, click "Show")
  3. Short-lived user token       (Tools -> Graph API Explorer -> Generate Access Token)

Then it:
  - exchanges the token for a long-lived one and lists your Facebook Pages,
  - saves the Page tokens into .env (the names come from settings.json),
  - saves the Page id and the Instagram ids into settings.json.

Tokens are never printed. Run:  python meta_setup.py
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")
GRAPH = "https://graph.facebook.com/" + os.getenv("GRAPH_VERSION", "v23.0")
ENV_FILE, SETTINGS_FILE = BASE / ".env", BASE / "settings.json"


def die(msg):
    sys.exit("\nERROR: " + msg)


def get(url, params=None):
    """GET that never leaks tokens in error messages."""
    try:
        r = requests.get(url, params=params, timeout=30)
    except requests.RequestException:
        die("Could not reach Facebook. Check your internet connection and try again.")
    if not r.ok:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        die(f"Facebook said no ({r.status_code}): {msg or 'unknown error'}")
    return r.json()


def soft_get(url, params=None):
    """GET that returns None instead of stopping when Facebook says no."""
    try:
        r = requests.get(url, params=params, timeout=30)
    except requests.RequestException:
        return None
    if not r.ok:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def pages_from_granted(user_token, app_id, app_secret):
    """Fallback for Facebook Login for Business: read which Pages the token was granted, then ask for each one.
    Returns (pages, scopes, page_ids). Only permission names and Page ids are collected, never secrets."""
    info = (soft_get(f"{GRAPH}/debug_token", {"input_token": user_token,
                                              "access_token": f"{app_id}|{app_secret}"}) or {}).get("data", {})
    scopes = info.get("scopes", [])
    ids = []
    for g in info.get("granular_scopes", []):
        if str(g.get("scope", "")).startswith("pages_"):
            ids += g.get("target_ids", [])
    ids = list(dict.fromkeys(ids))
    pages = []
    field_sets = ["id,name,access_token,instagram_business_account{id,username},connected_instagram_account{id,username}",
                  "id,name,access_token,instagram_business_account{id,username}",
                  "id,name,access_token"]
    for pid in ids:
        for fields in field_sets:  # try the richest request first; fall back if Facebook refuses a field
            d = soft_get(f"{GRAPH}/{pid}", {"fields": fields, "access_token": user_token})
            if d and d.get("access_token"):
                if not d.get("instagram_business_account") and d.get("connected_instagram_account"):
                    d["instagram_business_account"] = d["connected_instagram_account"]
                pages.append(d)
                break
    return pages, scopes, ids


def set_env(key, value):
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def choose(pages, question, default):
    while True:
        hint = f" [Enter = {default}]" if default else " [Enter = skip]"
        ans = input(f"{question}{hint}: ").strip()
        if not ans:
            return default
        if ans.isdigit() and 1 <= int(ans) <= len(pages):
            return int(ans)
        print("  Please type one of the numbers above.")


def main():
    if not ENV_FILE.exists():
        die("There is no .env file here. Run:  copy .env.example .env")
    s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))

    print(__doc__.split("Tokens are never printed")[0])
    # input() is used on purpose: pasting into a hidden prompt does not work in the Windows console.
    # The screen is cleared right after, so the pasted secret does not stay visible.
    app_id = input("App ID: ").strip()
    app_secret = input("App Secret (paste it, then press Enter): ").strip().strip("'\"")
    short = input("Short-lived user token (paste it, then press Enter): ").strip().strip("'\"")
    os.system("cls" if os.name == "nt" else "clear")
    if not (app_id and app_secret and short):
        die("All three values are needed.")

    # Pastes are hidden, so show only lengths and check the shapes to catch mix-ups.
    print(f"\nReceived: App ID {len(app_id)} digits, App Secret {len(app_secret)} characters, token {len(short)} characters")
    problems = []
    if not app_id.isdigit() or not 12 <= len(app_id) <= 20:
        problems.append("The App ID should be only digits (about 15 or 16 of them).")
    if app_secret.startswith("EAA") or len(app_secret) > 40:
        problems.append("What you pasted as the App Secret looks like the long token, not the secret. "
                        "The secret is exactly 32 characters (the letters a-f and numbers).")
    elif len(app_secret) != 32 or any(c not in "0123456789abcdefABCDEF" for c in app_secret):
        problems.append(f"The App Secret should be exactly 32 characters (letters a-f and numbers). I received {len(app_secret)}.")
    if not short.startswith("EAA") or len(short) < 60:
        problems.append("The token should start with EAA and be long (about 200 characters). "
                        "What you pasted as the token does not look right.")
    if problems:
        die("\n  ".join(problems) + "\n\nCopy the value again and run the helper again.")

    long_user = get(f"{GRAPH}/oauth/access_token", {
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": app_secret, "fb_exchange_token": short})["access_token"]

    pages, url, params = [], f"{GRAPH}/me/accounts", {
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "limit": 100, "access_token": long_user}
    while url:
        data = get(url, params)
        pages += data.get("data", [])
        url, params = data.get("paging", {}).get("next"), None
    if not pages:
        print("\nThe normal Page list was empty. Trying the second method ...")
        pages, scopes, ids = pages_from_granted(long_user, app_id, app_secret)
        if not pages:
            print(f"  Permissions on the token: {', '.join(scopes) if scopes else 'none found'}")
            print(f"  Page ids the token was granted: {', '.join(ids) if ids else 'none'}")
            die("No Facebook Pages found for this token. In the Graph API Explorer, click Generate Access Token again, "
                "choose \"Opt in to current Pages only\", and TICK your Page(s) before Continue.")

    print("\nPages found:")
    for i, p in enumerate(pages, 1):
        ig = p.get("instagram_business_account")
        print(f"  {i}. {p['name']}   Instagram: {'@' + ig['username'] if ig else 'not linked'}")

    fb, accounts = s["facebook"], s["instagram_accounts"]
    saved, env_page = [], {}

    def save_token(env_name, page):
        if env_name in env_page and env_page[env_name] != page["id"]:
            print(f"\nWARNING: {env_name} is used for two different Pages. The last one wins; "
                  "give each Page its own page_token_env in settings.json.")
        env_page[env_name] = page["id"]
        set_env(env_name, page["access_token"])
        if env_name not in saved:
            saved.append(env_name)

    print()
    d_fb = next((i for i, p in enumerate(pages, 1) if p["name"].lower() == fb["page_name"].lower()), None)
    n_fb = choose(pages, f"Number of the Facebook Page \"{fb['page_name']}\" (skip if you do not post to Facebook)", d_fb)
    if n_fb:
        save_token(fb["page_token_env"], pages[n_fb - 1])
        fb["page_id"] = pages[n_fb - 1]["id"]

    for acc in accounts:
        d = next((i for i, p in enumerate(pages, 1)
                  if (p.get("instagram_business_account") or {}).get("username", "").lower() == acc["name"].lower()), None)
        n = choose(pages, f"Number of the Page linked to Instagram @{acc['name']} (skip if not ready)", d)
        if not n:
            continue
        page = pages[n - 1]
        save_token(acc["page_token_env"], page)
        ig = page.get("instagram_business_account")
        if ig:
            acc["ig_user_id"] = ig["id"]
        else:
            print(f"\nNOTE: \"{page['name']}\" has no Instagram account linked, so @{acc['name']} is not set up yet.")

    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nDone. Saved (tokens are NOT shown):")
    print("  .env           " + (", ".join(saved) or "nothing"))
    print("  settings.json  facebook.page_id and the Instagram ids that were found")
    print("Next: python agent.py --check")


if __name__ == "__main__":
    main()
