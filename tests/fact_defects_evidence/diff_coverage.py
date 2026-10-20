import argparse
import json
import re
import subprocess
import sys


def changed_lines(base, paths):
    diff = subprocess.run(["git", "diff", "-U0", base, "--", *paths], capture_output=True, text=True, check=True).stdout
    result, current = {}, None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = None if line[4:] == "/dev/null" else line[6:]
        elif line.startswith("@@") and current:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, count = int(match.group(1)), int(match.group(2) or 1)
            result.setdefault(current, set()).update(range(start, start + count))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--fail-under", type=float, required=True)
    args = parser.parse_args()
    files = json.load(open(args.coverage))["files"]
    changed = changed_lines(args.base, sorted(files))
    hit = total = 0
    for path, lines in sorted(changed.items()):
        data = files.get(path)
        if data is None:
            continue
        executed, missing = set(data["executed_lines"]), set(data["missing_lines"])
        branches_hit = [b for b in data.get("executed_branches", []) if b[0] in lines]
        branches_missed = [b for b in data.get("missing_branches", []) if b[0] in lines]
        file_hit = len(lines & executed) + len(branches_hit)
        file_total = len(lines & (executed | missing)) + len(branches_hit) + len(branches_missed)
        hit, total = hit + file_hit, total + file_total
        for line in sorted(lines & missing):
            print(f"uncovered line {path}:{line}")
        for source, target in branches_missed:
            print(f"uncovered branch {path}:{source}->{target}")
    percent = 100.0 if total == 0 else 100.0 * hit / total
    print(f"diff coverage {hit}/{total} = {percent:.1f}%")
    return 0 if percent >= args.fail_under else 1


if __name__ == "__main__":
    sys.exit(main())
