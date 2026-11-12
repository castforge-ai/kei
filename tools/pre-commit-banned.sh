#!/bin/sh
# Banned-term gate: refuses any staged line or commit message that matches a term in the untracked list
# .local/banned_terms.txt.
#
# The terms are NOT in this file. They live in the untracked list
# .local/banned_terms.txt (one case-insensitive extended regex per line).
#
# Install (the same file serves both hooks):
#   cp tools/pre-commit-banned.sh .git/hooks/pre-commit
#   cp tools/pre-commit-banned.sh .git/hooks/commit-msg
#
# As pre-commit (no argument): checks the ADDED lines of the staged diff.
# As commit-msg (argument = message file): checks the commit message.
# Any match refuses the commit and names the file and line.
# A missing or empty list also refuses the commit (fail loud, never open).

ROOT=$(git rev-parse --show-toplevel) || exit 1
LIST="$ROOT/.local/banned_terms.txt"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t banned)
trap 'rm -rf "$TMP"' EXIT

# Strip comments, blank lines and CR from the list.
if [ ! -s "$LIST" ]; then
  echo "banned-terms: list missing or empty: $LIST. Commit refused." >&2
  exit 1
fi
sed -e 's/\r$//' -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' "$LIST" > "$TMP/pats"
if [ ! -s "$TMP/pats" ]; then
  echo "banned-terms: list has no patterns: $LIST. Commit refused." >&2
  exit 1
fi

if [ $# -ge 1 ]; then
  # commit-msg mode: ignore git's comment lines.
  if [ ! -r "$1" ]; then
    echo "banned-terms: cannot read the commit message file: $1. Commit refused." >&2
    exit 1
  fi
  sed -e 's/\r$//' "$1" | grep -v '^#' > "$TMP/msg"
  HITS=$(grep -n -i -E -f "$TMP/pats" "$TMP/msg")
  if [ -n "$HITS" ]; then
    echo "banned-terms: the commit message contains a banned term. Commit refused." >&2
    echo "$HITS" | sed 's/^/  message line /' >&2
    exit 1
  fi
  exit 0
fi


# pre-commit mode: collect added lines with "file<TAB>line" in a parallel map.
git diff --cached -U0 --no-color --no-ext-diff --diff-filter=ACMR | awk -v map="$TMP/map" -v txt="$TMP/txt" '
  /^\+\+\+ / { f = substr($0, 5); sub(/^b\//, "", f); next }
  /^--- /    { next }
  /^@@ /     { split($3, a, ","); n = substr(a[1], 2) + 0; next }
  /^\+/      { print f "\t" n > map; print substr($0, 2) > txt; n++; next }
'
[ -s "$TMP/txt" ] || exit 0

HITS=$(sed -e 's/\r$//' "$TMP/txt" | grep -n -i -E -f "$TMP/pats" | cut -d: -f1)
if [ -n "$HITS" ]; then
  echo "banned-terms: staged lines contain a banned term. Commit refused." >&2
  for i in $HITS; do
    loc=$(sed -n "${i}p" "$TMP/map")
    echo "  $(echo "$loc" | cut -f1):$(echo "$loc" | cut -f2)" >&2
  done
  echo "  Remove the term or replace it with a neutral name." >&2
  exit 1
fi
exit 0
