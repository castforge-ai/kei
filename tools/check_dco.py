"""Check that every commit between two revisions carries a Signed-off-by line (the Developer Certificate of Origin in
CONTRIBUTING.md). Merge commits are skipped. Usage: python tools/check_dco.py <base> <head> [--repo <folder>].

A sign-off is a trailer line `Signed-off-by: Name <address>`. The line names the person who certifies the commit; it
need not match the author, since a maintainer may sign off a contribution they carry, but it must have a name and an
address. Exit 0 when every commit has one, 1 with each commit that has none, 2 when git cannot list the commits.
"""
from __future__ import annotations

import re
import subprocess
import sys

SIGN_OFF = re.compile(r"^Signed-off-by: +\S.*<[^<>@\s]+@[^<>\s]+>\s*$", re.M)


def missing(base: str, head: str, repo: str = ".") -> list[str]:
    """The commits in base..head (no merges) whose message has no Signed-off-by line, as 'sha subject'."""
    revs = subprocess.run(["git", "-C", repo, "rev-list", "--no-merges", f"{base}..{head}"], capture_output=True,
                          text=True, check=True).stdout.split()
    out = []
    for c in revs:
        body = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B", c], capture_output=True, text=True,
                              check=True).stdout
        if not SIGN_OFF.search(body):
            out.append(f"{c[:12]} {body.strip().splitlines()[0] if body.strip() else '(no message)'}")
    return out


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="every commit in base..head carries a Signed-off-by line")
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    try:
        bad = missing(a.base, a.head, a.repo)
    except subprocess.CalledProcessError as e:
        print(f"git could not list the commits: {(e.stderr or '').strip()}")
        return 2
    for line in bad:
        print(f"no Signed-off-by line: {line}")
    if bad:
        print("Sign off with `git commit -s` (see CONTRIBUTING.md); for commits already made, "
              "`git rebase --signoff <base>` and push again.")
        return 1
    print("every commit is signed off")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
