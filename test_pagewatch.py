import contextlib
import tempfile
import unittest
from email.message import Message
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

import pagewatch


class CoreWatcherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "config.toml"
        self.config.write_text(
            '[[targets]]\nid = "course"\nurl = "https://example.com/course"\n',
            encoding="utf-8",
        )
        self.state_dir = self.root / ".state"

    def test_first_run_same_page_and_change(self):
        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>Places open</p>"),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
        baseline = self.state_dir / "course.txt"
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Places open\n")
        self.assertEqual(output.getvalue(), "course: baseline saved\n")

        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>Places closed</p>"),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
        self.assertIn("-Places open\n+Places closed\n", output.getvalue())
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Places open\n")

    def test_target_failure_does_not_block_another_or_change_its_state(self):
        self.config.write_text(
            '[[targets]]\nid = "broken"\nurl = "https://example.com/broken"\n'
            '[[targets]]\nid = "working"\nurl = "https://example.com/working"\n',
            encoding="utf-8",
        )
        self.state_dir.mkdir()
        (self.state_dir / "broken.txt").write_text("Known good\n", encoding="utf-8")

        def fetch(url):
            if url.endswith("broken"):
                raise OSError("fetch failed")
            return "<p>Working</p>"

        with (
            patch.object(pagewatch, "fetch_page", side_effect=fetch),
            contextlib.redirect_stdout(StringIO()),
            contextlib.redirect_stderr(StringIO()),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
        self.assertEqual(
            (self.state_dir / "broken.txt").read_text(encoding="utf-8"), "Known good\n"
        )
        self.assertEqual(
            (self.state_dir / "working.txt").read_text(encoding="utf-8"), "Working\n"
        )

    def test_normalization_ignores_markup_noise_and_scripts(self):
        first = (
            "<h1>Open&nbsp; places</h1><script>bad()</script><p>Apply <b>now</b></p>"
        )
        second = "<h1> Open places </h1><style>p{color:red}</style><p>Apply now</p>"
        self.assertEqual(pagewatch.normalize_text(first), "Open places\nApply now\n")
        self.assertEqual(
            pagewatch.normalize_text(first), pagewatch.normalize_text(second)
        )

    def test_main_content_excludes_navigation_and_footer(self):
        html = (
            "<nav>Menu update</nav><main><h1>Course</h1>"
            "<p>Recruitment extended</p></main><footer>Other news</footer>"
        )
        self.assertEqual(
            pagewatch.normalize_text(html), "Course\nRecruitment extended\n"
        )

    def test_empty_main_is_not_a_valid_baseline(self):
        with self.assertRaisesRegex(ValueError, "no text"):
            pagewatch.normalize_text("<nav>Menu</nav><main></main>")

    def test_ids_cannot_escape_state_directory(self):
        self.config.write_text(
            '[[targets]]\nid = "../outside"\nurl = "https://example.com"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "target id"):
            pagewatch.load_targets(self.config)

    def test_fetch_uses_timeout_and_page_charset(self):
        response = BytesIO("Zażółć".encode("iso-8859-2"))
        response.headers = Message()
        response.headers["Content-Type"] = "text/html; charset=iso-8859-2"
        with patch.object(pagewatch, "urlopen", return_value=response) as open_url:
            self.assertEqual(pagewatch.fetch_page("https://example.com"), "Zażółć")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 15)

    def test_failed_atomic_replace_preserves_previous_state(self):
        self.state_dir.mkdir()
        baseline = self.state_dir / "course.txt"
        baseline.write_text("Known good\n", encoding="utf-8")
        with patch.object(
            pagewatch.os, "replace", side_effect=OSError("replace failed")
        ):
            with self.assertRaisesRegex(OSError, "replace failed"):
                pagewatch.save_baseline(baseline, "New text\n")
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Known good\n")
        self.assertEqual(list(self.state_dir.iterdir()), [baseline])


if __name__ == "__main__":
    unittest.main()
