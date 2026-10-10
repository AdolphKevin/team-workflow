#!/usr/bin/env python3
"""Read-only project configuration and delivery-material checks, not business tests."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


RISKS = {"authorization", "persistence", "concurrency", "messaging", "public-contract", "cross-service"}
STATUSES = {"passed", "failed", "skipped", "not-run"}
DISPOSITIONS = {"none", "reused", "updated", "added"}


class InputError(Exception):
    pass


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise InputError(f"Cannot read JSON from {path}: {exc}") from exc


class Check:
    def __init__(self, root):
        self.root = root.resolve()
        self.problems = []

    def problem(self, field, message):
        self.problems.append({"field": field, "message": message})

    def obj(self, value, field, keys=None):
        if not isinstance(value, dict):
            self.problem(field, "Expected an object")
            return {}
        if keys is not None:
            for key in sorted(set(value) - set(keys)):
                self.problem(f"{field}.{key}", "Unknown field")
            for key in sorted(set(keys) - set(value)):
                self.problem(f"{field}.{key}", "Required field is missing")
        return value

    def text(self, value, field):
        if not isinstance(value, str) or not value.strip():
            self.problem(field, "Expected non-empty text")
            return ""
        return value

    def strings(self, value, field, nonempty=False):
        if not isinstance(value, list):
            self.problem(field, "Expected an array")
            return []
        result = [self.text(item, f"{field}[{i}]") for i, item in enumerate(value)]
        if nonempty and not result:
            self.problem(field, "At least one item is required")
        if len(set(result)) != len(result):
            self.problem(field, "Duplicate items are not allowed")
        return result

    def rows(self, value, field):
        if not isinstance(value, list) or not value:
            self.problem(field, "Expected a non-empty array")
            return []
        return value

    def file(self, value, field):
        name = self.text(value, field)
        if not name:
            return
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            self.problem(field, "Use a path inside the project")
            return
        try:
            target = (self.root / path).resolve()
            if not target.is_relative_to(self.root):
                self.problem(field, "Path resolves outside the project")
            elif not target.is_file() or target.stat().st_size == 0:
                self.problem(field, "File is missing or empty")
            else:
                with target.open("rb") as stream:
                    stream.read(1)
        except (OSError, RuntimeError, ValueError) as exc:
            self.problem(field, f"Cannot read file: {exc}")

    def version(self, value, field):
        if type(value) is not int or value != 1:
            self.problem(field, "Only schema_version 1 is supported")

    def references(self, value, field, known, nonempty=False):
        values = self.strings(value, field, nonempty)
        for item in values:
            if item not in known:
                self.problem(field, f"Unknown check: {item}")
        return values

    def profile(self, value):
        data = self.obj(value, "profile", {
            "schema_version", "project", "context", "knowledge", "checks", "required_checks", "risk_checks"
        })
        self.version(data.get("schema_version"), "profile.schema_version")
        self.text(data.get("project"), "profile.project")
        for i, path in enumerate(self.strings(data.get("context"), "profile.context", True)):
            self.file(path, f"profile.context[{i}]")
        knowledge = self.obj(data.get("knowledge"), "profile.knowledge", {"provider", "entry"})
        if knowledge.get("provider") != "cs":
            self.problem("profile.knowledge.provider", "Only the CS knowledge adapter is currently supported")
        self.file(knowledge.get("entry"), "profile.knowledge.entry")
        checks = self.obj(data.get("checks"), "profile.checks")
        for key, row in checks.items():
            label = f"profile.checks.{key}"
            if not re.fullmatch(r"[a-z][a-z0-9-]*", key):
                self.problem(label, "Use a lowercase check identifier")
            item = self.obj(row, label, {"argv", "purpose"})
            # Repeated command arguments are valid; this is not a set of identifiers.
            args = item.get("argv")
            if not isinstance(args, list) or not args:
                self.problem(f"{label}.argv", "Expected a non-empty command argument array")
            else:
                for i, arg in enumerate(args):
                    self.text(arg, f"{label}.argv[{i}]")
            self.text(item.get("purpose"), f"{label}.purpose")
        self.references(data.get("required_checks"), "profile.required_checks", checks)
        risks = self.obj(data.get("risk_checks"), "profile.risk_checks")
        for risk, ids in risks.items():
            if risk not in RISKS:
                self.problem(f"profile.risk_checks.{risk}", "Unknown risk")
            self.references(ids, f"profile.risk_checks.{risk}", checks, True)
        return data

    def result(self, value, field, revision, with_id=False):
        keys = {"status", "revision", "artifact"}
        if with_id:
            keys.add("id")
        row = self.obj(value, field, keys)
        status = row.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            self.problem(f"{field}.status", "Unknown check status")
        elif status != "passed":
            self.problem(f"{field}.status", f"Check has not passed: {status}")
        if row.get("revision") != revision:
            self.problem(f"{field}.revision", "Evidence does not match the expected revision")
        self.file(row.get("artifact"), f"{field}.artifact")
        return row

    def delivery(self, value, profile, revision):
        data = self.obj(value, "report", {
            "schema_version", "project", "revision", "task", "risks", "acceptance", "checks", "review", "knowledge"
        })
        self.version(data.get("schema_version"), "report.schema_version")
        if data.get("project") != profile.get("project"):
            self.problem("report.project", "Project does not match the configuration")
        if data.get("revision") != revision:
            self.problem("report.revision", "Report does not match the expected revision")
        task = self.obj(data.get("task"), "report.task", {"reference", "goal", "non_goals"})
        self.text(task.get("reference"), "report.task.reference")
        self.text(task.get("goal"), "report.task.goal")
        self.strings(task.get("non_goals"), "report.task.non_goals")
        required = set(profile["required_checks"])
        for risk in self.strings(data.get("risks"), "report.risks"):
            if risk not in RISKS:
                self.problem("report.risks", f"Unknown risk: {risk}")
            elif risk not in profile["risk_checks"]:
                self.problem("report.risks", f"Project has no checks defined for risk: {risk}")
            else:
                required.update(profile["risk_checks"][risk])
        results = set()
        for i, raw in enumerate(self.rows(data.get("checks"), "report.checks")):
            field = f"report.checks[{i}]"
            row = self.result(raw, field, revision, with_id=True)
            key = self.text(row.get("id"), f"{field}.id")
            if key not in profile["checks"]:
                self.problem(f"{field}.id", "Check is not configured for this project")
            if key in results:
                self.problem(f"{field}.id", "Duplicate check result")
            results.add(key)
        acceptance_ids = set()
        for i, raw in enumerate(self.rows(data.get("acceptance"), "report.acceptance")):
            field = f"report.acceptance[{i}]"
            row = self.obj(raw, field, {"id", "expectation", "checks"})
            key = self.text(row.get("id"), f"{field}.id")
            if key in acceptance_ids:
                self.problem(f"{field}.id", "Duplicate acceptance identifier")
            acceptance_ids.add(key)
            self.text(row.get("expectation"), f"{field}.expectation")
            required.update(self.references(row.get("checks"), f"{field}.checks", profile["checks"], True))
        for key in sorted(required - results):
            self.problem("report.checks", f"Required result is missing: {key}")
        self.result(data.get("review"), "report.review", revision)
        knowledge = self.obj(data.get("knowledge"), "report.knowledge", {"provider", "task_note", "disposition", "reason"})
        if knowledge.get("provider") != "cs":
            self.problem("report.knowledge.provider", "Expected CS task record")
        self.file(knowledge.get("task_note"), "report.knowledge.task_note")
        disposition = knowledge.get("disposition")
        if not isinstance(disposition, str) or disposition not in DISPOSITIONS:
            self.problem("report.knowledge.disposition", "Unknown knowledge disposition")
        self.text(knowledge.get("reason"), "report.knowledge.reason")

    def git(self, *args):
        try:
            result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InputError(f"Cannot read Git state: {exc}") from exc
        if result.returncode:
            raise InputError("Cannot read Git state; use a repository with an existing commit")
        return result.stdout.strip()

    def source(self, revision):
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision):
            raise InputError("--revision requires a full Git commit identifier")
        if Path(self.git("rev-parse", "--show-toplevel")).resolve() != self.root:
            self.problem("source.root", "--root must be the Git repository root")
        if self.git("rev-parse", "HEAD") != revision:
            self.problem("source.revision", "Current checkout does not match the expected revision")
        if self.git("status", "--porcelain=v1", "--untracked-files=normal"):
            self.problem("source.workspace", "Uncommitted changes exist; final revision evidence is not current")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["project", "delivery"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--profile", type=Path, help="Defaults to <root>/.team-workflow.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--revision")
    args = parser.parse_args(argv)
    check = Check(args.root)
    scope = "delivery-material-only" if args.mode == "delivery" else "project-configuration-only"
    try:
        if not check.root.is_dir():
            raise InputError("Project root does not exist")
        profile_path = args.profile or check.root / ".team-workflow.json"
        if not profile_path.is_absolute():
            profile_path = check.root / profile_path
        profile = check.profile(load_json(profile_path))
        if args.mode == "delivery":
            if not args.report or not args.revision:
                raise InputError("delivery requires --report and --revision")
            check.source(args.revision)
            report_path = args.report if args.report.is_absolute() else check.root / args.report
            report = load_json(report_path)
            if not check.problems:
                check.delivery(report, profile, args.revision)
        print(json.dumps({"ok": not check.problems, "scope": scope, "business_validation": "not-performed", "problems": check.problems}, ensure_ascii=False, indent=2))
        return 1 if check.problems else 0
    except InputError as exc:
        print(json.dumps({"ok": False, "scope": scope, "business_validation": "not-performed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
