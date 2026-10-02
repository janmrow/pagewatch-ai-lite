import contextlib
import difflib
import json
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
            '[[targets]]\nid = "course"\nurl = "https://example.com/course"\n'
            'intent = "Watch recruitment"\n',
            encoding="utf-8",
        )
        self.state_dir = self.root / ".state"

    def test_first_run_same_page_and_change(self):
        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>Places open</p>"),
            patch.object(pagewatch, "classify_change") as classify,
            patch.object(pagewatch, "send_notification") as notify,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
        classify.assert_not_called()
        notify.assert_not_called()
        baseline = self.state_dir / "course.txt"
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Places open\n")
        self.assertEqual(
            output.getvalue(),
            "course: baseline saved\n"
            "summary: checked=1 changed=0 ai=0 notified=0 review=0 failed=0\n"
            "summary: checked=1 changed=0 ai=0 notified=0 review=0 failed=0\n",
        )

        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>Places closed</p>"),
            patch.object(
                pagewatch, "classify_change", return_value="NOTIFY"
            ) as classify,
            patch.object(pagewatch, "send_notification") as notify,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
        self.assertEqual(classify.call_count, 1)
        self.assertEqual(
            classify.call_args.args[:3],
            ("course", "https://example.com/course", "Watch recruitment"),
        )
        self.assertIn("-Places open\n+Places closed\n", classify.call_args.args[3])
        self.assertEqual(
            notify.call_args.args[:3],
            ("course", "https://example.com/course", "NOTIFY"),
        )
        self.assertEqual(notify.call_args.args[3], classify.call_args.args[3])
        self.assertEqual(
            output.getvalue(),
            "course: NOTIFY\n"
            "summary: checked=1 changed=1 ai=1 notified=1 review=0 failed=0\n",
        )
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Places closed\n")

    def test_review_and_ignore_update_state(self):
        self.state_dir.mkdir()
        baseline = self.state_dir / "course.txt"
        baseline.write_text("Old\n", encoding="utf-8")
        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>New</p>"),
            patch.object(pagewatch, "classify_change", return_value="REVIEW"),
            patch.object(pagewatch, "send_notification") as notify,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[2], "REVIEW")
        self.assertEqual(
            output.getvalue(),
            "course: REVIEW\n"
            "summary: checked=1 changed=1 ai=1 notified=1 review=1 failed=0\n",
        )
        self.assertEqual(baseline.read_text(encoding="utf-8"), "New\n")

        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>Newer</p>"),
            patch.object(pagewatch, "classify_change", return_value="IGNORE"),
            patch.object(pagewatch, "send_notification") as notify,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
        notify.assert_not_called()
        self.assertEqual(
            output.getvalue(),
            "course: IGNORE\n"
            "summary: checked=1 changed=1 ai=1 notified=0 review=0 failed=0\n",
        )
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Newer\n")

    def test_oversized_diff_reviews_only_after_email_succeeds(self):
        self.assertEqual(pagewatch.MAX_CLASSIFICATION_DIFF_BYTES, 512 * 1024)
        self.state_dir.mkdir()
        baseline = self.state_dir / "course.txt"
        baseline.write_text("Old\n", encoding="utf-8")
        normal_text = "N" * 20_000
        oversized_text = "X" * (pagewatch.MAX_CLASSIFICATION_DIFF_BYTES + 1)
        settings = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "account@example.com",
            "SMTP_PASSWORD": "test-secret",
            "SMTP_FROM": "watcher@example.com",
            "SMTP_TO": "reader@example.com",
        }
        with (
            patch.dict(pagewatch.os.environ, settings, clear=True),
            patch.object(pagewatch.smtplib, "SMTP") as smtp,
        ):
            with (
                patch.object(
                    pagewatch, "fetch_page", return_value=f"<p>{normal_text}</p>"
                ),
                patch.object(
                    pagewatch, "classify_change", return_value="IGNORE"
                ) as classify,
                contextlib.redirect_stdout(StringIO()),
            ):
                self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
            classify.assert_called_once()
            self.assertIn(normal_text, classify.call_args.args[3])
            self.assertLessEqual(
                len(classify.call_args.args[3].encode("utf-8")),
                pagewatch.MAX_CLASSIFICATION_DIFF_BYTES,
            )
            smtp.assert_not_called()
            self.assertEqual(baseline.read_text(encoding="utf-8"), normal_text + "\n")

            server = smtp.return_value.__enter__.return_value
            server.send_message.side_effect = OSError("SMTP failed")
            error = StringIO()
            output = StringIO()
            with (
                patch.object(
                    pagewatch, "fetch_page", return_value=f"<p>{oversized_text}</p>"
                ),
                patch.object(pagewatch, "classify_change") as classify,
            ):
                with (
                    contextlib.redirect_stderr(error),
                    contextlib.redirect_stdout(output),
                ):
                    self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
                classify.assert_not_called()
                self.assertIn("course [email]: OSError: SMTP failed", error.getvalue())
                self.assertEqual(
                    output.getvalue(),
                    "summary: checked=1 changed=1 ai=0 notified=0 review=1 failed=1\n",
                )
                self.assertEqual(
                    baseline.read_text(encoding="utf-8"), normal_text + "\n"
                )

                expected_diff = "".join(
                    difflib.unified_diff(
                        (normal_text + "\n").splitlines(keepends=True),
                        (oversized_text + "\n").splitlines(keepends=True),
                        fromfile="course: previous",
                        tofile="course: current",
                    )
                )
                message = server.send_message.call_args.args[0]
                self.assertEqual(message["Subject"], "[PageWatch] REVIEW: course")
                body = message.get_content()
                self.assertIn("Target: course", body)
                self.assertIn("Page:\nhttps://example.com/course", body)
                self.assertIn("Note:\nAutomatic classification was skipped", body)
                self.assertIn(f"{len(expected_diff.encode('utf-8'))} bytes", body)
                self.assertIn("limit 512 KiB", body)
                self.assertIn("Automatic classification was skipped", body)
                self.assertIn("Open the page and review the change manually", body)
                self.assertIn("Before:\n" + normal_text[:100], body)
                self.assertIn("Now:\n" + oversized_text[:100], body)
                self.assertIn("[Change details truncated; open the page", body)
                self.assertNotIn("@@ ", body)
                self.assertNotIn("Reason:", body)
                self.assertLess(len(body), 5_000)

                server.send_message.side_effect = None
                output = StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(pagewatch.run(self.config, self.state_dir), 0)
                classify.assert_not_called()
                self.assertEqual(
                    output.getvalue(),
                    "course: REVIEW\n"
                    "summary: checked=1 changed=1 ai=0 notified=1 review=1 failed=0\n",
                )
                self.assertEqual(
                    baseline.read_text(encoding="utf-8"), oversized_text + "\n"
                )

    def test_notification_failure_preserves_state_and_other_target_runs(self):
        self.config.write_text(
            '[[targets]]\nid = "first"\nurl = "https://example.com/first"\n'
            'intent = "Watch recruitment"\n'
            '[[targets]]\nid = "second"\nurl = "https://example.com/second"\n'
            'intent = "Watch recruitment"\n',
            encoding="utf-8",
        )
        self.state_dir.mkdir()
        (self.state_dir / "first.txt").write_text("Old\n", encoding="utf-8")
        (self.state_dir / "second.txt").write_text("Old\n", encoding="utf-8")
        error = StringIO()
        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>New</p>"),
            patch.object(pagewatch, "classify_change", return_value="NOTIFY"),
            patch.object(
                pagewatch,
                "send_notification",
                side_effect=[OSError("SMTP failed"), None],
            ) as notify,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(error),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
        self.assertEqual(notify.call_count, 2)
        self.assertIn("first [email]: OSError: SMTP failed", error.getvalue())
        self.assertEqual(
            output.getvalue(),
            "second: NOTIFY\n"
            "summary: checked=2 changed=2 ai=2 notified=1 review=0 failed=1\n",
        )
        self.assertEqual(
            (self.state_dir / "first.txt").read_text(encoding="utf-8"), "Old\n"
        )
        self.assertEqual(
            (self.state_dir / "second.txt").read_text(encoding="utf-8"), "New\n"
        )

    def test_review_email_failure_counts_review_without_notification(self):
        self.state_dir.mkdir()
        baseline = self.state_dir / "course.txt"
        baseline.write_text("Old\n", encoding="utf-8")
        output = StringIO()
        error = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>New</p>"),
            patch.object(pagewatch, "classify_change", return_value="REVIEW"),
            patch.object(
                pagewatch, "send_notification", side_effect=OSError("SMTP failed")
            ) as notify,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(error),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
        notify.assert_called_once()
        self.assertIn("course [email]: OSError: SMTP failed", error.getvalue())
        self.assertEqual(
            output.getvalue(),
            "summary: checked=1 changed=1 ai=1 notified=0 review=1 failed=1\n",
        )
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Old\n")

    def test_classification_failure_preserves_state(self):
        self.state_dir.mkdir()
        baseline = self.state_dir / "course.txt"
        baseline.write_text("Old\n", encoding="utf-8")
        for failure in (ValueError("bad reply"), TimeoutError("LLM timed out")):
            with self.subTest(failure=type(failure).__name__):
                error = StringIO()
                output = StringIO()
                with (
                    patch.object(pagewatch, "fetch_page", return_value="<p>New</p>"),
                    patch.object(pagewatch, "classify_change", side_effect=failure),
                    patch.object(pagewatch, "send_notification") as notify,
                    contextlib.redirect_stderr(error),
                    contextlib.redirect_stdout(output),
                ):
                    self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
                notify.assert_not_called()
                self.assertIn(
                    f"course [classify]: {type(failure).__name__}", error.getvalue()
                )
                self.assertEqual(
                    output.getvalue(),
                    "summary: checked=1 changed=1 ai=1 notified=0 review=0 failed=1\n",
                )
                self.assertEqual(baseline.read_text(encoding="utf-8"), "Old\n")

    def test_target_failure_does_not_block_another_or_change_its_state(self):
        self.config.write_text(
            '[[targets]]\nid = "broken"\nurl = "https://example.com/broken"\n'
            'intent = "Watch recruitment"\n'
            '[[targets]]\nid = "working"\nurl = "https://example.com/working"\n'
            'intent = "Watch recruitment"\n',
            encoding="utf-8",
        )
        self.state_dir.mkdir()
        (self.state_dir / "broken.txt").write_text("Known good\n", encoding="utf-8")

        def fetch(url):
            if url.endswith("broken"):
                raise TimeoutError("fetch timed out")
            return "<p>Working</p>"

        error = StringIO()
        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", side_effect=fetch),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(error),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
        self.assertIn("broken [fetch]: TimeoutError: fetch timed out", error.getvalue())
        self.assertEqual(
            output.getvalue(),
            "working: baseline saved\n"
            "summary: checked=1 changed=0 ai=0 notified=0 review=0 failed=1\n",
        )
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

    def test_console_request_and_strict_decision(self):
        response = BytesIO(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "  IGNORE\n"},
                        }
                    ]
                }
            ).encode("utf-8")
        )
        with (
            patch.dict(
                pagewatch.os.environ,
                {
                    "OPENCODE_MODEL": "glm-5.1",
                    "OPENCODE_API_KEY": "test-secret",
                },
            ),
            patch.object(pagewatch, "urlopen", return_value=response) as open_url,
        ):
            decision = pagewatch.classify_change(
                "course",
                "https://example.com/course",
                "Watch recruitment",
                "+Places open",
            )
        self.assertEqual(decision, "IGNORE")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, pagewatch.CONSOLE_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(request.get_header("User-agent"), "pagewatch-ai-lite/0.1")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 30)
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "glm-5.1")
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("untrusted", payload["messages"][0]["content"])
        context = json.loads(payload["messages"][1]["content"])
        self.assertEqual(context["target_id"], "course")
        self.assertEqual(context["url"], "https://example.com/course")
        self.assertEqual(context["intent"], "Watch recruitment")
        self.assertEqual(context["untrusted_diff"], "+Places open")
        self.assertNotIn("test-secret", request.data.decode("utf-8"))

    def test_console_rejects_invalid_decision_and_incomplete_reply(self):
        for content, finish_reason in [("IGNORE extra", "stop"), ("IGNORE", "length")]:
            response = BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": finish_reason,
                                "message": {"content": content},
                            }
                        ]
                    }
                ).encode("utf-8")
            )
            with (
                patch.dict(
                    pagewatch.os.environ,
                    {
                        "OPENCODE_MODEL": "glm-5.1",
                        "OPENCODE_API_KEY": "test-secret",
                    },
                ),
                patch.object(pagewatch, "urlopen", return_value=response),
            ):
                with self.assertRaises(ValueError):
                    pagewatch.classify_change(
                        "course", "https://example.com", "Watch recruitment", "+New"
                    )

        with (
            patch.dict(
                pagewatch.os.environ,
                {"OPENCODE_MODEL": "glm-5.1", "OPENCODE_API_KEY": "test-secret"},
            ),
            patch.object(pagewatch, "urlopen", return_value=BytesIO(b"not JSON")),
        ):
            with self.assertRaises(json.JSONDecodeError):
                pagewatch.classify_change(
                    "course", "https://example.com", "Watch recruitment", "+New"
                )

    def test_console_requires_credentials_before_request(self):
        with (
            patch.dict(pagewatch.os.environ, {"OPENCODE_MODEL": "glm-5.1"}, clear=True),
            patch.object(pagewatch, "urlopen") as open_url,
        ):
            with self.assertRaisesRegex(ValueError, "OPENCODE_API_KEY"):
                pagewatch.classify_change(
                    "course", "https://example.com", "Watch recruitment", "+New"
                )
        open_url.assert_not_called()

    def test_notification_uses_starttls_and_contains_change(self):
        settings = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "account@example.com",
            "SMTP_PASSWORD": "test-secret",
            "SMTP_FROM": "watcher@example.com",
            "SMTP_TO": "reader@example.com",
        }
        with (
            patch.dict(pagewatch.os.environ, settings, clear=True),
            patch.object(pagewatch.smtplib, "SMTP") as smtp,
        ):
            diff = "".join(
                difflib.unified_diff(
                    ["Course\n", "Places closed\n", "Apply today\n"],
                    ["Course\n", "Places open\n", "Apply today\n"],
                    fromfile="course: previous",
                    tofile="course: current",
                )
            )
            pagewatch.send_notification(
                "course",
                "https://example.com/course",
                "NOTIFY",
                diff,
            )
        smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
        server = smtp.return_value.__enter__.return_value
        self.assertIsInstance(
            server.starttls.call_args.kwargs["context"], pagewatch.ssl.SSLContext
        )
        server.login.assert_called_once_with("account@example.com", "test-secret")
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["Subject"], "[PageWatch] NOTIFY: course")
        self.assertEqual(message["From"], "watcher@example.com")
        self.assertEqual(message["To"], "reader@example.com")
        body = message.get_content()
        self.assertIn("Target: course", body)
        self.assertIn("Page:\nhttps://example.com/course", body)
        self.assertIn("Before:\nPlaces closed", body)
        self.assertIn("Now:\nPlaces open", body)
        self.assertIn("Context:\nCourse\nApply today", body)
        self.assertNotIn("Reason:", body)
        self.assertNotIn("--- ", body)
        self.assertNotIn("+++ ", body)
        self.assertNotIn("@@ ", body)
        self.assertNotIn("-Places closed", body)
        self.assertNotIn("+Places open", body)

    def test_change_details_for_addition_removal_and_multiple_hunks(self):
        addition = "".join(
            difflib.unified_diff(["Course\n"], ["Course\n", "Places open\n"])
        )
        details = pagewatch.format_change_details(addition)
        self.assertIn("Added:\nPlaces open", details)
        self.assertIn("Context:\nCourse", details)
        self.assertNotIn("Before:", details)
        self.assertNotIn("Change 1", details)

        removal = "".join(
            difflib.unified_diff(["Course\n", "Places closed\n"], ["Course\n"])
        )
        details = pagewatch.format_change_details(removal)
        self.assertIn("Removed:\nPlaces closed", details)
        self.assertNotIn("Now:", details)

        previous = [f"Line {number}\n" for number in range(20)]
        current = previous.copy()
        current[1] = "First change\n"
        current[18] = "Second change\n"
        details = pagewatch.format_change_details(
            "".join(difflib.unified_diff(previous, current))
        )
        self.assertIn("Change 1\n\nBefore:\nLine 1\n\nNow:\nFirst change", details)
        self.assertIn("Change 2\n\nBefore:\nLine 18\n\nNow:\nSecond change", details)
        self.assertLess(details.index("Change 1"), details.index("Change 2"))

    def test_independent_edits_within_one_hunk_remain_separate(self):
        previous = [
            "Course\n",
            "old application notice\n",
            "context one\n",
            "context two\n",
            "context three\n",
            "context four\n",
            "End\n",
        ]
        current = [
            "Course\n",
            "context one\n",
            "context two\n",
            "context three\n",
            "context four\n",
            "new tuition notice\n",
            "End\n",
        ]
        diff = "".join(difflib.unified_diff(previous, current))
        self.assertEqual(diff.count("\n@@ "), 1)
        details = pagewatch.format_change_details(diff)
        self.assertIn("Change 1\n\nRemoved:\nold application notice", details)
        self.assertIn("Change 2\n\nAdded:\nnew tuition notice", details)
        self.assertIn("Context:\nCourse\ncontext one", details)
        self.assertIn("Context:\ncontext four\nEnd", details)
        self.assertNotIn("Before:", details)
        self.assertNotIn("Now:", details)

    def test_long_replacement_exposes_difference_near_end(self):
        shared_prefix = "A" * 2500
        diff = "".join(
            difflib.unified_diff(
                [shared_prefix + "APPLICATION CLOSED\n"],
                [shared_prefix + "APPLICATION OPEN\n"],
            )
        )
        details = pagewatch.format_change_details(diff)
        before, now = details.split("\n\nNow:\n", 1)
        self.assertIn("Before:\n…", before)
        self.assertIn("APPLICATION CLOSED", before)
        self.assertTrue(now.startswith("…"))
        self.assertIn("APPLICATION OPEN", now)
        self.assertIn("[Change details truncated; open the page", details)
        self.assertLess(len(details), 4_100)

    def test_change_details_are_bounded_with_explicit_truncation(self):
        diff = "".join(
            difflib.unified_diff(["A" * 20_000 + "\n"], ["B" * 20_000 + "\n"])
        )
        details = pagewatch.format_change_details(diff)
        self.assertIn("Before:\n" + "A" * 100, details)
        self.assertIn("Now:\n" + "B" * 100, details)
        self.assertIn("[Change details truncated; open the page", details)
        self.assertLess(len(details), 4_100)

    def test_main_loads_local_env_without_overriding_shell(self):
        (self.root / ".env").write_text(
            "OPENCODE_MODEL=file-model\nOPENCODE_API_KEY=file-key\n",
            encoding="utf-8",
        )
        with (
            patch.object(pagewatch, "__file__", str(self.root / "pagewatch.py")),
            patch.object(pagewatch.sys, "argv", ["pagewatch.py"]),
            patch.object(pagewatch, "run", return_value=0) as run,
            patch.dict(
                pagewatch.os.environ, {"OPENCODE_MODEL": "shell-model"}, clear=True
            ),
        ):
            self.assertEqual(pagewatch.main(), 0)
            self.assertEqual(pagewatch.os.environ["OPENCODE_MODEL"], "shell-model")
            self.assertEqual(pagewatch.os.environ["OPENCODE_API_KEY"], "file-key")
        run.assert_called_once_with(Path("config.toml"), Path(".state"))

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

    def test_failed_state_save_after_notification_keeps_previous_state(self):
        self.state_dir.mkdir()
        baseline = self.state_dir / "course.txt"
        baseline.write_text("Known good\n", encoding="utf-8")
        error = StringIO()
        output = StringIO()
        with (
            patch.object(pagewatch, "fetch_page", return_value="<p>New</p>"),
            patch.object(pagewatch, "classify_change", return_value="NOTIFY"),
            patch.object(pagewatch, "send_notification") as notify,
            patch.object(
                pagewatch.os, "replace", side_effect=OSError("replace failed")
            ),
            contextlib.redirect_stderr(error),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(pagewatch.run(self.config, self.state_dir), 1)
        notify.assert_called_once()
        self.assertIn("course [save state]: OSError: replace failed", error.getvalue())
        self.assertEqual(
            output.getvalue(),
            "summary: checked=1 changed=1 ai=1 notified=1 review=0 failed=1\n",
        )
        self.assertEqual(baseline.read_text(encoding="utf-8"), "Known good\n")
        self.assertEqual(list(self.state_dir.iterdir()), [baseline])


if __name__ == "__main__":
    unittest.main()
