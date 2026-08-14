"""Unit tests for the generic fetch fallback utilities."""

from __future__ import annotations

import unittest
from unittest import mock

import requests

from fetch_utils import fetch_first_success, try_parsers


def _make_session(*responses):
    """Build a fake session whose get() returns responses in sequence."""
    session = mock.Mock()
    session.get.side_effect = responses
    return session


def _http_error():
    """A raise_for_status that raises the realistic requests.HTTPError."""
    return mock.Mock(side_effect=requests.HTTPError("boom"))


class TestFetchFirstSuccess(unittest.TestCase):
    def test_first_source_wins(self):
        session = _make_session(
            mock.Mock(ok=True, text="body-cnn", raise_for_status=lambda: None)
        )
        body, source = fetch_first_success(
            session,
            [("cnn", "http://cnn"), ("fallback", "http://fb")],
            timeout=10, retries=1, backoff=1.0,
        )
        self.assertEqual(body, "body-cnn")
        self.assertEqual(source, "cnn")

    def test_falls_back_when_first_fails(self):
        session = _make_session(
            mock.Mock(raise_for_status=_http_error()),
            mock.Mock(ok=True, text="body-fb", raise_for_status=lambda: None),
        )
        body, source = fetch_first_success(
            session,
            [("cnn", "http://cnn"), ("fb", "http://fb")],
            timeout=10, retries=1, backoff=1.0,
        )
        self.assertEqual(body, "body-fb")
        self.assertEqual(source, "fb")

    def test_all_sources_fail_raises(self):
        session = _make_session(
            mock.Mock(raise_for_status=_http_error()),
            mock.Mock(raise_for_status=_http_error()),
        )
        with self.assertRaises(RuntimeError):
            fetch_first_success(
                session,
                [("a", "http://a"), ("b", "http://b")],
                timeout=10, retries=1, backoff=1.0,
            )

    def test_retries_then_succeeds(self):
        with mock.patch("fetch_utils.time.sleep") as sleep:
            session = _make_session(
                mock.Mock(raise_for_status=_http_error()),
                mock.Mock(ok=True, text="body", raise_for_status=lambda: None),
            )
            body, source = fetch_first_success(
                session, [("a", "http://a")], timeout=10, retries=2, backoff=1.0
            )
        self.assertEqual(body, "body")
        self.assertEqual(source, "a")
        # backoff * 2**0 = 1.0 dopo il primo tentativo fallito
        sleep.assert_called_once_with(1.0)

    def test_validator_rejects_body_and_falls_back(self):
        # Prima fonte 200 ma il validatore la rifiuta (block page) → seconda
        def validate(name, body):
            return "ok" in body

        session = _make_session(
            mock.Mock(ok=True, text="block-page", raise_for_status=lambda: None),
            mock.Mock(ok=True, text="ok-body", raise_for_status=lambda: None),
        )
        body, source = fetch_first_success(
            session,
            [("a", "http://a"), ("b", "http://b")],
            timeout=10, retries=1, backoff=1.0,
            validate=validate,
        )
        self.assertEqual(body, "ok-body")
        self.assertEqual(source, "b")


class TestTryParsers(unittest.TestCase):
    def test_first_parser_wins(self):
        def p1(body):
            return {"from": "p1"}

        def p2(body):
            return {"from": "p2"}

        result, name = try_parsers("body", [("p1", p1), ("p2", p2)])
        self.assertEqual(result["from"], "p1")
        self.assertEqual(name, "p1")

    def test_falls_back_when_first_fails(self):
        def p1(body):
            raise ValueError("no")

        def p2(body):
            return {"from": "p2"}

        result, name = try_parsers("body", [("p1", p1), ("p2", p2)])
        self.assertEqual(result["from"], "p2")
        self.assertEqual(name, "p2")

    def test_all_parsers_fail_raises(self):
        def p1(body):
            raise ValueError("no")

        with self.assertRaises(ValueError):
            try_parsers("body", [("p1", p1)])


if __name__ == "__main__":
    unittest.main()
