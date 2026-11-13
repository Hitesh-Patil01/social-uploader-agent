# Social Uploader Agent

**Version 1.1.0**

Post one video to **YouTube, Facebook and Instagram** from your phone. You send the video, and the agent asks you
(on Telegram) where it should go, takes your title and caption, adds your fixed mention, hashtags and tags, then uploads and
schedules it on the platforms you chose. It uses the official APIs with tokens, so it never asks for your account
passwords, and it runs entirely on free tiers.

Different videos can go to different places: one video to only Instagram @account_one, the next to YouTube and Facebook, and so on.
Nothing is posted anywhere you did not choose.

> **Disclaimer.** This is a personal project, shared as it is under the MIT License (see the `LICENSE` file). It comes with no warranty and no support. Use it at your own risk and only with accounts you own.
> It is not affiliated with or endorsed by Google, YouTube, Meta, Facebook, Instagram, Telegram, Oracle or Cloudflare. Their rules and APIs change, and they can limit or close an account, so read their terms before you use it.
> You must create your own Telegram bot, Google project, Meta app and server. Nothing here gives you access to anyone else's accounts.

You can run it in either of two ways:

| | **Track A: Windows PC** | **Track B: free Oracle Cloud server** |
|---|---|---|
| Cost | Free | Free (needs a credit card that works abroad, and some rules: **read section 9.0 first**) |
| PC must stay on | Yes, for Instagram post times and while you answer | **No**. Your PC can be off |
| Setup time | About 2 to 3 hours (mostly the Meta/Instagram part) | Track A's setup plus about 1.5 hours |
| Best for | Trying it out, or posting at times when your PC is on anyway | Hands-off, always-on posting |

Both tracks share the same setup first (Parts 1 to 5). Then you pick Track A or Track B.

## Quick start

**You need:** a YouTube channel, a Facebook Page and/or an Instagram Creator or Business account linked to a Page, a Telegram account, a Google account, and a computer with Python 3.10 or newer (Windows commands are used in the guide). For an always-on server you also need a card that works abroad (read section 9.0 first).

1. **Install the tools and get the files** (section 3): Python, ffmpeg, cloudflared, then `pip install -r requirements.txt`.
2. **Fill in your settings** (section 4): copy `settings.example.json` to `settings.json` and put in your handles, hashtags, tags and usual times.
3. **Make a Telegram bot** with @BotFather and put its token in `.env` (section 5).
4. **Connect YouTube** (section 6): a Google Cloud project, then `python agent.py --auth`.
5. **Connect Facebook and Instagram** (section 7): a Meta app, then `python meta_setup.py`.
6. **Check everything:** `python agent.py --check` and `python tests/test_project.py`.
7. **Run it** on your PC with `run_agent.bat` (section 8), or on a free server (section 9).
8. **Post:** put a video in the inbox folder (or your Google Drive folder). The bot asks where to post it. Answer with the places, then your title and caption, then `ok` (section 10).

**What happens after `ok`:** YouTube uploads the video as private and turns it public at your time. Facebook schedules it. Instagram has no scheduler for programs, so the agent itself publishes at your time, which means **the agent must be running then**. Allow a few minutes for each video.

**Good to know:** the first setup takes a few hours, mostly the Meta and Instagram part. Test with a short video that you can delete. Section 15 says what has been tested live and what the limits are.

---

