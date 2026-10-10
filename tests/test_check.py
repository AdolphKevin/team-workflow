import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/team-workflow/scripts/check.py"


class DeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.write(".gitignore", ".team-workflow/\n")
        self.write("AGENTS.md", "Project rules\n")
        self.write("app.py", "def greeting():\n    return 'hello'\n")
        self.write(".codestable/wiki/INDEX.md", "Knowledge entry\n")
        self.write(".codestable/wiki/task-notes/task.md", "Completed task; existing knowledge reused.\n")
        self.profile = {
            "schema_version": 1,
            "project": "sample-service",
            "context": ["AGENTS.md"],
            "knowledge": {"provider": "cs", "entry": ".codestable/wiki/INDEX.md"},
            "checks": {
                "unit": {"argv": ["python3", "-m", "unittest"], "purpose": "Check behavior"},
                "database": {"argv": ["make", "test-db"], "purpose": "Check persisted state"},
            },
            "required_checks": ["unit"],
            "risk_checks": {"persistence": ["database"]},
        }
        self.write(".team-workflow.json", json.dumps(self.profile))
        self.commit()
        self.revision = self.git("rev-parse", "HEAD").strip()
        # Test fixtures represent material presence, not real business-test results.
        self.write(".team-workflow/unit.log", "Synthetic unit result for checker tests.\n")
        self.write(".team-workflow/database.log", "Synthetic database result for checker tests.\n")
        self.write(".team-workflow/review.md", "Synthetic review artifact for checker tests.\n")
        self.report = {
            "schema_version": 1,
            "project": "sample-service",
            "revision": self.revision,
            "task": {"reference": "fixture-task", "goal": "Return a greeting", "non_goals": []},
            "risks": [],
            "acceptance": [{"id": "A1", "expectation": "Greeting is returned", "checks": ["unit"]}],
            "checks": [self.result("unit")],
            "review": {"status": "passed", "revision": self.revision, "artifact": ".team-workflow/review.md"},
            "knowledge": {"provider": "cs", "task_note": ".codestable/wiki/task-notes/task.md", "disposition": "none", "reason": "No new stable knowledge"},
        }

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True, stderr=subprocess.STDOUT)

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Workflow Test", "-c", "user.email=workflow-test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "Test fixture")

    def result(self, key, status="passed"):
        return {"id": key, "status": status, "revision": self.revision, "artifact": f".team-workflow/{key}.log"}

    def run_check(self, mode="delivery"):
        self.write(".team-workflow/delivery.json", json.dumps(self.report))
        command = [sys.executable, str(SCRIPT), mode, "--root", str(self.root)]
        if mode == "delivery":
            command += ["--report", ".team-workflow/delivery.json", "--revision", self.revision]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.stderr, "", result.stderr)
        return result.returncode, json.loads(result.stdout)

    def assert_blocked(self, field):
        code, result = self.run_check()
        self.assertEqual(code, 1, result)
        self.assertFalse(result["ok"])
        self.assertTrue(any(p["field"] == field for p in result["problems"]), result)

    def test_complete_materials_pass_without_claiming_business_validation(self):
        code, result = self.run_check()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["scope"], "delivery-material-only")
        self.assertEqual(result["business_validation"], "not-performed")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_required_database_result_cannot_be_replaced_by_unit_success(self):
        self.report["risks"] = ["persistence"]
        self.assert_blocked("report.checks")

    def test_skipped_failed_and_not_run_checks_do_not_pass(self):
        for status in ["skipped", "failed", "not-run"]:
            with self.subTest(status=status):
                self.report["checks"][0]["status"] = status
                self.assert_blocked("report.checks[0].status")

    def test_risk_without_project_validation_is_blocked(self):
        self.report["risks"] = ["authorization"]
        self.assert_blocked("report.risks")

    def test_persistence_materials_pass_when_all_required_results_exist(self):
        self.report["risks"] = ["persistence"]
        self.report["checks"].append(self.result("database"))
        self.report["acceptance"][0]["checks"].append("database")
        self.assertEqual(self.run_check()[0], 0)

    def test_old_evidence_and_review_are_rejected(self):
        self.report["checks"][0]["revision"] = "a" * 40
        self.report["review"]["revision"] = "b" * 40
        self.assert_blocked("report.checks[0].revision")
        self.assert_blocked("report.review.revision")

    def test_a_new_commit_invalidates_the_previous_report(self):
        self.write("app.py", "def greeting():\n    return 'changed'\n")
        self.commit()
        self.assert_blocked("source.revision")

    def test_uncommitted_and_untracked_code_invalidate_final_revision_evidence(self):
        for path in ["app.py", "new_source.py"]:
            with self.subTest(path=path):
                self.write(path, "changed = True\n")
                self.assert_blocked("source.workspace")
                self.git("reset", "--hard", "HEAD")
                if path == "new_source.py":
                    (self.root / path).unlink()

    def test_missing_empty_and_external_artifacts_are_rejected(self):
        for name in [".team-workflow/missing.log", ".team-workflow/empty.log", "../outside.log"]:
            with self.subTest(name=name):
                self.write(".team-workflow/empty.log", "")
                self.report["checks"][0]["artifact"] = name
                self.assert_blocked("report.checks[0].artifact")

    def test_symlink_cannot_supply_evidence_from_outside_the_project(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "result.log"
            outside.write_text("External result\n")
            (self.root / ".team-workflow/linked.log").symlink_to(outside)
            self.report["checks"][0]["artifact"] = ".team-workflow/linked.log"
            self.assert_blocked("report.checks[0].artifact")

    def test_acceptance_must_reference_a_configured_and_reported_check(self):
        self.report["acceptance"][0]["checks"] = ["database"]
        self.assert_blocked("report.checks")
        self.report["acceptance"][0]["checks"] = ["invented"]
        self.assert_blocked("report.acceptance[0].checks")

    def test_unknown_schema_and_mistyped_fields_are_rejected(self):
        self.report["schema_version"] = 2
        self.report["check"] = self.report.pop("checks")
        self.assert_blocked("report.schema_version")
        self.assert_blocked("report.check")

    def test_malformed_objects_produce_findings_instead_of_crashing(self):
        original = copy.deepcopy(self.report)
        for field in ["task", "knowledge", "review"]:
            with self.subTest(field=field):
                self.report = copy.deepcopy(original)
                self.report[field] = []
                self.assert_blocked(f"report.{field}")

    def test_no_new_cards_is_a_valid_knowledge_disposition(self):
        self.assertEqual(self.run_check()[0], 0)
        self.report["knowledge"]["reason"] = ""
        self.assert_blocked("report.knowledge.reason")

    def test_project_check_does_not_execute_declared_commands(self):
        self.profile["checks"]["unit"]["argv"] = [sys.executable, "-c", "raise SystemExit('must not execute')"]
        self.write(".team-workflow.json", json.dumps(self.profile))
        code, result = self.run_check("project")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["scope"], "project-configuration-only")

    def test_invalid_json_is_an_input_error(self):
        self.write(".team-workflow.json", "{invalid json")
        code, result = self.run_check("project")
        self.assertEqual(code, 2, result)
        self.assertIn("Cannot read JSON", result["error"])

    def test_duplicate_results_cannot_supply_another_required_check(self):
        self.report["risks"] = ["persistence"]
        self.report["checks"].append(copy.deepcopy(self.report["checks"][0]))
        self.assert_blocked("report.checks[1].id")
        self.assert_blocked("report.checks")


if __name__ == "__main__":
    unittest.main()
