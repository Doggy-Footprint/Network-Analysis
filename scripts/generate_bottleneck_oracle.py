from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping, Sequence


Runner = Callable[[Sequence[str], Path], str]


def generate(root: Path, runner: Runner) -> Mapping[str, object]:
    corpus = root / "corpus"
    command = ("rg", "--json", "--fixed-strings", "--glob", "*.py", "needle", ".")
    version = runner(("rg", "--version"), corpus).splitlines()[0]
    raw_search = runner(command, corpus)
    files_command = ("rg", "--files", "--glob", "*.py")
    raw_files = runner(files_command, corpus)
    read_command = ("sed", "-n", "1,3p", "unicode.py")
    raw_read = runner(read_command, corpus)
    return {
        "tool": {"rg": version, "read": "sed"},
        "commands": {"search": list(command), "files": list(files_command), "read": list(read_command)},
        "raw": {"search": raw_search, "files": raw_files, "unicode.py": raw_read},
    }


def main() -> None:
    import subprocess
    root = Path(__file__).resolve().parents[1] / "fixtures" / "bottlenecks"
    data = generate(
        root,
        lambda command, cwd: subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout,
    )
    (root / "frozen-oracle.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
