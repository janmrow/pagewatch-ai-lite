# PageWatch AI Lite

PageWatch AI Lite watches a few web pages for changes. The first run saves a
baseline; later runs ask AI whether a change matters and email you about
relevant or uncertain changes.

## Run on Mikrus (Ubuntu)

Connect by SSH. The server needs Python 3.11 or newer. In your home directory:

```sh
git clone https://github.com/janmrow/pagewatch-ai-lite.git
cd pagewatch-ai-lite
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
nano .env
.venv/bin/python pagewatch.py
ls .state/*.txt
```

Fill in the OpenCode model and API key, and the SMTP settings shown in
`.env.example`. The first successful run prints `baseline saved` for all four
targets and sends no email. Secrets in `.env` and the `.state/` directory stay
outside Git.

Check `TZ=Europe/Warsaw date` and add this line with `crontab -e`:

```cron
0 * * * * case "$(TZ=Europe/Warsaw date +\%H)" in 09|11|13|15) cd "$HOME/pagewatch-ai-lite" && { TZ=Europe/Warsaw date -Is; .venv/bin/python pagewatch.py; echo "exit=$?"; } >> .state/cron.log 2>&1;; esac
```

The hourly cron check runs the watcher only at 09:00, 11:00, 13:00 and 15:00
Warsaw time, including daylight saving changes. This also works when the
server's system timezone is UTC. Check `crontab -l` and
`tail -n 40 .state/cron.log` for timestamps, results and errors.
