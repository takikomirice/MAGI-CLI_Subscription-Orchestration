from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from magi.config import load_config
from magi.pipeline import run_request


class PlanFileTests(unittest.TestCase):
    def test_plan_mode_writes_project_plan_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config = load_config(project_root)

            artifacts = run_request(
                config,
                "Create a detailed implementation plan.",
                mode="plan",
                selected_providers={"codex"},
            )

            plan_path = project_root / "plan.md"
            plan_text = plan_path.read_text(encoding="utf-8", errors="replace")

            self.assertTrue(plan_path.exists())
            self.assertIn("# Project Plan", plan_text)
            self.assertIn(f"source_run_id: `{artifacts.run_id}`", plan_text)
            self.assertIn("## MAGI Plan", plan_text)
            self.assertIn("# MAGI Report", plan_text)

    def test_plan_mode_archives_previous_plan_and_reuses_it_as_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config = load_config(project_root)

            run_request(
                config,
                "Create the initial implementation plan.",
                mode="plan",
                selected_providers={"codex"},
            )
            original_plan = (project_root / "plan.md").read_text(encoding="utf-8", errors="replace")

            second_artifacts = run_request(
                config,
                "Refine the implementation plan with better sequencing.",
                mode="plan",
                selected_providers={"codex"},
            )

            prompt_text = second_artifacts.advisor_paths[0].read_text(encoding="utf-8", errors="replace")
            archive_dir = project_root / "plans" / "archive"

            self.assertTrue(archive_dir.exists())
            self.assertTrue(any(archive_dir.iterdir()))
            self.assertIn("<MAGI_PROJECT_PLAN>", prompt_text)
            self.assertIn(original_plan.splitlines()[0], prompt_text)


if __name__ == "__main__":
    unittest.main()
