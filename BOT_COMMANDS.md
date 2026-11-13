# Social Uploader: Telegram bot commands (version 1.2.0)

Send these to your bot in Telegram. There are two kinds:
- **Commands that start with `/`** work at any time.
- **Replies** work only while the bot is asking you about a video (after it says "New video…").

---

## 1. Commands (start with `/`, work any time)

| Command | What it does |
|---|---|
| `/help` or `/start` | Shows a short guide and the list of commands |
| `/status` | Shows that the agent is alive, its version, which places are switched on, what it is doing, how many videos are in the inbox, and the Instagram posts waiting |
| `/jobs` | Lists the waiting Instagram posts with numbers (account, time, state, first line of the caption) |
| `/cancel 1` | Removes Instagram post number 1 from the list (use the number from `/jobs`) |
| `/cancel 1 2` | Removes several Instagram posts at once |
| `/cancel all` | Removes every waiting Instagram post. Nothing will be posted for them |
| `/disk` | Shows how many videos are kept on this machine in each folder (inbox, scheduled, skipped, done), how big they are, and the free disk space. Warns when less than 3 GB is free |
| `/clean` | Deletes the **cancelled** videos (the `skipped` folder) and says how much space it freed. Never touches the inbox or the Instagram posts that are still waiting |
| `/clean done` | Also deletes **posted** videos. It first asks you to confirm: send `/clean done yes`. The small results records are kept |
| `/clean all` | Cancelled and posted videos together. Confirm with `/clean all yes` |
| `/restart` | Restarts the agent. It is back in about 15 seconds. Use it after updating files. A video you were answering about is asked about again, and waiting Instagram posts are kept |
| `/stop` | Stops the agent for good. Waiting Instagram posts do **not** go out until it runs again. To start it again: `sudo systemctl start social-uploader` on the server, or `run_agent.bat` on the PC |

Notes
- A cancelled video is **kept** in the `skipped` folder until you send `/clean`. Nothing is left at Instagram.
- `/cancel` removes **Instagram posts only**. YouTube and Facebook posts are held by Google and Facebook, so delete those in YouTube Studio and Meta Business Suite.
- `/restart` works when the agent was started with `run_agent.bat` or runs as the server service.
- `/stop` goes to whichever agent is reading the bot. If an old agent is still running on your PC, close its window instead of sending `/stop`.
- A message cannot start the agent. If the agent is not running, the bot stays silent.

---

## 2. Replies while the bot is asking about a video

### Step 1: "Where should this video be posted?"
| You send | Meaning |
|---|---|
| `yt` | YouTube |
| `fb` | Facebook Page |
| `ig1` | Instagram account number 1 (the first in `settings.json`) |
| `ig2` | Instagram account number 2 |
| `ig` or `instagram` | All Instagram accounts |
| `all` | Everything that is switched on |
| `yt fb`, `ig2 yt`, `yt, ig1` | Several places, separated by spaces or commas |
| an Instagram handle | That account, for example `your_instagram_handle` |
| `skip` or `cancel` | Ignore this video (it moves to the `skipped` folder) |

### Step 2: the title and caption
Send **one message**. The first line is the title and the rest is the caption.
You can also use headings (they are removed and never appear in the posts):
`Title:` / `Caption:`, `Tittle:`, `शीर्षक (Title):` / `कॅप्शन (Caption):`, bold `**…**`, with the text on the same line or below.
If you paste a finished post (with hashtags and mention at the end), those are removed and yours are added.

### Step 3: the preview. You can reply with:
| You send | What it does |
|---|---|
| `ok` (also `yes`, `y`, `okay`) | Schedules the video **only** for the places you chose |
| `date 21 Oct` | Changes the date. Also `date tomorrow`, `date today`, `date 21/10`, `date 2026-10-21`. The default is tomorrow |
| `yt 8pm` | Changes the time for YouTube. Also `time yt 8:30` |
| `yt 8pm, fb 9pm` | Changes several times at once (separate lines also work) |
| `all 8am` | The same time for every chosen place |
| `pages yt ig1` | Changes the places for this video. Times you already changed are kept |
| `edit` | Send a new title and caption |
| a long new message | Treated as a new title and caption (a pasted edit) |
| `cancel` or `skip` | Drop this video |

Time formats: `8pm`, `8:30pm`, `8:00 pm`, `20:00`. A time without am/pm, like `8`, means 8 in the morning.
Time codes: `yt`, `fb`, `ig1`, `ig2` (only for places you chose).
YouTube and Facebook need a time at least 15 minutes ahead.

---

## 3. What happens after `ok`
- **YouTube:** uploaded as private, becomes public at your time, added to your playlist.
- **Facebook:** scheduled with Facebook's own scheduler.
- **Instagram:** held by the agent, which prepares the video about 20 hours before and publishes at the time. The agent must be running then.
- You get messages with the links, and a short "still manual" reminder: hide likes and shares on Instagram, and the AI-content label on Facebook and Instagram.

---

## 4. Messages the bot sends by itself
| Message | Meaning |
|---|---|
| "Agent 1.2.0 is running…" | The agent has just started |
| "New video: name.mp4" and the places menu | A video arrived in the inbox |
| "PLEASE CHECK" and the preview | Check the text, date and times, then reply `ok` |
| "Working on it: …" | Uploading |
| "Instagram @… is ready and will post at …" | The video is prepared. It will be published at that time |
| "✅ Instagram @… posted: link" | Published |
| "❌ … failed: …" | Something went wrong. The message names the place. Tokens are hidden in it |
