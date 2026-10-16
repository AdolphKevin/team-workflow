#!/usr/bin/env python3
"""复用独立试用的本地平台接口；数据由 FAKE_PLATFORM_FILE 指定。"""
import json
import os
import subprocess
import sys

DATA = os.environ.get(
    "FAKE_PLATFORM_FILE",
    ".tw/local/platform.json",
)


def load():
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


def arg(name, argv):
    i = argv.index(name)
    return argv[i + 1]


def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def op_task(argv):
    tid = arg("--id", argv)
    data = load()
    rec = data["tasks"].get(tid)
    if rec is None:
        sys.stderr.write(f"task not found: {tid}\n")
        return 1
    items = list(rec["items"])
    head = [i for i in items if i["kind"] == "task"]
    rest = sorted((i for i in items if i["kind"] != "task"),
                  key=lambda i: (i["created_at"], i["url"]))
    out({
        "id": tid,
        "url": tid,
        "repository": rec["repository"],
        "state": rec["state"],
        "owners": rec["owners"],
        "items": head + rest,
        "raw": rec,
    })
    return 0


def op_commit(argv):
    rev = arg("--revision", argv)
    r = git("log", "-1", "--format=%an <%ae>%x00%aI", rev, "--")
    if r.returncode != 0 or not r.stdout.strip():
        out({"exists": False, "revision": rev, "author": None, "time": None})
        return 0
    author, when = r.stdout.strip().split("\x00")
    out({"exists": True, "revision": rev, "author": author, "time": when})
    return 0


def op_reference(argv):
    url = arg("--url", argv)
    data = load()
    for tid, rec in data["tasks"].items():
        if url == tid:
            out({"reachable": True, "kind": "task"})
            return 0
        for item in rec["items"]:
            if item["url"] == url:
                kind = {"task": "task", "change": "change"}.get(item["kind"], "comment")
                out({"reachable": True, "kind": kind})
                return 0
    for marker, kind in (("/commit/", "commit"), ("/blob/", "file")):
        if marker in url:
            tail = url.split(marker, 1)[1]
            rev = tail.split("/", 1)[0]
            ok = git("cat-file", "-e", rev + "^{commit}").returncode == 0
            if ok and kind == "file":
                path = tail.split("/", 1)[1].split("#", 1)[0]
                ok = git("cat-file", "-e", f"{rev}:{path}").returncode == 0
            res = {"reachable": ok, "kind": kind}
            if ok:
                res["revision"] = git("rev-parse", rev).stdout.strip()
            out(res)
            return 0
    out({"reachable": False, "kind": "comment"})
    return 0


def main(argv):
    if not argv:
        sys.stderr.write("missing operation\n")
        return 2
    op, rest = argv[0], argv[1:]
    handler = {"task": op_task, "commit": op_commit, "reference": op_reference}.get(op)
    if handler is None:
        sys.stderr.write(f"unsupported operation: {op}\n")
        return 2
    return handler(rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
