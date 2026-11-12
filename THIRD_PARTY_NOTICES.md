# Third-party notices

Kei's own code and rule book are under the MIT licence in LICENSE. The material below belongs to others and keeps
its own notice.

## Claireon

tests/fixtures/unreal/claireon_tools.json is the tool list (names, descriptions and input schemas) that the Claireon
Unreal Editor plugin, version 2.2.0 (https://github.com/believer-oss/claireon), returned to Kei's client during
testing. It is kept as a test fixture. Claireon is under the MIT licence:

```
MIT License

Copyright (c) 2026 The Claireon Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Epic Games' Game Animation Sample project

Rules HED22, LOC39, LOC40, LOC45, LOC48 and LOC50 in kei/book report measurements made from Epic Games' Game Animation
Sample. This repository does not include the sample's assets or animation clips. Access to and use of the sample remain
subject to the licence that applies to the copy obtained from Epic. These measurements are not an Epic endorsement or a
grant of rights in Epic content.

## Tools Kei runs but does not ship

Kei starts these programs when they are installed on your machine; none of them is included in this repository, and
each keeps its own licence and terms:

- Python and its standard library (PSF licence).
- Claude Code (Anthropic's terms) and OpenAI Codex CLI (Apache-2.0), or any agent command line you configure.
- FFmpeg and ffprobe (LGPL or GPL, depending on the build you installed); Kei only runs them as separate programs.
- git and the GitHub CLI gh, for lesson sharing.
- Unreal Engine with the Claireon plugin, and Autodesk Maya, under their own licence agreements.
- Node.js, used only by tools/rig_golden.js to regenerate test data.

## Development tools

- pytest (MIT) and hatchling (MIT), used to test and build Kei; they are not part of the installed package.
