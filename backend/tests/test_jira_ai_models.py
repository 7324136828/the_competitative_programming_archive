import unittest
from unittest.mock import patch

from backend.jira.services.ai.client import resolve_model


class JiraAiModelResolutionTests(unittest.TestCase):
    def test_configured_default_is_selected_when_connector_reports_it(self):
        with patch(
            "backend.jira.services.ai.client.resolve_configured_model",
            return_value={"model": "preferred", "modelSource": "settings"},
        ):
            result = resolve_model(
                available_models=[{"id": "first"}, {"id": "preferred"}]
            )

        self.assertEqual(result, {"model": "preferred", "modelSource": "settings"})

    def test_first_connector_model_is_selected_when_default_is_missing(self):
        with patch(
            "backend.jira.services.ai.client.resolve_configured_model",
            return_value={"model": "missing-default", "modelSource": "default"},
        ):
            result = resolve_model(
                available_models=[{"id": "first"}, {"id": "second"}]
            )

        self.assertEqual(result, {"model": "first", "modelSource": "connector"})

    def test_configured_fallback_is_retained_when_connector_is_unavailable(self):
        configured = {"model": "offline-default", "modelSource": "settings"}
        with (
            patch(
                "backend.jira.services.ai.client.resolve_configured_model",
                return_value=configured,
            ),
            patch(
                "backend.jira.services.ai.client.list_models",
                side_effect=RuntimeError("offline"),
            ),
        ):
            result = resolve_model()

        self.assertEqual(result, configured)


if __name__ == "__main__":
    unittest.main()
