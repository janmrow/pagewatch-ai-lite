# PageWatch AI Lite

PageWatch AI Lite watches a few web pages for changes. The first run saves a
baseline; later runs ask AI whether a change matters and email you about
relevant or uncertain changes.

For classification, put a [Console Chat Completions model](https://opencode.ai/v2/docs/console/inference/)
and a Console service account key in a local `.env` file. Shell environment
variables take precedence. Set `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_FROM`, and `SMTP_TO` there too. Email uses STARTTLS on port 587 by default.

## Run on Ubuntu

Requires Python 3.11 or newer. If you do not have `config.toml`, copy
`config.example.toml` to it and edit the targets. From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
nano .env
python pagewatch.py
```

Run `python pagewatch.py` again whenever you want to check for changes.
`IGNORE` saves the new baseline. `NOTIFY` and `REVIEW` send an email, then save
the new baseline. If sending fails, the previous baseline stays in place.
