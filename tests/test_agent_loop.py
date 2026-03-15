from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from magi.config import load_config
from magi.pipeline import run_request


class AgentLoopTests(unittest.TestCase):
    def test_agent_loop_retries_after_failed_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / ".magi.toml").write_text(
                textwrap.dedent(
                    """
                    project_name = "agent-loop-test"
                    runs_dir = "runs"

                    [agent]
                    max_attempts = 3
                    verification_timeout_seconds = 30
                    verification_commands = [
                      ["python", "-c", "import os, sys; attempt = int(os.environ['MAGI_AGENT_ATTEMPT']); print(f'attempt={attempt}'); sys.exit(0 if attempt >= 2 else 1)"],
                    ]
                    """
                ).strip(),
                encoding="utf-8",
            )
            config = load_config(project_root)

            artifacts = run_request(
                config,
                "Implement the requested change.",
                mode="agent",
                selected_providers={"codex"},
            )

            report_text = artifacts.report_path.read_text(encoding="utf-8", errors="replace")
            prompt_text = (artifacts.run_dir / "agent_attempt_02" / "prompt.md").read_text(
                encoding="utf-8",
                errors="replace",
            )
            verification_one = (artifacts.run_dir / "agent_attempt_01" / "verification.yaml").read_text(
                encoding="utf-8",
                errors="replace",
            )
            verification_two = (artifacts.run_dir / "agent_attempt_02" / "verification.yaml").read_text(
                encoding="utf-8",
                errors="replace",
            )

            self.assertIn("- agent_attempts: 2/3", report_text)
            self.assertIn("- agent_verification: passed", report_text)
            self.assertIn("<MAGI_VERIFICATION_FEEDBACK>", prompt_text)
            self.assertIn("Attempt 1 verification failed.", prompt_text)
            self.assertIn("exit_code: 1", verification_one)
            self.assertIn("exit_code: 0", verification_two)

    def test_agent_loop_falls_back_to_parallel_advisory_when_multiple_providers_are_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / ".magi.toml").write_text(
                textwrap.dedent(
                    """
                    project_name = "agent-loop-test"
                    runs_dir = "runs"

                    [agent]
                    max_attempts = 3
                    verification_timeout_seconds = 30
                    verification_commands = [
                      ["python", "-c", "import sys; sys.exit(0)"],
                    ]
                    """
                ).strip(),
                encoding="utf-8",
            )
            config = load_config(project_root)

            artifacts = run_request(
                config,
                "Implement the requested change.",
                mode="agent",
            )

            report_text = artifacts.report_path.read_text(encoding="utf-8", errors="replace")

            self.assertEqual(len(artifacts.advisor_paths), 3)
            self.assertFalse((artifacts.run_dir / "agent_attempt_01").exists())
            self.assertNotIn("## Agent Loop", report_text)

    def test_agent_mode_ignores_synth_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config = load_config(project_root)

            artifacts = run_request(
                config,
                "Implement the requested change.",
                mode="agent",
                selected_providers={"codex"},
                synth_provider="gemini",
            )

            request_text = artifacts.request_path.read_text(encoding="utf-8", errors="replace")
            report_text = artifacts.report_path.read_text(encoding="utf-8", errors="replace")

            self.assertIsNone(artifacts.synthesizer_path)
            self.assertIn('synth_provider: ""', request_text)
            self.assertNotIn("- synthesizer:", report_text)


if __name__ == "__main__":
    unittest.main()