## Contents
1. [How it works](#1-how-it-works)
2. [What you need](#2-what-you-need)
3. [Part 1: Install the tools and get the files](#3-part-1-install-the-tools-and-get-the-files)
4. [Part 2: Your settings](#4-part-2-your-settings-settingsjson)
5. [Part 3: Telegram bot](#5-part-3-telegram-bot)
6. [Part 4: YouTube](#6-part-4-youtube)
7. [Part 5: Facebook and Instagram](#7-part-5-facebook-and-instagram)
8. [Track A: run it on a Windows PC](#8-track-a-run-it-on-a-windows-pc)
9. [Track B: run it on a free Oracle Cloud server](#9-track-b-run-it-on-a-free-oracle-cloud-server)
10. [Daily use](#10-daily-use)
11. [Settings and environment reference](#11-settings-and-environment-reference)
12. [Security and credentials](#12-security-and-credentials)
13. [Maintenance](#13-maintenance)
14. [Troubleshooting](#14-troubleshooting)
15. [Honest status and limits](#15-honest-status-and-limits)
16. [Project files, tests and git](#16-project-files-tests-and-git)
17. [Command cheat sheet](#17-command-cheat-sheet)

---

## 1. How it works

```
 Your phone                       The agent (PC or server)                  Platforms
 ----------                       ------------------------                  ---------
 1. Save a video  ------------->  2. Sees the video
    (inbox folder or                 asks on Telegram: "Where to post?"
     Google Drive folder)
 3. Answer on Telegram  -------->  4. Takes your title + caption,
    "yt fb", the text, "ok"           adds mention, hashtags, tags
                                  5. Uploads / schedules   ------------->   YouTube   (Google schedules it)
                                                                           Facebook  (Facebook schedules it)
                                     Holds the Instagram schedule  ----->   Instagram (the agent publishes at the time)
 6. Telegram: links and results <-
```

**Who holds each schedule**

| Platform | What the agent does | Who publishes at the set time |
|---|---|---|
| YouTube | Uploads as private and sets a publish time, adds it to your playlist | Google |
| Facebook Page | Uploads and schedules with Facebook's own scheduler | Facebook |
| Instagram | Prepares the video and **waits** | **The agent itself**, so it must be running at that time |

Instagram has no scheduler that a program can use (only Instagram's own app has one). That is why the agent must be running at
Instagram post times. It is also the reason Track B exists.

**How Instagram scheduling works**

Instagram's own scheduler exists only inside Instagram's and Meta's apps. A program like this cannot use it, so **the agent holds the post itself and publishes it at the time you chose.**
1. After you reply `ok`, the post is saved in a queue file, `schedule.json`, next to `agent.py`. It is not kept in Instagram, and it survives restarts and reboots.
2. About 20 hours before the post time, the agent prepares the video: it opens a temporary free link (cloudflared) so Instagram can fetch the file, and Telegram says "ready and will post at ...".
   It waits until then because Instagram only keeps a prepared video for 24 hours.
3. At the exact time the agent publishes it and sends "posted" with the link. The video then moves to the `done` folder.
4. **The agent must be running at those times.** On a server it always is. In Track A your PC must be on and awake.
5. If the agent was off at the time, it publishes late once it is running again, as long as that is within about a day. After that, Instagram has dropped the prepared video, you get an error message in Telegram, and you send the video again.
6. `/status` shows the Instagram posts that are waiting, and `/jobs` lists them with numbers. Remove one with `/cancel 1`, several with `/cancel 1 2`, or all with `/cancel all`.
   This removes **Instagram posts only**. YouTube and Facebook posts are held by Google and Facebook, so delete those in YouTube Studio and Meta Business Suite.
   (If the agent will not start, you can also stop it, delete that post's block in `schedule.json`, and start it again.)

YouTube and Facebook are different: Google and Facebook hold their own schedules, so those posts go out even if the agent is off at that time.

**What is automatic and what is still manual**

| Automatic | Still manual |
|---|---|
| Title, description, mention, hashtags, tags | Hiding likes/shares on Instagram |
| Cover picture (frame at 7 seconds) for Facebook and Instagram | The AI-content label on Facebook and Instagram |
| Date and time on every platform | |
| YouTube: private first, public at your time, added to a playlist, AI flag | |

---

## 2. What you need

- A **YouTube channel**.
- A **Facebook Page** that you are the admin of (a Page, not a personal profile).
- An **Instagram Creator or Business account**, linked to a Facebook Page. **Each Instagram account needs its own Page.**
- A **Telegram** account (on your phone).
- A **Google account** (the one that owns the channel; also used for Google Drive).
- A **Facebook account** that manages those Pages. It is also used to register as a Meta developer (free).
- A **Windows PC** (or Linux/macOS) for the setup. Windows commands are used in this guide.
- For Track B only: an **Oracle Cloud** account and a **Visa or Mastercard credit card** for verification.

Nothing here costs money. The only payment step is the card check when you sign up for Oracle (Track B).

---

## 3. Part 1: Install the tools and get the files

### Put the files in a folder
Make a folder, for example `C:\social-uploader`. **Do not** put it inside OneDrive, Google Drive or Dropbox, because it will hold
secret keys. Copy the project files into it, all in the same folder:
`agent.py`, `captions.py`, `meta_setup.py`, `requirements.txt`, `settings.example.json`, `.env.example`, `run_agent.bat`,
`deploy_to_server.bat`, and the `server` folder (with `setup_server.sh`, `social-uploader.service`, `sync_inbox.sh`).

### Install the programs (Windows, in cmd)
```
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install Cloudflare.cloudflared
```
**Close cmd and open a new one**, because Windows only finds new programs in a new window. Then check:
```
python --version
ffmpeg -version
cloudflared --version
```
If `python` opens the Microsoft Store or says "Python was not found", install Python from python.org (tick **Add python.exe to PATH**),
then press the Windows key, type **Manage app execution aliases**, and turn off `python.exe` and `python3.exe`.

### Set up the project
```
cd /d C:\social-uploader
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
copy settings.example.json settings.json
```
After `activate`, the prompt starts with `(venv)`. **Every time you open a new cmd window, run these two lines again before using the agent:**
```
cd /d C:\social-uploader
venv\Scripts\activate
```
(Linux/macOS: `python3 -m venv venv`, `source venv/bin/activate`, `cp` instead of `copy`, `nano` instead of Notepad.)

Check the version and what is missing at any time:
```
python agent.py --version
python agent.py --check
```
At this stage, `--check` lists MISSING for several things. That is your to-do list for the next parts.

---

## 4. Part 2: Your settings (`settings.json`)

Open it in Notepad (`notepad settings.json`) and replace every example value with your own. Every field is explained in
[section 11](#11-settings-and-environment-reference). The ones to change first:

- `youtube.channel_handle`, `youtube.mention`: your channel handle, such as `@mychannel`.
- `youtube.hashtags`, `youtube.tags`, `facebook.hashtags` and each Instagram account's `hashtags`: your fixed lists.
- `facebook.page_name` and `facebook.mention`: the exact name of your Facebook Page.
- `instagram_accounts`: one block per Instagram account (`name` without @, `mention` with @, `publish_time`). Delete the second
  block if you have one account, or copy a block (with a new `page_token_env`, such as `META_PAGE_TOKEN_3`) for more.
- `fixed_text.cta`: a line added to every post, for example "Please share and follow". Use `""` for none.
- Leave `ig_user_id` and `page_id` empty. `meta_setup.py` fills them in.

**JSON rules:** keep the quotation marks and commas exactly as in the example. Each line ends with a comma except the last one in a group.
Marathi, Hindi and emoji are fine. If the file has a typo, the agent says which line.

Test it. This needs no internet:
```
python captions.py
```
It shows how a sample post will look on every platform. You can also test your own text: `python captions.py mypost.txt`.

---

## 5. Part 3: Telegram bot

Telegram is how you control everything.

1. Install **Telegram** on your phone. (On the PC you can use web.telegram.org.)
2. In Telegram, search for **@BotFather** (blue tick) and send `/newbot`. Choose a name, then a username that ends in `bot`.
3. BotFather sends you a **token**: digits, a colon, then a secret (`123456789:AAH…`). **Keep it secret. Never paste it into a chat,
   email or screenshot.** If it leaks, send `/revoke` to BotFather and choose your bot to get a new one.
4. Put it in `.env`:
   ```
   notepad .env
   ```
   Write values right after the `=`, with no spaces and no quotes:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   PLATFORMS=youtube
   ```
   (`PLATFORMS` uses the full words `youtube`, `facebook`, `instagram`, separated by commas. Switch platforms on one at a time while
   you set them up.) Save with Ctrl+S. When saving in Notepad, make sure the file is not renamed to `.env.txt`.
5. In Telegram, open **your bot**, press **Start**, and send `hi`.
6. Find your chat id:
   ```
   python agent.py --chatid
   ```
   Put the number in `.env` as `TELEGRAM_CHAT_ID=...`.
7. Check:
   ```
   python agent.py --check
   ```
   The Telegram lines must say OK, including "Telegram accepts the token".

The agent only obeys messages from your own chat id.

---

## 6. Part 4: YouTube

Google changes menu names sometimes. Use the nearest option if something looks different.

**A. Get the key file**
1. Go to **console.cloud.google.com** and sign in with the Google account that **owns your YouTube channel**. Use the default
   project or create one.
2. Search **YouTube Data API v3**, open it, and click **Enable**.
3. Search **Google Auth Platform** and click **Get started**: app name, your email, audience **External**, your email again,
   agree, **Create**.
4. Open **Audience** and add **your own Gmail** under **Test users**.
5. Open **Clients → Create client**, choose **Desktop app**, and click **Create**. Click **Download JSON**.
6. Rename the file to exactly `client_secret.json` and put it in the project folder. (Turn on File Explorer's *File name
   extensions* so it does not become `client_secret.json.json`.)

**B. Log in once**
```
python agent.py --auth
```
Your browser opens. Choose your account (and your channel if asked). **"Google hasn't verified this app"** is normal for your own app:
click **Continue** (or **Advanced → Go to … (unsafe)**) and allow the permissions. `token.json` is created.
Then `python agent.py --check` must show the YouTube login as OK.

**C. Stop the login from expiring.** In **Google Auth Platform → Audience**, if the status is **Testing**, click **Publish app**. In Testing
mode the login stops working after 7 days. After publishing, delete `token.json` and run `python agent.py --auth` once more.

**Google needs two web pages before you can publish the app.** The Branding page asks for a home page and a privacy policy link on a domain you own. A free way is **GitHub Pages**:
create a **public** repository named `YOUR_GITHUB_USERNAME.github.io`, upload the two templates from `docs/privacy-site-templates/` (replace every `YOUR_...` placeholder with your own details, and do not add a logo),
then turn on **Settings → Pages → Deploy from a branch → main → / (root)**. On Google's Branding page use `https://YOUR_GITHUB_USERNAME.github.io/` as the home page, the same address with `privacy.html` as the privacy policy,
and `YOUR_GITHUB_USERNAME.github.io` as the authorized domain. As far as we know, Google's verification process is not needed when you are the only user.

**D. Test** (see [section 10](#10-daily-use) for how to send a video). Send a short vertical video to `yt` only, with the time a day ahead.
In **studio.youtube.com → Content** check that **Visibility says Scheduled**, the title, description, tags and playlist are right,
then delete the test video.

> If Visibility shows plain *Private* with no schedule, Google may be holding uploads from an unaudited project as private.
> Publish by hand in Studio, or apply for Google's API audit.

---

## 7. Part 5: Facebook and Instagram

This is the longest part. Do it in order, and test after each step.

### 7.1 Link each Instagram account to its own Facebook Page
1. In the Instagram app, switch to the account, then **Settings and activity → Account type and tools**. It must be a **Professional** account
   (Creator or Business). If not, switch it.
2. Link the Page: **Edit profile → Public business information → Page → Connect existing Page** (or create a new Page there). Log in to
   Facebook with the account that manages the Page.
3. Each Instagram account needs **its own Page**, and a Page links to only one Instagram account.
4. **Turn off automatic sharing to Facebook** in the Instagram app for each account (**Settings and activity → Sharing to other apps**, or the sharing settings in Accounts Center). In the author's test, Instagram copied each Reel to the linked Page until this was switched off, and if you also post to `fb` the same video appears twice. Reels are not
   copied to the Page. After your first Instagram test, check the Page for a copy.

**If linking shows "Something went wrong"** (it can happen repeatedly):
- Stop retrying. Look at **Edit profile → Page** in the Instagram app for an orange **Confirm** button, which means a link is waiting.
- Try the other routes: from the Page on Facebook, **Settings → Linked accounts → Instagram → Connect account**, or Meta Business Suite
  (**Settings → Business assets → Add assets → Instagram account**). Use an Incognito window in Edge or Firefox, and allow pop-ups.
- If the dialog asks to create a *business portfolio*, that is normal. It groups the Page and Instagram profile.
- In the Instagram app, choose **Create new Facebook Page** instead of connecting an old auto-made one.
- If it still fails, wait a day and try again from the phone app, or report it with **Help → Report a problem**. Other accounts can be set up meanwhile.

> Linked accounts can share fate: a serious violation on one can affect the other. Keep each Instagram account linked to only its own Page,
> avoid linking more accounts in Accounts Center than you need, add a **backup admin** to each Page (**Settings → Page access**), and turn on two-factor authentication.

### 7.2 Create the Meta app
1. Go to **developers.facebook.com** with the **Facebook account that manages the Pages**, click **Get Started**, and finish the free
   developer registration (choose **Developer** when asked). *Use the right account: if it does not manage the Pages, the Page list in
   the login popup will say "You don't have any Pages".*
2. **My Apps → Create App**. Name it `social-uploader`. On the use-case screen, choose the filter **Others**, scroll to the bottom and select
   **Other** ("Looking for something else?"), then app type **Business**, then **Create app**. (Meta says the "Other" option is going away. If
   it has gone, the **Content management** use case "Manage everything on your Page" is the closest replacement. It is untested here.)
3. On the dashboard, under **Products → Add Product**, scroll to the end and **Set up** **Facebook Login for Business**.
4. Open **Facebook Login for Business → Configurations → Create configuration**:
   - Name: `uploader`, login variation: General, access token: **User access token**.
   - Permissions: `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`.
5. Open **App settings → Basic** and copy the **App ID**. Click **Show** next to **App Secret** (32 characters of letters a-f and numbers).

### 7.3 Make a token and run the helper
1. Open **Tools → Graph API Explorer**, press F5, and set **Meta App** to `social-uploader`. Choose **Get User Access Token**, open the **Configurations** tab
   and pick `uploader`. Click **Generate Access Token**.
2. In the popup choose **Opt in to current Pages only** and tick your Pages. On the next screen choose **Opt in to current Instagram accounts only** and
   tick your Instagram accounts. Click **Continue** and **Save**. Copy the token (about 240 to 290 characters, starting with `EAA`).
3. Run the helper right away, because the token lasts about an hour:
   ```
   python meta_setup.py
   ```
   Enter the App ID, then paste the App Secret and the token (right-click to paste in cmd). Do not take screenshots here: the values are
   visible until the screen clears. It prints how many characters it received (the secret must be 32), lists your Pages with their Instagram
   accounts, and asks which Page is which. Press **Enter** to accept each suggestion.
4. It saves the Page tokens in `.env` and the Page and Instagram ids in `settings.json`. If a Page shows *"Instagram: not linked"*, the Instagram account was
   not ticked in the popup, or the link in 7.1 is not complete.

The normal Page list can be empty with this login type. The helper then uses a second method automatically. This is expected.

### 7.4 Switch the platforms on and test
Switch on one platform at a time in `.env`, and run `python agent.py --check` each time:
```
PLATFORMS=youtube,facebook
```
- **Facebook:** send a short video to `fb`, then in **Meta Business Suite → Planner** check the text, the time and the cover. Delete the test post.
  (The page mention appears as plain text, not a blue tag.)
- **Instagram:** use a real video (it goes public the moment it publishes). Vertical 9:16, MP4, H.264/AAC, **90 seconds or less**. Reply `ig1`, set a time
  15 to 20 minutes ahead, and watch for "posted" (allow a few minutes: about 3 to 5 minutes for a 30 to 45 second Reel in the author's tests). Check the Reel, its cover, and the Page for an unwanted copy; if there is one, switch off the automatic share (7.1, point 4) and delete the copy.

To test one Instagram account at a time, add `IG_ACCOUNTS=your_instagram_handle` to `.env`. Remove the line when all accounts work.
Finally set `PLATFORMS=youtube,facebook,instagram`.

Now choose Track A or Track B.

---

## 8. Track A: run it on a Windows PC

1. Start the agent:
   ```
   run_agent.bat
   ```
   It starts the agent and restarts it if it stops or crashes. Keep the window open. (You can also run `python agent.py`.) Telegram says the agent is running.
2. **Start it automatically.** Press **Windows + R**, type `shell:startup`, and put a shortcut to `run_agent.bat` there. Or use Task Scheduler:
   **Create Task**, trigger **At log on** (delay 30 seconds), action **Start a program** `run_agent.bat` with **Start in** set to the project folder,
   untick "Stop the task if it runs longer than". Choose **Run only when user is logged on**. Use only one of the two.
3. **Keep the PC awake.** Settings → System → Power: set **Sleep** to **Never** while plugged in. On a laptop, set closing the lid to **Do nothing**.
   Stay signed in to Windows. Locking the screen is fine.
4. **Videos from your phone (optional).** Install **Google Drive for desktop** (or OneDrive), make a folder in it, and set it in `.env`, for example
   `INBOX_DIR=C:\Users\YourName\Google Drive\social-inbox`. Use **Mirror files** (Drive) or **Always keep on this device** (OneDrive). Otherwise
   just copy videos into the `inbox` folder.

The PC must be on and awake at every Instagram post time. YouTube and Facebook schedule themselves, but the upload happens when you answer `ok`.

---

## 9. Track B: run it on a free Oracle Cloud server

Do Parts 1 to 5 on your PC first, so the agent works there. The server then runs the same files all the time.

### 9.0 Read this first: rules that keep your Oracle account alive
Free cloud accounts are generous but strict. These rules come from a real problem: the author's first Oracle account was closed by Oracle's automated checks within about two weeks of setting it up. No reason was given, and support could only raise an internal appeal. We cannot prove what caused it, and Oracle can change its rules at any time. Follow these rules anyway. They cost nothing.

**Before you sign up**
1. **One account per person, with your real details.** Oracle's Free Trial and Free Tier are for first-time Oracle Cloud users, and creating or trying to create more than one free account is not allowed. Use your own name, address, phone number and email. Do not use a VPN, someone else's details, or a second email address to get around this.
2. **Use a Visa or Mastercard credit card, and switch on "International online" payments before you sign up.** Oracle bills as a foreign company. Many Indian banks switch international online use off by default, so check the card settings in your bank's app.
3. **Keep international payments on afterwards.** Oracle may try small payments later (a verification of about 1 US dollar, or a bill), even on a free account. If your bank refuses, Oracle records a failed payment. If you worry about big charges, set a **small per-transaction limit** in the bank's app instead of switching international use off. In the author's case, a small Oracle payment was declined with the message "International online usage disabled", and within days the console sign-in failed and the server stopped answering. We cannot prove the two are connected, so do not take the chance.
4. **Do not remove, replace or cancel the card on the account, and do not let it expire.** Keep it under **Billing & Cost Management → Payment methods**. If your bank reissues the card, add the new one before the old one stops working. Keep the bank's SMS and email alerts on.
5. **Use an email address you read every day, and check its spam folder.** Oracle's notices (such as "Action recommended") arrive there. Allow mail from `oracle.com` and `oraclecloud.com`. Write down your **Cloud Account Name**, user name and password in a password manager.
6. **Sign up from your home connection**, in the same country as your card and phone number.
7. **Choose the home region carefully.** It cannot be changed, and Always Free resources only work there. For India, choose **India West (Mumbai)**. After signup, check it: profile icon → **Tenancy** → **Home region** (Mumbai shows as `BOM`).

**While you use the account**
8. **Stay inside the Always Free limits:** one `VM.Standard.E2.1.Micro` server (or the Arm `A1` shape), boot and block volumes together at or below 200 GB (the default boot volume is about 47 GB), no block volumes, no extra reserved IP addresses, no load balancers, and nothing in other regions. Look for the **"Always Free-eligible"** badge when you choose the shape. **Governance & Administration → Tenancy Explorer** lists everything in the account.
9. **Do not upgrade to Pay As You Go** unless you accept paid billing. As far as we know, a Free Tier account that was never upgraded cannot be billed by accident.
10. **Keep the server from looking idle.** Oracle can stop or reclaim an Always Free server if its CPU, memory and network use all stay below about 20% for 7 days in a row (the exact figures can change). This agent is very light, so add the keep-alive job in section 9.6, and look at the **Monitoring** graph after a few days. It is not a guarantee.
11. **Set a budget alert** (**Billing & Cost Management → Budgets**, a very small amount, an email at 100%) and look at **Cost Analysis** the day after you create the server. The cost shown when you create the instance (for example about 2.76 US dollars a month for the boot volume) is a list price. As far as we know, that estimate does not apply the free allowance.
12. **Read every Oracle email**, in the inbox and in spam. Never click a link in a message you did not expect. Go to cloud.oracle.com yourself.
13. **Sign in to the console at least once a month** and check the server says **Running**. Oracle says a free account stays active as long as it has been used within the past 60 days.
14. **Do not run anything that looks like abuse:** proxies, VPNs, crypto mining, scanning tools or heavy outgoing traffic. The Instagram step in this project uses a short-lived Cloudflare tunnel to hand each video to Instagram. It is small and brief, and Oracle gave no reason for the author's closure, so we cannot say whether it mattered. If you want to avoid it, run the agent on a PC or a home machine (section 8).
15. **Keep every secret and file on your own computer, not only on the server.** Back up `.env`, `settings.json`, `token.json`, `rclone.conf` and your SSH key somewhere private, and keep the PC agent (Track A) ready as a fallback. Treat the free server as replaceable.

**If something goes wrong**
16. Signs of trouble: the console says "Invalid username or password" even after a reset, SSH times out, and the bot stops answering `/status`. Do not keep guessing passwords. Use **Forgot Password?** on the cloud sign-in page once, search your email for Oracle messages, and read section 9.13.
17. **Do not open another free account to get around a closure.** Oracle allows one per person, and its support told the author that a different email address does not make you eligible. Ask Oracle in writing first, and wait for a clear yes.

### 9.1 Honest notes first
- **Card:** Oracle verifies you with a **Visa or Mastercard credit card**. Prepaid, virtual and some Indian cards (for example RuPay) are often refused. A small hold
  is made and refunded. Always Free servers are not billed. **Read section 9.0 before you sign up.**
- **Idle servers can be stopped.** If CPU, memory and network use all stay below about 20% for 7 days, Oracle may stop or reclaim a free server (the exact figures can change).
  Add the keep-alive job in section 9.6. Upgrading to Pay As You Go is optional, costs real money if you use paid resources, and is not needed for this.
- **Capacity:** the ARM shape can be "out of capacity". The small AMD shape used here is almost always available.
- Oracle can reject or stall some sign-ups. If so, use its sign-up support form and do not create several accounts.
- Keep copies of `.env`, `settings.json` and `token.json` on your PC, so you can rebuild the server in about an hour.

### 9.2 Create the Oracle account
Use a normal home connection (no VPN), a real email, and a card with international payments switched on.
1. Go to **oracle.com/cloud/free** and click **Start for free**. Choose your country, enter your details and verify your email.
2. Set a password and a **Cloud Account Name** (write it down: it is your sign-in name).
3. Choose a **home region** near you (for India: **India West (Mumbai)**). **It cannot be changed later.**
4. Verify your phone, add the card and submit. Wait for the "account ready" email (minutes, sometimes an hour). Until then, some pages say
   "provisioning is in progress".
5. Sign in at **cloud.oracle.com**. The banner "Free Tier account … limited to Always Free resources" is only information.
6. Check the home region (profile icon → **Tenancy** → **Home region**; Mumbai shows as `BOM`). Then set **Billing & Cost Management → Budgets → Create Budget** with a very small
   amount and an email alert at 100% of actual spend. **Do not upgrade to Pay As You Go.**

### 9.3 Create the network and the server
1. **Network first.** Menu → **Networking → Virtual cloud networks → Actions → Start VCN Wizard → Create VCN with Internet Connectivity**. Name it `main-vcn`, leave
   the defaults, **Next**, **Create**. This makes a **public subnet** with internet access and default rules that allow SSH. (Do not click the plain **Create VCN** button. The wizard makes a public and a private subnet; always choose the **public** one for the server.)
2. **Make your SSH key** on your PC (cmd). Press Enter twice for no passphrase:
   ```
   mkdir C:\keys
   ssh-keygen -t ed25519 -f C:\keys\oracle.key -C "oracle"
   type C:\keys\oracle.key.pub
   ```
   `oracle.key` is the **private** key. Keep it secret. `oracle.key.pub` is the **public** key (one line starting with `ssh-ed25519`), which Oracle needs.
3. Menu → **Compute → Instances → Create instance**:
   - Name `social-uploader`.
   - **Image: Canonical Ubuntu 22.04.** (Not Oracle Linux: the scripts are for Ubuntu.)
   - **Shape:** click **Change shape**. The first list shows only paid shapes (E4, E5): do not pick them. Open the card **Specialty and previous generation** and pick
     **VM.Standard.E2.1.Micro**, marked **Always Free-eligible** (1 GB memory). The badge is shown on the shape screen, not on the Review page. The Arm shape `VM.Standard.A1.Flex`
     (under Ampere) with 1 OCPU and 6 GB is the alternative if available; the agent has not been tested on Arm.
   - **Networking:** select the existing network `main-vcn` and the **public** subnet. Turn on **Automatically assign public IPv4 address**. (If that switch is greyed out,
     the subnet is not a public one.)
   - **Add SSH keys → Paste public keys:** paste the line from `oracle.key.pub`. **Never choose "No SSH keys".**
   - **Storage:** leave the default boot volume size (about 47 GB) and do not attach block volumes.
   - On the **Review** page check: Ubuntu 22.04, the shape, **Public IPv4 address: Yes**, the public subnet and your key. **View estimated cost** lists only the boot volume at a list price;
     that is expected (see section 9.0, point 11). Click **Create**. Do not click any **Upgrade** button.
4. Wait for **Running**, then copy the **Public IP address** from the instance page. The user name is `ubuntu`. (The server prompt may show the network's name, such as `ubuntu@main-vcn`. That is only a label.)

### 9.4 Connect from your PC
Fix the key file's permissions first, because Windows refuses a key that others can read:
```
icacls "C:\keys\oracle.key" /inheritance:r
icacls "C:\keys\oracle.key" /grant:r "%USERNAME%:R"
```
> If ssh still says *UNPROTECTED PRIVATE KEY FILE* and your Windows user name equals your computer name, the second command granted access to the computer, not to you.
> Run `whoami /user`, copy your full ID (it ends with an extra number), then run
> `icacls "C:\keys\oracle.key" /remove "*S-1-5-21-…(the long number in the error)"` and
> `icacls "C:\keys\oracle.key" /grant:r "*YOUR_FULL_ID:R"`. Check with `icacls "C:\keys\oracle.key"`: only you should be listed.

Connect:
```
ssh -o ServerAliveInterval=30 -i C:\keys\oracle.key ubuntu@YOUR_SERVER_IP
```
Answer `yes` the first time. The prompt becomes `ubuntu@social-uploader:~$`. **From then on, commands typed in that window run on the server.** Create the folder:
```
mkdir -p ~/social-uploader
```
Use a **second cmd window** on your PC for uploads. (If Ctrl+V does not paste in the server window, right-click once or press Shift+Insert, or use PowerShell.)

### 9.5 Upload the project (PC window)
```
cd /d C:\social-uploader
scp -i C:\keys\oracle.key agent.py captions.py meta_setup.py settings.json requirements.txt .env token.json ubuntu@YOUR_SERVER_IP:~/social-uploader/
scp -i C:\keys\oracle.key -r server ubuntu@YOUR_SERVER_IP:~/social-uploader/
```
- Do not copy `schedule.json`, the `venv` folder or videos.
- Wait until every Instagram post still waiting on the PC has been published, because its saved file paths point to the PC.
- In the server's `.env`, `INBOX_DIR=` must be empty (a Windows path does not exist on the server). Edit with `nano ~/social-uploader/.env`
  (save with Ctrl+O, Enter; leave with Ctrl+X).

### 9.6 Run the setup script (server window)
```
bash ~/social-uploader/server/setup_server.sh
```
(Type `bash` first. The file is not marked as runnable. If it complains about `\r`, run `sed -i 's/\r$//' ~/social-uploader/server/*.sh`.)
It installs Python, ffmpeg, cloudflared and rclone, adds swap on small servers, builds the environment, installs the background service (starts at boot, restarts after a crash),
runs the check and starts the agent. If a purple screen about restarting services appears, press Enter.

**Keep-alive job (do this once, right after the setup).** It stops the server from looking idle (section 9.0, point 10). In the **server** window, type these four lines one at a time
(copy and right-click to paste, do not retype):
```
crontab -l > /tmp/cron.txt
echo '@hourly timeout 240 nice -n 19 yes >/dev/null 2>&1' >> /tmp/cron.txt
crontab /tmp/cron.txt
crontab -l
```
The last line must show two lines: the Drive sync (`... sync_inbox.sh`, once section 9.8 is done) and the keep-alive (`@hourly ... /dev/null 2>&1`). Check that `/dev/null` is spelled with two `l`s.
The job runs a light 4-minute load at the lowest priority once an hour. Re-running the setup script keeps it. A few days later, open **Compute → Instances → your instance → Monitoring**
and look at the CPU graph. If it never rises above 20%, run the job more often (for example `*/30 * * * *` instead of `@hourly`).

### 9.7 Hand over from the PC to the server
1. **Stop the PC agent by closing its window.** Do not send `/stop` for this: `/stop` goes to whichever agent is reading the bot, which could be the server one.
2. Remove the PC agent's automatic start (the Startup shortcut or the Task Scheduler entry). Two agents at once answer every message twice.
3. Send `/status` to your bot. It must answer from the server.

### 9.8 Send videos from your phone with Google Drive
The server checks a Drive folder every minute and moves new videos into the agent's inbox. You log in once, on your PC.
1. In Google Drive, create a folder in My Drive called exactly `social-inbox`.
2. **Create your own Google client ID.** rclone's shared one is being retired in 2026. In the same Google Cloud project as YouTube: enable **Google Drive API**, then
   **Google Auth Platform → Clients → Create client → Desktop app** (name `rclone`) and keep the **Client ID** and **Client secret**.
   Check **Audience**: if it says Testing, click **Publish app**.
3. Install rclone on your PC: `winget install Rclone.Rclone` (then open a new cmd).
4. Pasting into rclone's prompts can fail in cmd, so build one command in **Notepad**, then copy the whole line from there:
   ```
   rclone config create gdrive drive scope=drive client_id=YOUR_CLIENT_ID client_secret=YOUR_CLIENT_SECRET
   ```
   Paste it into cmd (right-click). Your browser opens: choose your account and allow access ("Google hasn't verified this app" → Advanced → continue).
   Test: `rclone lsd gdrive:` must list `social-inbox`.
5. Copy the login to the server. On the server: `mkdir -p ~/.config/rclone`. On the PC:
   ```
   scp -i C:\keys\oracle.key "%APPDATA%\rclone\rclone.conf" ubuntu@YOUR_SERVER_IP:~/.config/rclone/rclone.conf
   ```
   On the server: `chmod 600 ~/.config/rclone/rclone.conf` and `rclone lsd gdrive:` (must list `social-inbox`).
6. Switch the sync on: `bash ~/social-uploader/server/setup_server.sh` again (it adds the one-minute job; check with `crontab -l`).
7. Use it: in the **Google Drive app** (not Google Photos) upload a video into `social-inbox`. After one to three minutes the bot asks where to post it.
   The video leaves Drive when it is moved (Google keeps it in the trash for 30 days), so keep your own copy.

`rclone.conf` gives access to your Drive, so keep it private.

### 9.9 Everyday server checks
```
sudo systemctl status social-uploader --no-pager
journalctl -u social-uploader -n 30 --no-pager
tail -n 30 ~/social-uploader/agent.log
tail -n 20 ~/social-uploader/sync.log
free -h
df -h /
```
- Closing the SSH window does not stop the agent. After `/stop` on Telegram, start it with `sudo systemctl start social-uploader`.
- The server's clock is not important: times follow the time zone in `settings.json`.
- Once a month: sign in to the Oracle console, check the server says **Running**, and look at **Monitoring** and **Cost Analysis**.
- Install updates now and then: `sudo apt-get update && sudo apt-get upgrade -y`, then `sudo reboot`. Do not reboot within half an hour of an Instagram post time.

### 9.10 Update the agent later
Edit the two lines at the top of `deploy_to_server.bat` (your key path and `ubuntu@YOUR_SERVER_IP`), double-click it, then send `/restart` to your bot.
Check that the server runs the same version as your PC:
```
python agent.py --version                               (on the PC)
cd ~/social-uploader && ./venv/bin/python agent.py --version     (on the server)
```
To compare files exactly: `certutil -hashfile agent.py SHA256` on the PC and `sha256sum agent.py` on the server must print the same value.
To change `.env` on the server: `nano ~/social-uploader/.env`, then `sudo systemctl restart social-uploader`.

### 9.11 If the server stops
Check the console: **cloud.oracle.com → Compute → Instances → social-uploader**. If it says **Stopped**, click **Start**, wait for **Running**, then wait two to three minutes and send `/status`.
The public IP can change after a stop, so use the new one. (Optional: reserve the address under **Attached VNICs → VNIC → IPv4 addresses**.) The agent and the Drive sync start by themselves.
If the server is *Running* but `/status` is silent, connect with ssh and run `sudo systemctl start social-uploader`. The Instagram queue is stored on the server's disk and survives a stop.
A post is published late if the server comes back within about a day. After that, Instagram has dropped the prepared video, you get an error message, and you resend it.

### 9.12 Go back to the PC
Send `/stop` to stop the server agent for good, then start `run_agent.bat` on the PC. Run only one of them.

### 9.13 If Oracle closes or locks your account
**What it looked like for the author:** the console said "Invalid username or password" even after a password reset, SSH timed out, and the bot stopped answering. Oracle's chat support then said the account
had been terminated by the system after an audit. They could not give details, raised an internal appeal, gave no reference number or timeline, and said the result would arrive by email only if the decision was overturned.
1. Do not keep guessing passwords. Reset it once with **Forgot Password?** on the cloud sign-in page, and search your email (and spam) for Oracle messages.
2. Contact Oracle's chat: open `oracle.com/corporate/contact/`, start the chat, and choose **Get Support → Cloud Infrastructure (OCI) including Free Trial → Cloud Support Chat**, category **OCI Authentication**, sub-category **Password Reset**.
   The first bot may not understand "agent"; try "representative". Give your Cloud Account Name, region and what happened. Never type a full card number, PIN or CVV: the last four digits are enough.
3. Ask for an internal appeal, a written summary by email, and what you may do next. Save the chat text.
4. Meanwhile keep posting from your PC (section 8). Never run the PC agent and a server agent at the same time. If the old server comes back, close the PC agent and use `/jobs` and `/cancel` to clear duplicate Instagram posts.
5. Instagram posts waiting on a closed server are lost. YouTube and Facebook posts already scheduled still go out, because Google and Facebook hold them.
6. If the closure stands, you do not need Oracle. The same steps work on any Ubuntu 22.04 server with at least 1 GB of memory. Options (check current prices and terms before you sign up):

| Option | Cost | Notes |
|---|---|---|
| Your PC (section 8) | Free | Must be on and awake at Instagram post times |
| An old laptop or Raspberry Pi at home with Ubuntu 22.04 | Electricity only | Always on, no account that can be closed. `setup_server.sh` works on it |
| Azure free account | About 12 months free, then paid | Small Linux VM and 15 GB of outbound data a month; a card stays on file |
| Google Cloud Always Free e2-micro | Free within limits | US regions only, 1 GB of outbound data a month; each post sends the video out about 3 times |
| A small paid VPS from another provider | A few US dollars a month | Needs a card that works abroad; use at least 1 GB of memory |

---

## 10. Daily use

1. Get the video to the agent: put it in the `inbox` folder (Track A, or `scp` it to the server) or save it in your Google Drive folder.
   For large files copied by hand, upload under a temporary name and rename when finished, for example
   `scp -i C:\keys\oracle.key video.mp4 ubuntu@YOUR_SERVER_IP:~/social-uploader/inbox/video.mp4.part`, then on the server
   `mv ~/social-uploader/inbox/video.mp4.part ~/social-uploader/inbox/video.mp4`.
2. After about a minute the bot asks **where to post it**. Reply with the codes, separated by spaces:

| Code | Place |
|---|---|
| `yt` | YouTube |
| `fb` | Facebook |
| `ig1`, `ig2` | The Instagram accounts, in the order of `settings.json` |
| `ig` or `instagram` | All Instagram accounts |
| `all` | Everything that is switched on |

   Examples: `yt fb`, `ig2`, `ig1 yt`, `all`. You can also write an Instagram handle.
3. Send the **title and caption in one message.** The first line is the title and the rest is the caption. Headings are fine and are removed:
   `Title:` / `Caption:`, `Tittle:`, `शीर्षक (Title):` / `कॅप्शन (Caption):`, bold `**…**`, with the text on the same line or below the heading.
   If you paste a finished post (with hashtags and mention at the end), those are removed and yours are added.
4. Read the preview (the chosen places, final text, date, times), then reply:

| You send | What happens |
|---|---|
| `ok` | Schedules the video **only** for the places you chose |
| `date 21 Oct` (or `tomorrow`, `21/10`) | Changes the date. The default is tomorrow |
| `yt 8pm` (or `time yt 8:30`) | Changes the time of one place |
| `yt 8pm, fb 9pm` | Changes several times (separate lines also work) |
| `all 8am` | The same time for every chosen place |
| `pages yt ig1` | Changes the places. Times you already changed are kept |
| `edit` | Send a new title and caption |
| `cancel` | Skip this video (it moves to the `skipped` folder) |

   Time formats: `8pm`, `8:30pm`, `8:00 pm`, `20:00`. A time without am/pm, like `8`, means 8 in the morning. YouTube and Facebook need a time at least 15 minutes ahead.
5. After `ok`: YouTube is uploaded (private, public at your time, in your playlist), Facebook is scheduled, and the agent holds Instagram until its time. The single result message appears only when all chosen places are done, and Instagram needs a few minutes to process each video, so be patient.
   You get messages with the links. Then do the manual steps: hide likes and shares on Instagram, and the AI label if you use one.

Several videos in the inbox are handled one at a time.

**Bot commands** (send them to your bot while the agent runs):

| Send | What happens |
|---|---|
| `/help` or `/start` | Short guide |
| `/status` | Alive, version, what it is doing, the Instagram posts waiting |
| `/jobs` | Lists the waiting Instagram posts with numbers |
| `/cancel 1`, `/cancel 1 2`, `/cancel all` | Removes waiting Instagram posts (numbers from `/jobs`). The video moves to the `skipped` folder |
| `/restart` | Restarts the agent (works when started with `run_agent.bat` or the server service) |
| `/stop` | Stops the agent for good. Waiting Instagram posts do not go out until it runs again |

**Preview a cover** before posting: `python agent.py --cover C:\path\video.mp4` saves the frame as a picture. Add a number to try another second, for example `... video.mp4 12`.

**A message cannot start the agent.** The agent is the program that reads Telegram. If it is not running (PC off, closed window), start it yourself (Track A) or in the Oracle console (Track B).

---

## 11. Settings and environment reference

### `settings.json`
| Setting | Meaning |
|---|---|
| `timezone` | Your time zone, for example `Asia/Kolkata` |
| `cover_frame_seconds` | The second of the video used as cover (default 7). Short videos use the middle |
| `append_cta_if_missing` | Add `fixed_text.cta` to every post if your text does not already contain it |
| `fixed_text.cta` | A closing line for every post. `""` for none |
| `youtube.channel_handle`, `mention` | Your handle, such as `@mychannel` |
| `youtube.privacy`, `schedule_to_public` | Upload private, then make public at the time (recommended) |
| `youtube.publish_time` | Usual publish time, 24-hour, such as `"08:00"` |
| `youtube.playlist_title` | Exact name of an existing playlist. `""` for none |
| `youtube.ai_label` | `true` marks videos as AI/altered content (if YouTube rejects it, the agent retries without) |
| `youtube.hashtags`, `youtube.tags` | Hashtags (in the description) and tags (the Tags box) |
| `facebook.page_name`, `mention` | The exact Page name |
| `facebook.publish_time`, `hashtags` | Usual time and hashtags |
| `facebook.page_id` | Filled in by `meta_setup.py` |
| `facebook.page_token_env` | Name of the `.env` secret that holds the Page token |
| `instagram_accounts[]` | One block per account: `name` (no @), `mention`, `publish_time`, `hashtags`, `ig_user_id` (filled in by the helper), `page_token_env` |

### `.env`
| Variable | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Required. From BotFather and `--chatid` |
| `PLATFORMS` | `youtube`, `facebook`, `instagram`, separated by commas |
| `IG_ACCOUNTS` | Optional. Use only these Instagram accounts (names from `settings.json`). Empty = all |
| `META_PAGE_TOKEN_1`, `META_PAGE_TOKEN_2` | Page tokens. Filled in by `meta_setup.py`. Never type them by hand |
| `GRAPH_VERSION` | Meta API version (default `v23.0`) |
| `INBOX_DIR` | Optional folder to watch. Default: the `inbox` folder next to `agent.py`. Empty on a server |
| `KEEP_VIDEOS` | `1` keeps posted videos in `done`, `0` deletes them |
| `TUNNEL_PORT` | Local port for the temporary Instagram video link (default 8765) |
| `YT_CATEGORY_ID` | YouTube category number (default 22) |

`AGENT_LOOP=1` is set automatically by `run_agent.bat` and by the server service. It makes `/restart` work. Do not set it yourself.

---

## 12. Security and credentials

- **Where secrets live:** plain files in the project folder: `.env` (Telegram and Meta tokens), `client_secret.json` and `token.json` (YouTube), and on a server
  also `~/.config/rclone/rclone.conf` (Google Drive). Anyone who can open the folder can read them. Keep the folder out of OneDrive, Google Drive, Dropbox and git.
- **Where they go:** only to the service they belong to (Google, Meta, Telegram). Error messages and `agent.log` hide tokens automatically.
- **Never** paste a token or secret into a chat, an email, a forum or a screenshot (including screenshots of Notepad, nano or cmd with `.env` open).
- **If a secret leaks, replace it:**
  - Telegram: send `/revoke` to @BotFather, copy the new token into `.env`, upload `.env`, restart the agent.
  - Google client secret: create a new secret under **Google Auth Platform → Clients**, then `rclone config update gdrive client_secret=NEWSECRET`, and copy `rclone.conf` again.
    For YouTube, remove the app under your Google account's third-party access and run `python agent.py --auth`.
  - Meta: generate a new token and run `python meta_setup.py` again.
  - SSH key: make a new key pair and replace the public key on the server.
- The agent obeys only your own Telegram chat id. The server needs no open ports except SSH.
- Two-factor authentication on Google, Facebook, Instagram and Oracle. Backup admins on each Facebook Page.
- Do not commit anything listed in `.gitignore`.

---

## 13. Maintenance

| What | How often | How |
|---|---|---|
| Is the agent alive? | Now and then | `/status` on Telegram |
| YouTube login | Does not expire if the Google app is *Published* | `python agent.py --auth`, upload the new `token.json` |
| Google Drive login (server) | Same | `rclone config reconnect gdrive:` on the PC, copy `rclone.conf` |
| Facebook and Instagram tokens | Long-lived. They stop if you change your password or remove the app | Make a new token and run `python meta_setup.py` |
| Server updates | Monthly | `sudo apt-get update && sudo apt-get upgrade -y`, then `sudo reboot` |
| Disk space | Monthly | `df -h /`, delete old videos: `rm ~/social-uploader/done/*.mp4` (or `KEEP_VIDEOS=0`) |
| Backups | After any change | Keep copies of `.env`, `settings.json`, `token.json` (and `rclone.conf`) somewhere private. **Not in git** |

---

## 14. Troubleshooting

| What you see | What to do |
|---|---|
| `'python' is not recognized` / "Python was not found" | Install Python (Part 1). Open a **new** cmd afterwards |
| `ModuleNotFoundError` | You forgot `venv\Scripts\activate`. The prompt must start with `(venv)` |
| `.env` saved as `.env.txt` | In Notepad's Save As choose **All files**, or rename the file |
| `--check` lists MISSING | Each line names what is missing. Follow the matching part of this guide |
| `--chatid`: "No messages yet" | Open your bot, press Start, send `hi`, run it again |
| `Telegram accepts the token: NO - Unauthorized` | The token in `.env` is wrong or revoked: digits, colon, secret, no spaces or quotes |
| The agent stops by itself at start | It refuses to run with a missing or rejected Telegram token and says why in the log. Fix `.env`, then start it again |
| Every Telegram reply comes twice | Two agents are running (PC and server, or two windows). Close one |
| `/stop` stopped the wrong agent | `/stop` goes to whichever agent reads the bot. Stop a PC agent by closing its window |
| `settings.json has a typo` | A missing comma or quote. Compare with `settings.example.json` |
| Google "Access blocked" / `access_denied` | Add your Gmail under **Audience → Test users**, or Publish the app |
| Google `redirect_uri_mismatch` | The client was not a **Desktop app**. Create a new one |
| YouTube shows Private, not Scheduled | Google may hold unaudited projects as private. Publish by hand or apply for the API audit |
| YouTube or Drive login stops after about a week | The Google app is in Testing. **Publish app**, then log in again |
| Meta login popup: "You don't have any Pages" | You are logged in with a Facebook account that does not manage the Pages. Use the managing account (also for the developer registration) |
| Graph API Explorer: "No configurations available", cannot generate a token | The app has no Facebook Login for Business configuration. Do 7.2 step 3 and 4 |
| Helper: "Error validating client secret" | The secret does not match the App ID. Copy the secret again from **App settings → Basic** of the same app |
| Helper shows "1 characters" | The paste did not arrive. Right-click to paste, or use Shift+Insert |
| Helper: Page shows "Instagram: not linked" | Tick the Instagram account in the popup, and complete the link in 7.1 |
| Instagram link: "Something went wrong" | See the notes under 7.1: other routes, the Confirm button, a new Page, or wait a day |
| Facebook upload error 413 | Fixed in this version (chunked upload). Make sure `agent.py` is current: `python agent.py --version` |
| Facebook or Instagram: token invalid/expired | Make a new token and run `python meta_setup.py` |
| Instagram error mentioning `cloudflared` | Install it (`winget install Cloudflare.cloudflared`, or the setup script on a server) and open a new window |
| Instagram did not post on time | The agent was not running at that time (PC off or asleep, server stopped) |
| I posted a test video and want to cancel it | Instagram: `/jobs`, then `/cancel 1` (or `/cancel all`). YouTube: delete it in YouTube Studio. Facebook: delete it in Meta Business Suite. The agent cannot cancel those two |
| "Time … has passed or is too close" | Choose a later date or time (YouTube and Facebook need 15+ minutes ahead) |
| Nothing happens when I add a video | Wait about a minute. Only `.mp4`, `.mov`, `.m4v`. Check the folder (`INBOX_DIR`). Check `/status` |
| Video from Drive never arrives | `rclone lsd gdrive:` must list `social-inbox`. Read `~/social-uploader/sync.log`. Check `crontab -l`. Use Google Drive, not Google Photos |
| `UNPROTECTED PRIVATE KEY FILE` | Fix the key permissions (9.4), including the same-name note |
| `Permission denied (publickey)` | Wrong key file or user. Use the key you made and `ubuntu@` |
| `Connection timed out` (ssh) | The server is stopped, or its IP changed. Check the Oracle console |
| Oracle says "Invalid username or password" after a reset, ssh times out and the bot is silent | Possible account closure. Do not keep guessing passwords. See section 9.13 |
| Your bank declines an Oracle payment ("International online usage disabled") | Switch on International online for the card (a small per-transaction limit is fine). See section 9.0 |
| The instance wizard shows only paid shapes (E4, E5) | Click **Change shape → Specialty and previous generation**, then pick `VM.Standard.E2.1.Micro` |
| The wizard's estimated cost shows a boot volume price | It is a list price. Check **Cost Analysis** the next day. See section 9.0, point 11 |
| `bad interpreter` or `$'\r': command not found` | Run `sed -i 's/\r$//' ~/social-uploader/server/*.sh`. Git users: `.gitattributes` prevents this |
| Server pasting problems | Right-click once, Shift+Insert, or use PowerShell. Type short commands by hand |

---

## 15. Honest status and limits

**Tested live by the author (up to version 1.1.0):** Telegram control; YouTube upload, schedule, tags, description, playlist; Facebook chunked upload, schedule, text and cover;
Instagram linking, token setup and the helper; **publishing real Instagram posts at their set time on both Instagram accounts, run from the server with the PC off**; `/cancel all` removing queued Instagram posts; the Oracle server setup;
Google Drive sync; the choose-where-to-post flow; time commands; heading removal.
The automated tests (section 16) cover all of this offline. Your results may differ: platform rules, app review states and account types change, so run the tests in section 7.4 on your own accounts before you rely on it.

**Limits**
- YouTube's free quota allows roughly 6 uploads a day. Projects Google has not audited may keep uploads private.
- Facebook posting is for **Pages**, not personal profiles. A page mention through the API appears as plain text, not a blue tag.
- Instagram Reels through the API can be at most 90 seconds. Instagram has no API scheduler, so the agent must be running at post time.
- The AI-content label on Facebook and Instagram, and hiding likes and shares on Instagram, are manual.
- `fb` posts to one Facebook Page only (the one in `settings.json`).
- Instagram needs a few minutes to process each video (about 3 to 5 minutes for a 30 to 45 second Reel in the author's tests). Instagram's own "share to Facebook" setting can copy Reels to your Page, so turn it off (section 7.1).
- Free cloud accounts can be closed by the provider's automated checks, sometimes with no stated reason and no confirmed way back (section 9.13). Section 9.0 lists what we know to avoid. Keep backups and treat the server as replaceable.
- Meta, Google and Oracle change their menus and rules. If a screen differs from this guide, pick the nearest option.

---

## 16. Project files, tests and git

```
agent.py                    the agent
captions.py                 title/caption parsing and the per-platform text
meta_setup.py               one-time helper for Facebook and Instagram tokens and ids
requirements.txt            Python packages
settings.example.json       copy to settings.json and fill in
.env.example                copy to .env and fill in
run_agent.bat               Windows: start the agent and restart it if it stops
deploy_to_server.bat        Windows: send updated files to your server
server/setup_server.sh      server: one-command setup
server/social-uploader.service   server: background service definition
server/sync_inbox.sh        server: moves videos from Google Drive into the inbox
tests/test_project.py       offline tests
docs/privacy-site-templates/  two web page templates for Google's Branding page (section 6)
LICENSE                     the MIT License
.gitignore, .gitattributes  keep secrets out of git, keep correct line endings
```

**Run the tests** (no internet and no accounts needed, your own files are not touched):
```
python tests/test_project.py -v
```

**Putting it in git**
```
cd C:\social-uploader
git init
git add .
git status
```
Read the `git status` list **before committing**. It must not contain `.env`, `token.json`, `client_secret.json`, `settings.json`, `schedule.json`, any `.key` file or any video. If one appears,
stop and fix `.gitignore`. Then:
```
git commit -m "First commit"
```
If you keep your own copy in git, use a **private** repository, commit `settings.example.json`, and never commit your own `settings.json`. Anyone who clones this project repeats Parts 1 to 5 with their own accounts.
Never reuse someone else's tokens, Telegram bot or Meta app, and never publish your own `.env`, `token.json`, `rclone.conf` or screenshots of them.
GitHub's web upload ignores `.gitignore`, so check the file list before you commit.

**License, support and contributions.** The project is released under the MIT License (see `LICENSE`). It is provided as it is, without warranty or support.
Improvements are welcome as pull requests: run `python tests/test_project.py` first, and never include secrets or personal data.

---

## 17. Command cheat sheet

| Command | What it does |
|---|---|
| `python agent.py` | Runs the agent |
| `run_agent.bat` | Runs the agent and restarts it if it stops (Windows) |
| `python agent.py --check` | Shows what is still missing |
| `python agent.py --version` | Prints the version |
| `python agent.py --chatid` | Finds your Telegram chat id |
| `python agent.py --auth` | One-time YouTube login |
| `python agent.py --cover video.mp4 [seconds]` | Saves the cover frame as a picture |
| `python captions.py [file.txt]` | Shows how posts will look (no internet) |
| `python meta_setup.py` | Sets up the Facebook and Instagram tokens and ids |
| `python tests/test_project.py -v` | Runs the offline tests |
| `bash ~/social-uploader/server/setup_server.sh` | One-time server setup (run on the server) |
| `sudo systemctl status/start/stop/restart social-uploader` | Controls the agent on the server |
| `/help`, `/status`, `/jobs`, `/cancel`, `/restart`, `/stop` | Bot commands in Telegram |
