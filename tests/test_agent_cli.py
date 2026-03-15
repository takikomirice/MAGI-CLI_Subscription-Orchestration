from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from magi.cli import _apply_agent_provider_selection, _parse_agent_mode_payload
from magi.config import load_config


class AgentCLITests(unittest.TestCase):
    def test_apply_agent_provider_selection_defaults_to_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(Path(tmp))

            selected, synth_provider, model_overrides, effort_overrides = _apply_agent_provider_selection(
                config,
                None,
                "gemini",
                {},
                {},
                "",
                "",
                "",
                emit=lambda message: None,
            )

            self.assertEqual(selected, {"codex"})
            self.assertIsNone(synth_provider)
            self.assertEqual(model_overrides, {})
            self.assertEqual(effort_overrides, {})

    def test_parse_agent_mode_payload_selects_provider_model_effort_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(Path(tmp))

            payload, selected, synth_provider, model_overrides, effort_overrides = _parse_agent_mode_payload(
                "gemini gemini-3.1-pro-preview high implement the assigned task",
                config,
                None,
                None,
                {},
                {},
            )

            self.assertEqual(payload, "implement the assigned task")
            self.assertEqual(selected, {"gemini"})
            self.assertIsNone(synth_provider)
            self.assertEqual(model_overrides["gemini"], "gemini-3.1-pro-preview")
            self.assertEqual(effort_overrides["gemini"], "high")


if __name__ == "__main__":
    unittest.main()
