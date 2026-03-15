from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from magi.config import load_config
from magi.pipeline import run_request
from magi.runs import resolve_handoff_context


class HandoffTests(unittest.TestCase):
    def test_last_plan_selector_skips_newer_non_plan_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config = load_config(project_root)

            plan_artifacts = run_request(
                config,
                "Create the implementation plan.",
                mode="plan",
                selected_providers={"codex"},
            )
            run_request(
                config,
                "Ask a follow-up question.",
                mode="ask",
                selected_providers={"codex"},
            )

            handoff = resolve_handoff_context(config.runs_dir, "last-plan")

            self.assertEqual(handoff.run_id, plan_artifacts.run_id)
            self.assertEqual(handoff.mode, "plan")
            self.assertIn("# MAGI Report", handoff.report_markdown)

    def test_agent_run_includes_handoff_report_in_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config = load_config(project_root)

            plan_artifacts = run_request(
                config,
                "Plan the implementation in phases.",
                mode="plan",
                selected_providers={"codex"},
            )
            plan_report = plan_artifacts.report_path.read_text(encoding="utf-8", errors="replace").strip()

            agent_artifacts = run_request(
                config,
                "Implement the approved plan.",
                mode="agent",
                selected_providers={"codex"},
                handoff_selector="last-plan",
            )

            request_text = agent_artifacts.request_path.read_text(encoding="utf-8", errors="replace")
            advisor_text = agent_artifacts.advisor_paths[0].read_text(encoding="utf-8", errors="replace")

            self.assertIn("selector: last-plan", request_text)
            self.assertIn(f"run_id: {plan_artifacts.run_id}", request_text)
            self.assertIn("<MAGI_HANDOFF_REPORT>", advisor_text)
            self.assertIn(f"source_run_id: {plan_artifacts.run_id}", advisor_text)
            self.assertIn(plan_report.splitlines()[0], advisor_text)

    def test_last_selector_resolves_previous_run_not_current_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config = load_config(project_root)

            plan_artifacts = run_request(
                config,
                "Plan the implementation in phases.",
                mode="plan",
                selected_providers={"codex"},
            )

            agent_artifacts = run_request(
                config,
                "Implement the approved plan.",
                mode="agent",
                selected_providers={"codex"},
                handoff_selector="last",
            )

            request_text = agent_artifacts.request_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn("selector: last", request_text)
            self.assertIn(f"run_id: {plan_artifacts.run_id}", request_text)


if __name__ == "__main__":
    unittest.main()
