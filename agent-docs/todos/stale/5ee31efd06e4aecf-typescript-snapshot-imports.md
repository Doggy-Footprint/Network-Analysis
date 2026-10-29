# TypeScript snapshot import resolution

## Goal

“ROADMAP / ANALYSIS_APPROACH에서 이 남은 업무를 각각 handoff로 넘기자.” Roadmap item: “Make every analyzer consume one immutable repository snapshot directly.”

## Purpose

Keep TypeScript relative import edges determined by the captured snapshot when the source tree changes or is removed after capture. This is a focused correction to one filesystem existence check.

## State

- Branch: `master`; base commit: `ad8431b`.
- Changed files for this handoff: this file and `agent-docs/handoff/index.md`; source planning documents `ROADMAP.md` and `ANALYSIS_APPROACH.md` are removed.
- The CLI passes a captured snapshot to `TypeScriptAnalyzer`, which parses its source contents. `TypeScriptAnalyzer._resolve_import` still checks `candidate.is_file()`, so a captured relative import target can lose its edge if its live file disappears before resolution.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| None recorded | — | — |

## Next Step

Make `TypeScriptAnalyzer._resolve_import` check captured module paths when a snapshot is supplied. Add a regression case that captures two TypeScript files with a relative import, removes the target file, and confirms the import edge still points to the captured target. Preserve the existing filesystem behavior when no snapshot is supplied.

## Open Questions

- None for this focused correction.

## Spec

No workflow spec exists for this handoff. Version, status, and run ID: not applicable.

## Execution Ledger

- Finding: `code_analyzer/cli.py` passes a snapshot to TypeScript analysis; disposition: retain the existing path.
- Finding: `language_analyzers/typescript/analyzer.py` resolves imports with a filesystem existence check; disposition: correct only the snapshot path and verify its import edge.
- Evidence and mutation outcomes: source inspection only; no implementation mutation or verification run.
- Correction count: 0; verifier count: 0.
