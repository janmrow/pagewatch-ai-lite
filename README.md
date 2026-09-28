# PageWatch AI Lite

PageWatch AI Lite watches a few web pages for changes. The first run saves a
baseline; later runs print a diff if a page changed. AI filtering and email
notifications are not available yet.

## Run on Ubuntu

Requires Python 3.11 or newer. If you do not have `config.toml`, copy
`config.example.toml` to it and edit the targets. From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python pagewatch.py
```

Run `python pagewatch.py` again whenever you want to check for changes.
