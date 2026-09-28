"""Fetch configured pages and report changes from their saved baselines."""

import argparse
import difflib
import os
import re
import sys
import tempfile
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

BLOCK_TAGS = {
    "article",
    "br",
    "dd",
    "div",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
MAX_PAGE_BYTES = 5_000_000


class TextExtractor(HTMLParser):
    def __init__(self, main_only=False):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipped = []
        self.main_only = main_only
        self.in_main = False
        self.seen_main = False

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main = True
            self.seen_main = True
        if tag in SKIP_TAGS:
            self.skipped.append(tag)
        elif (
            tag in BLOCK_TAGS
            and not self.skipped
            and (not self.main_only or self.in_main)
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skipped:
            if tag == self.skipped[-1]:
                self.skipped.pop()
        elif tag in BLOCK_TAGS and (not self.main_only or self.in_main):
            self.parts.append("\n")
        if tag == "main":
            self.in_main = False

    def handle_data(self, data):
        if not self.skipped and (not self.main_only or self.in_main):
            self.parts.append(data)


def normalize_text(html):
    parser = TextExtractor(main_only=True)
    parser.feed(html)
    if not parser.seen_main:
        parser = TextExtractor()
        parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    text = "\n".join(line for line in lines if line)
    if not text:
        raise ValueError("page contains no text")
    return text + "\n"


def load_targets(config_path):
    with config_path.open("rb") as config_file:
        targets = tomllib.load(config_file).get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("config must contain at least one [[targets]] entry")

    result = []
    seen_ids = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("each target must be a TOML table")
        target_id = target.get("id")
        url = target.get("url")
        if not isinstance(target_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*", target_id
        ):
            raise ValueError(
                "target id must use letters, digits, underscores, or hyphens"
            )
        if target_id in seen_ids:
            raise ValueError(f"duplicate target id: {target_id}")
        if not isinstance(url, str):
            raise ValueError(f"target {target_id}: url must be a string")
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError(f"target {target_id}: url must be HTTP or HTTPS")
        result.append((target_id, url))
        seen_ids.add(target_id)
    return result


def fetch_page(url):
    request = Request(url, headers={"User-Agent": "pagewatch-ai-lite/0.1"})
    with urlopen(request, timeout=15) as response:
        content = response.read(MAX_PAGE_BYTES + 1)
        if len(content) > MAX_PAGE_BYTES:
            raise ValueError("page exceeds 5 MB limit")
        charset = response.headers.get_content_charset() or "utf-8"
    return content.decode(charset, errors="replace")


def save_baseline(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temp_file:
            temp_file.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def run(config_path, state_dir):
    targets = load_targets(config_path)
    failed = False
    for target_id, url in targets:
        try:
            current = normalize_text(fetch_page(url))
            state_path = state_dir / f"{target_id}.txt"
            try:
                previous = state_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                save_baseline(state_path, current)
                print(f"{target_id}: baseline saved")
                continue
            if current != previous:
                diff = difflib.unified_diff(
                    previous.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=f"{target_id}: previous",
                    tofile=f"{target_id}: current",
                )
                sys.stdout.writelines(diff)
        except Exception as exc:
            failed = True
            print(f"{target_id}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--state-dir", type=Path, default=Path(".state"))
    args = parser.parse_args()
    try:
        return run(args.config, args.state_dir)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"configuration: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
