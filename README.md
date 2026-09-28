# PageWatch AI Lite

PageWatch AI Lite watches a few web pages for changes. The first run saves a
baseline; later runs ask AI whether a change matters. Email notifications are
not available yet.

For classification, put a [Console Chat Completions model](https://opencode.ai/v2/docs/console/inference/)
and a Console service account key in a local `.env` file. Shell environment
variables take precedence.

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
`IGNORE` saves the new baseline; `NOTIFY` and `REVIEW` print the diff and keep
the previous baseline until email delivery is implemented.
