# Quickstart

1. Install the command, with Python 3.12 or newer: `pipx install kei-animator` (or `uv tool install kei-animator`).
2. Check the setup: `kei doctor`. Each line is ok, warn or fail, with the fix.
3. See the tools work with no agent and no subscription: `kei demo`. It renders, checks and draws an approved walk in
   about 40 seconds.
4. Install the skill for your agent: `kei skill install` (Claude Code) or `kei skill install --agent codex`.
5. In the folder where your shots will live, ask your agent for an animation, for example "animate a mannequin
   running". The agent runs `kei init` the first time.

A real shot runs for hours, not minutes: the benchmark shots took 8 to 13 hours, with several agent tries and
reviews at each stage. The shot stops when it needs you, and `kei status` says why.

When the shot is delivered, watch it with `kei review <shot>`, or send it to someone else with `kei pack <shot>`.
Sign it off with `kei approve`, or send it back with a note in your own words.

Next: [the twelve stages](stages.md), or [troubleshooting](troubleshooting.md) when a shot stops.
