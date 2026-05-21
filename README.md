# AI News → Hebrew → Telegram

A free, fully automatic publisher that reads English-language AI news from RSS feeds, summarizes and translates each item to Hebrew with Google Gemini (free tier), and posts to your Telegram channel on a schedule.

Total cost: **$0** when run on a public GitHub repo.

## What runs where

- **GitHub Actions** runs `main.py` once per hour (free on public repos).
- **Gemini Flash (free tier)** writes a short Hebrew post for each new article — up to ~1,500 requests/day at no charge.
- **Telegram Bot API** publishes the post to your channel (free).
- A small `seen.json` file in the repo remembers what was already posted so you never see duplicates.

## One-time setup (about 15 minutes)

### 1. Create a Telegram bot

1. In Telegram, message **@BotFather**.
2. Send `/newbot`, follow the prompts, and copy the **token** it gives you (looks like `123456:ABC-DEF...`). Keep this safe — it's `TELEGRAM_BOT_TOKEN`.

### 2. Add the bot to your channel as admin

1. Open your channel → **Manage Channel** → **Administrators** → **Add Administrator**.
2. Search for your bot by its username and add it. The only permission it needs is **Post Messages**.

### 3. Get your channel ID

Easiest way:
- If your channel is **public** (has a `@username`), your `TELEGRAM_CHAT_ID` is just `@yourchannelname`.
- If it's **private**, send any test message in the channel, then open this URL in a browser (replace `<TOKEN>`):
  `https://api.telegram.org/bot<TOKEN>/getUpdates`
  Look for `"chat":{"id":-100...}`. That number (with the minus sign) is your `TELEGRAM_CHAT_ID`.

### 4. Get a free Gemini API key

1. Go to <https://aistudio.google.com/apikey>.
2. Sign in with a Google account → **Create API key**.
3. Copy the key. This is `GEMINI_API_KEY`.

Free tier limits at the time of writing: ~15 requests/minute and ~1,500 requests/day on Gemini Flash — far more than this script needs.

### 5. Push this project to GitHub

```bash
cd ai-telegram-feed
git init
git add .
git commit -m "initial commit"
# create a new PUBLIC repo on github.com, then:
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

> Use a **public** repo so GitHub Actions minutes are unlimited. If you'd rather keep it private, you still get 2,000 free minutes/month, which is plenty.

### 6. Add your secrets to GitHub

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**. Add three:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The token from step 1 |
| `TELEGRAM_CHAT_ID`   | `@yourchannel` or the `-100...` number from step 3 |
| `GEMINI_API_KEY`     | The Gemini key from step 4 |

### 7. Run it once to confirm everything works

In GitHub: **Actions** tab → **AI News → Telegram** → **Run workflow**. Watch the log. Within ~30 seconds you should see new posts in your channel.

After that, it runs automatically every hour. No further action needed.

## Tweaking the publisher

- **Add or remove sources**: edit `feeds.yaml` and push. The next run will use the new list.
- **Post more or less often**: edit the `cron:` line in `.github/workflows/run.yml`. `0 */2 * * *` = every 2 hours, `0 9,18 * * *` = 9am and 6pm UTC, etc. ([cron syntax cheatsheet](https://crontab.guru))
- **More or fewer posts per run**: change `MAX_ITEMS_PER_RUN` in the workflow file (default 5).
- **Tone of the Hebrew posts**: edit the `PROMPT` string at the top of `main.py`.
- **Different Gemini model**: set `GEMINI_MODEL` env var in the workflow (default `gemini-2.0-flash`).

## Local testing (optional)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=@yourchannel
export GEMINI_API_KEY=...
python main.py
```

## Troubleshooting

- **No posts appear**: check the Actions log. Common causes: bot isn't an admin in the channel, wrong `TELEGRAM_CHAT_ID`, or Gemini key not set.
- **"Bad Request: chat not found"**: the bot isn't in the channel, or the chat ID is wrong.
- **Posts include English instead of Hebrew**: the model fell back. Increase `temperature` or switch `GEMINI_MODEL` to a stronger model like `gemini-2.5-flash`.
- **Same article posted twice**: `seen.json` wasn't committed back. Make sure the repo has **Settings → Actions → General → Workflow permissions → Read and write**.
