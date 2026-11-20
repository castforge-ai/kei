# Security

Kei runs AI agent command lines on your machine, with the permissions kei.toml gives them. Know what it does:

- **Seats.** The animator may write in the shot folder and the folder above it (`--add-dir ..`), and run the
  commands its `--allowedTools` list names: kei, ffmpeg, ffprobe, and python for the scripts in its `.kei/scratch/`
  folder only (no one-liners). A scratch script is still full Python, so this narrows and records what the animator
  runs rather than sandboxing it. Critics are read-only. Seats do not receive other
  services' credentials from your environment (GitHub, cloud, payment and database tokens are removed).
- **Shot state.** One `kei run` works on a shot at a time (`.kei/run.lock`). A running `kei run` takes a chat note
  from the shot's state file only when `kei note` signed it with the key in `~/.kei/note.key` (or `KEI_HOME`), so a
  seat that edits the state file cannot pass a note off as yours. A seat allowed to run any command can still read
  that key as you can: the signature stops an edit, not a determined forgery.
- **Local pages.** The live and review pages listen on 127.0.0.1 only, check the Host header and a per-run token, and
  refuse cross-origin writes. The review page's link works once: after the first load, a copy of it in a
  transcript or the browser history opens nothing, and the token the page posts with never appears in a URL. A
  change to an agent's command line from the page's Settings tab is saved only with a one-time code Kei prints in
  the terminal, never sent to the page. The live page is read-only, so its link can be opened again.
- **Unreal.** The Unreal bridge (Claireon) accepts commands from any process on this machine on its local port.
- **Web.** With `seats.web = "on"` the agents read web pages; a page could carry instructions. Turn it off for
  unattended runs on sensitive machines.

Report a vulnerability privately to the maintainers through GitHub's "Report a vulnerability" on this repository,
not in a public issue.
