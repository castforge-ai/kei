# Contributing to Kei

Unless a contribution is clearly marked and approved as third-party material under another compatible licence, you
submit your original contribution under this repository's MIT licence.

Certify each contribution under the Developer Certificate of Origin 1.1 (below) by adding a `Signed-off-by:` line with
your name and an address you are entitled to publish. The sign-off and your contribution history are public. Kei's
own lesson sharing does not sign off for you: add the line yourself when you agree to the certificate.

Before you submit a lesson, code, artwork, animation or example, confirm that:

- you made it, or you have permission to submit it under the stated licence;
- any employer, client or collaborator whose permission is needed has given it;
- it holds no confidential information, no personal information you may not publish, and no restricted production
  material;
- you have named the third-party sources it relies on and kept their required notices;
- material from any other source follows that source's terms: reproduce protected wording, examples or arrangement
  only where authorised, name the source and licence, keep the required notices and say what you changed;
- you have reviewed anything an AI helped you write for third-party content, and you say in the pull request which
  material an AI helped with. An AI's help does not give you permission to contribute it;
- you have checked any employer, client or other restriction that affects the contribution before you sign off.

Say whether a lesson comes from your own test, your general experience, published research (cite it precisely) or
another source. If a source is confidential, contact the maintainers privately first; never publish confidential
material to show where a lesson came from.

That a lesson fixes an animation does not mean you may publish it. Maintainers may ask for permission records, and
may decline a contribution whose rights cannot be established. Turning on automatic sharing does not authorise
sharing your employer's or client's material.

## Developing Kei

    git clone <this repository> && cd kei
    uv sync                      # Python 3.12+, pytest and pytest-xdist
    uv run pytest -q -n auto     # the whole suite, about 2 minutes on 16 cores
    uv run kei demo              # the tools on an approved walk, offline

Maya and Unreal tests skip themselves when the application is not installed. Runtime code uses the standard library
only. A behaviour change ships with its test and, when the agent uses it, its line in the stage prompts
(kei/prompts/); `tests/test_prompt_commands.py` fails when a prompt names a kei command that does not exist.
`uv.lock` is not committed on purpose: Kei has no runtime dependency to pin, and the dev tools float within the
ranges pyproject.toml gives. Every text file is LF (`.gitattributes`).

### Adding a rule to the book

A rule lives in its topic file in kei/book/ as `### <ID>. <title>`, then a `stages:` line, then the rule in your own
words with a source tag. Use the next free ID of the topic. Never paste text from a book or a course.

### The maintainers' banned-terms hook

`tools/pre-commit-banned.sh` refuses commits that name terms on the maintainers' private list. It runs only in a
clone where a maintainer copied it into `.git/hooks`; contributors do not need it.

## Developer Certificate of Origin 1.1

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```
