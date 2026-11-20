# Kei documentation

The [README](../README.md) at the top of the repository is the full reference. These pages are the short paths
through it.

| Page | Read it when |
|---|---|
| [Quickstart](quickstart.md) | you have not run Kei yet |
| [The twelve stages](stages.md) | you want to know what a shot goes through and what each stage leaves |
| [File formats](formats.md) | you write or read `shot.json`, `plan.json`, a lesson bundle or a notes file |
| [Engines and tools](engines.md) | you take a shot into Unreal, Maya, Blender, Godot or Unity |
| [Troubleshooting](troubleshooting.md) | a shot stopped and you want to know why and what to do |

The JSON Schemas in [schemas/](schemas/) are generated from Kei's code with `kei schema --write docs/schemas`, and a
test fails when they differ from the code, so they always describe the files Kei reads.
