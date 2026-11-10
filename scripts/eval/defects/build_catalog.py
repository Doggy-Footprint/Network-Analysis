"""Agent-reported types must stay independent of the analyzer's candidate kinds; they come from agent-reported.md."""
import json
from pathlib import Path

AGENT_WEIGHT = 3
GENERAL_WEIGHT = 1

AGENT = [
    ("P01", "Functional requirement violation / logic error", "strong", "SD", None),
    ("P02", "Reference to non-existent internal symbol", "strong", "S", None),
    ("P03", "Wrong external API usage", "moderate", "S", None),
    ("P04", "Deprecated API usage", "moderate", "S", None),
    ("P05", "Hallucinated package / dependency", "moderate", "S", None),
    ("P06", "Project resource / configuration mismatch", "moderate", "S", None),
    ("P07", "Incomplete implementation", "moderate", "SD", None),
    ("P08", "Plausible-but-wrong patch that passes weak tests", "strong", "D", None),
    ("P09", "Scoping errors: shadowing, redeclaration, use-before-assignment", "moderate", "S", None),
    ("P10", "Broad / swallowed exception handling, missing error handling", "strong", "S", None),
    ("P11", "Error-handling paths untested", "moderate", "S", None),
    ("P12", "Test manipulation to make tests pass", "moderate", "D", None),
    ("P13", "Weak or absent test oracles", "moderate", "S", None),
    ("P14", "Over-mocking in tests", "moderate", "SD", None),
    ("P15", "Changed code not covered by tests", "moderate", "D", None),
    ("P16", "Duplicated code / semantic clones", "strong", "SD", None),
    ("P17", "Reimplementing library functionality", "weak", "S", None),
    ("P18", "Avoidance of refactoring / adding instead of restructuring", "moderate", "D", None),
    ("P19", "Unused variables, arguments, imports", "moderate", "S", None),
    ("P20", "Unnecessary methods", "moderate", "D", None),
    ("P21", "Architecture violation: layer bypass and circular dependencies", "moderate", "S", None),
    ("P22", "Tightly coupled monolith", "weak", "S", None),
    ("P23", "Encapsulation violation (protected/private member access)", "moderate", "S", None),
    ("P24", "Non-compliance with documented project constraints", "strong", "SD", None),
    ("P25", "Data-layer / ORM misuse", "moderate", "S", None),
    ("P26", "Increased complexity", "moderate", "SD", None),
    ("P27", "Over-specification (single-use code)", "weak", "S", None),
    ("P28", "Over-engineering for improbable edge cases", "weak", "S", None),
    ("P29", "Excessive comments", "weak", "S", None),
    ("P30", "Naming and formatting inconsistency", "moderate", "S", None),
    ("P31", "Insecure code (general CWE weaknesses)", "strong", "S", None),
    ("P32", "Hard-coded credentials", "strong", "S", None),
    ("P33", "Path traversal", "strong", "S", None),
    ("P34", "Injection: OS command, format string, raw SQL, XSS", "strong", "S", None),
    ("P35", "Inefficient / non-literal regular expressions", "strong", "S", None),
    ("P36", "Missing or incorrect authorization", "moderate", "S", None),
    ("P37", "Known-vulnerable dependency version", "moderate", "SD", None),
    ("P38", "Dependency declaration smells", "strong", "S", None),
    ("P39", "Environment-specific assumptions / hard-coded paths and URLs", "moderate", "S", None),
    ("P40", "Performance inefficiency (excessive I/O, N+1)", "weak", "S", None),
    ("P41", "Concurrency correctness", "weak", "S", None),
    ("P42", "PR description claims changes the diff lacks", "moderate", "D", "needs PR metadata"),
    ("P43", "Documentation or comments needing correction", "moderate", "D", None),
    ("P44", "Self-admitted technical debt notes", "moderate", "S", None),
    ("P45", "Tangled / multi-purpose change", "moderate", "D", None),
    ("P46", "Unwanted or misaligned changes", "moderate", "D", "needs the task statement"),
    ("P47", "Duplicate / superseded PRs", "strong", "D", "needs repository PR history"),
    ("P48", "CI / test failures", "strong", "D", "injections must keep the build and tests green"),
    ("P49", "Elevated churn", "strong", "D", "needs weeks of history"),
    ("P50", "Breaking changes", "moderate", "D", None),
    ("P51", "Destructive operations against instructions", "weak", "D", "operational, not repository content"),
    ("P52", "License issues", "moderate", "S", None),
]

GENERAL = [
    ("G01", "Package-level cycle", "Suryanarayana2014; Mo2015", "S"),
    ("G02", "Unstable dependency (Stable Dependencies Principle violation)", "Martin2002; Arcan2017", "S"),
    ("G03", "Unhealthy inheritance (base class depends on a subclass)", "Mo2015", "S"),
    ("G04", "Misplaced module (placed in a higher layer, imported from below)", "Sarkar2009", "S"),
    ("G05", "Unwired framework component (router, provider, entity never registered)", "none: plausible", "S"),
    ("G06", "Cycle closed through a DI binding", "Lippert2006; Laigner2022", "S"),
    ("G07", "Cycle closed through a migration revision", "Lippert2006; Qiu2013", "S"),
    ("G08", "Static-check bypass through dynamic or reflective access", "Landman2017", "S"),
    ("G09", "Shotgun surgery / scattered references to one target", "Fowler2018; Garcia2009", "S"),
    ("G10", "Hub-like dependency / fat DI class", "Suryanarayana2014; Laigner2022", "S"),
    ("G11", "Useless injection (injected dependency never used)", "Laigner2022", "S"),
    ("G12", "Concrete class injection", "Laigner2022", "S"),
    ("G13", "Direct container call / service locator", "Laigner2022; Seemann2010", "S"),
    ("G14", "Feature envy", "Fowler2018", "S"),
    ("G15", "Message chains", "Fowler2018", "S"),
    ("G16", "Middle man", "Fowler2018", "S"),
    ("G17", "Data class", "Fowler2018", "S"),
    ("G18", "Long parameter list", "Fowler2018", "S"),
    ("G19", "Primitive obsession", "Fowler2018", "S"),
    ("G20", "Missing migration for a model change / orphan migration table", "Qiu2013", "SD"),
    ("G21", "Client call to a non-existent or renamed route", "none: plausible", "S"),
    ("G22", "Android performance and resource smells", "Hecht2015", "S"),
]


def build():
    rows = []
    for ident, name, grade, vis, reason in AGENT:
        rows.append({
            "id": ident, "name": name, "agent_reported": True, "weight": AGENT_WEIGHT,
            "evidence_grade": grade, "visibility": vis,
            "injectable": reason is None, "not_injectable_reason": reason,
            "sources": "agent-reported.md",
        })
    for ident, name, sources, vis in GENERAL:
        rows.append({
            "id": ident, "name": name, "agent_reported": False, "weight": GENERAL_WEIGHT,
            "evidence_grade": None, "visibility": vis,
            "injectable": True, "not_injectable_reason": None, "sources": sources,
        })
    return {
        "version": 1,
        "scoring": "weighted type recall = sum(weight * type_recall) / sum(weight), over injectable types with at least one valid injection",
        "types": rows,
    }


if __name__ == "__main__":
    out = Path(__file__).with_name("catalog.json")
    out.write_text(json.dumps(build(), indent=1) + "\n")
