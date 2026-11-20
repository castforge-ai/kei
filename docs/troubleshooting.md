# Troubleshooting by status

`kei status <shot>` prints the status, the reason in plain words and the next command. `kei status <shot> --json`
gives the same for a script. Each status below says what it means and what to do.

| Status | Exit code | What it means | What to do |
|---|---|---|---|
| `running` | 0 | Kei is working on the shot, or a run was stopped mid-stage | `kei run <shot>` goes on where it stopped |
| `needs_answer` | 3 | a stage or a critic asked a question only a person can settle | `kei answer <shot> --text "..."`, then `kei run <shot>` |
| `needs_human` | 2 | the stage reached its limit of tries or send-backs, or a person must act (an asset Kei made dirty, a fit to approve) | read `kei status`; `kei retry <shot>` gives the stage new tries |
| `needs_approval` | 4 | the shot is delivered and waits for your sign-off | `kei review <shot>`, then `kei approve <shot>` or `kei note <shot> --text "..."` |
| `done` | 0 | you signed the shot off | a later `kei note` withdraws the approval and reopens it |
| `rejected` | 0 | the shot was dropped or rejected | a later `kei note` reopens it |
| `paused_usage` | 5 | a seat hit a usage limit; the pause costs no try | wait for the reset, then `kei run <shot>`; `--wait-on-limit` waits for you |
| `paused_machine` | 5 | a seat could not start, a critic failed twice (a crash, a timeout or no verdict), or Maya or Unreal stopped answering | fix what `kei status` names (often `kei doctor` shows it), then `kei run <shot>` |

Common causes:

- **A seat program is missing or has a bad flag.** `kei doctor` names it and its fix.
- **Unreal does not answer.** `kei unreal check` reads the project and asks the editor; start the editor with
  `-StartMCPServer` or click the Claireon button.
- **A flag you do not understand.** `kei check <shot> <pass> --explain <flag>` prints its measure, frames, value
  and limits.
- **Two runs on one shot.** The second stops at once: `.kei/run.lock` holds the shot while a run works on it, and a
  lock left by a closed run is taken over.
