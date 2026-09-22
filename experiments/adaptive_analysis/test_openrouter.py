"""OpenRouter transport contract tests using HTTP mocks and a dummy key only."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

import httpx

from src import run_ai_scientists as client


class OpenRouterTransportTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.object(client, "OPENROUTER_KEY", "offline-dummy-key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    @staticmethod
    def response(body, status=200):
        return httpx.Response(
            status, json=body,
            request=httpx.Request("POST", client.OPENROUTER_URL),
        )

    @staticmethod
    def completion(**extra):
        return {
            "model": "provider/actual-model-version",
            "provider": "Example Provider",
            "id": "gen-offline-example",
            "choices": [{"message": {"content": '{"tool":"submit"}'},
                         "finish_reason": "stop", "native_finish_reason": "end_turn"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28,
                      "completion_tokens_details": {"reasoning_tokens": 5}},
            **extra,
        }

    def invoke(self, response=None, *, error=None, **options):
        output = io.StringIO()
        with patch.object(client.httpx, "post", return_value=response, side_effect=error) as post:
            with contextlib.redirect_stdout(output):
                result = client.call_openrouter("requested/model", "system", "user", 7, **options)
        return result, post.call_args, output.getvalue()

    def test_legacy_defaults_and_actual_response_identity(self):
        result, request, _ = self.invoke(self.response(self.completion()))
        self.assertEqual(request.args, (client.OPENROUTER_URL,))
        self.assertEqual(request.kwargs["json"], {
            "model": "requested/model",
            "messages": [{"role": "system", "content": "system"},
                         {"role": "user", "content": "user"}],
            "temperature": 0.7, "max_tokens": 4096,
        })
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer offline-dummy-key")
        self.assertEqual(request.kwargs["timeout"], 120.0)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["model"], "requested/model")
        self.assertEqual(result["actual_model"], "provider/actual-model-version")
        self.assertEqual(result["provider"], "Example Provider")
        self.assertEqual(result["generation_id"], "gen-offline-example")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["native_finish_reason"], "end_turn")
        self.assertEqual(result["usage"]["completion_tokens_details"]["reasoning_tokens"], 5)

    def test_reasoning_options_omit_temperature_and_preserve_length_usage(self):
        body = self.completion(choices=[{
            "message": {"content": None}, "finish_reason": "length",
            "native_finish_reason": "max_output_tokens",
        }])
        result, request, _ = self.invoke(
            self.response(body), temperature=None, max_tokens=16000, reasoning_effort="medium"
        )
        self.assertNotIn("temperature", request.kwargs["json"])
        self.assertEqual(request.kwargs["json"]["max_tokens"], 16000)
        self.assertEqual(request.kwargs["json"]["reasoning"], {"effort": "medium"})
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["content"])
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["usage"], body["usage"])

    def test_explicit_zero_temperature_and_missing_metadata(self):
        body = {"choices": [{"message": {"content": "ok"}}], "provider": {"name": "ignored"}}
        result, request, _ = self.invoke(self.response(body), temperature=0.0, max_tokens=2048)
        self.assertEqual(request.kwargs["json"]["temperature"], 0.0)
        self.assertNotIn("reasoning", request.kwargs["json"])
        for key in ("actual_model", "provider", "generation_id", "finish_reason", "native_finish_reason"):
            self.assertIsNone(result[key])
        self.assertEqual(result["usage"], {})

    def test_http_and_api_error_bodies_are_not_logged_or_returned(self):
        sentinel = "secret-in-error-body"
        for status, code in ((429, "http_error"), (200, "api_error")):
            with self.subTest(status=status):
                result, _, output = self.invoke(self.response({
                    "error": {"code": sentinel, "message": sentinel, "metadata": {"raw": sentinel}}
                }, status))
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["http_status"], status)
                self.assertEqual(result["error_code"], code)
                self.assertNotIn(sentinel, output + json.dumps(result))
                self.assertNotIn("offline-dummy-key", output + json.dumps(result))

    def test_choice_error_retains_generation_identity_but_not_error_text(self):
        sentinel = "secret-provider-error"
        body = self.completion(choices=[{
            "finish_reason": "error", "native_finish_reason": "provider_error",
            "error": {"message": sentinel},
        }])
        result, _, output = self.invoke(self.response(body))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "api_error")
        self.assertEqual(result["generation_id"], "gen-offline-example")
        self.assertEqual(result["actual_model"], "provider/actual-model-version")
        self.assertEqual(result["finish_reason"], "error")
        self.assertEqual(result["usage"], body["usage"])
        self.assertNotIn(sentinel, output + json.dumps(result))

    def test_error_and_malformed_completions_preserve_reported_usage(self):
        usage = {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42,
                 "cost": 0.007, "completion_tokens_details": {"reasoning_tokens": 28}}
        for body, code in (
            ({"error": {"message": "private-error"}, "usage": usage}, "api_error"),
            ({"choices": [], "usage": usage}, "invalid_response"),
            ({"choices": [{"message": {"content": []}}], "usage": usage}, "invalid_response"),
        ):
            with self.subTest(code=code, body=body):
                result, _, output = self.invoke(self.response(body))
                self.assertEqual(result["error_code"], code)
                self.assertEqual(result["usage"], usage)
                self.assertNotIn("private-error", output + json.dumps(result))

    def test_refusal_is_a_boolean_without_retaining_refusal_text(self):
        sentinel = "refusal-text-not-for-logging"
        for refusal in (sentinel, None, ""):
            with self.subTest(refusal=refusal):
                body = self.completion(choices=[{
                    "message": {"content": None, "refusal": refusal},
                    "finish_reason": "stop",
                }])
                result, _, output = self.invoke(self.response(body))
                self.assertIs(result["refusal"], bool(refusal))
                self.assertNotIn(sentinel, output + json.dumps(result))

    def test_exception_messages_and_malformed_responses_are_sanitized(self):
        sentinel = "secret-in-exception-message"
        for error, code in ((httpx.ReadTimeout(sentinel), "request_timeout"),
                            (httpx.ConnectError(sentinel), "request_error"),
                            (RuntimeError(sentinel), "unexpected_error")):
            with self.subTest(code=code):
                result, _, output = self.invoke(error=error)
                self.assertEqual(result["error_code"], code)
                self.assertIsNone(result["http_status"])
                self.assertNotIn(sentinel, output + json.dumps(result))
        for body in ({"choices": []}, {"choices": [{"message": sentinel}]}, [sentinel]):
            with self.subTest(body=body):
                result, _, output = self.invoke(self.response(body))
                self.assertEqual(result["error_code"], "invalid_response")
                self.assertEqual(result["http_status"], 200)
                self.assertNotIn(sentinel, output + json.dumps(result))


if __name__ == "__main__":
    unittest.main()
