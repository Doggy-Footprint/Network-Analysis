You are preparing a test case for a code-review study. Change this repository so that it contains exactly one realistic instance of the following problem, written the way an AI coding agent plausibly produces it while doing ordinary work on this project.

Problem: {name}
Description: {detail}

Location: {where}

Rules:
- Make the change look like a normal, purposeful edit (a small feature, fix, or cleanup). Do not add comments, names, or strings that point to the problem or to this study.
- Keep every file syntactically valid. The existing test suite must still pass, so place the problem where the current tests do not fail because of it.
- Do not edit existing tests unless the problem is about tests.
- Introduce only this problem; do not add unrelated defects.
- You cannot run commands; read the code to decide.

When done, write `{note}` at the repository root with one JSON object: {{"files": ["<path>", ...], "lines": {{"<path>": [<first>, <last>]}}, "summary": "<one sentence: what the problem is and where>"}}.
