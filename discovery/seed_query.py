import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol, Sequence, Tuple, Union

from .models import Scenario, SeedQueryError, SeedQuerySet, SeedTerm

SCHEMA = "seed_queries.v1"
_GENERATOR_KEYS = ("model_id", "revision", "backend", "prompt_id", "prompt", "decoding")


def task_hash(task: str) -> str:
    return hashlib.sha256(task.encode("utf-8")).hexdigest()


class SeedQueryGenerator(Protocol):
    def generate(self, task: str) -> SeedQuerySet: ...


class ExplicitSeedQueries:
    def __init__(self, terms: Sequence[SeedTerm]):
        self.terms = tuple(terms)

    def generate(self, task: str) -> SeedQuerySet:
        return SeedQuerySet(
            source="explicit",
            terms=self.terms,
            generator={
                "model_id": "explicit",
                "revision": "1",
                "backend": "none",
                "prompt_id": "",
                "prompt": "",
                "decoding": {},
                "fixture_sha256": "",
                "raw_output": "\n".join(f"{item.surface}:{item.term}" for item in self.terms),
            },
        )


class CachedSeedQueryGenerator:
    def __init__(self, fixture: Mapping[str, Any], fixture_sha256: str):
        if not isinstance(fixture, Mapping):
            raise SeedQueryError("seed query fixture root must be an object")
        if fixture.get("schema") != SCHEMA:
            raise SeedQueryError(f"seed query fixture schema must be {SCHEMA}")
        generator = fixture.get("generator")
        if not isinstance(generator, Mapping):
            raise SeedQueryError("seed query fixture generator must be an object")
        for key in _GENERATOR_KEYS:
            if key not in generator:
                raise SeedQueryError(f"seed query fixture generator is missing key: {key}")
        entries = fixture.get("entries")
        if not isinstance(entries, list):
            raise SeedQueryError("seed query fixture entries must be a list")
        self.generator = dict(generator)
        self.fixture_sha256 = fixture_sha256
        self.entries: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise SeedQueryError("seed query fixture entry must be an object")
            task = entry.get("task")
            recorded = entry.get("task_sha256")
            if not isinstance(task, str) or not task:
                raise SeedQueryError("seed query fixture entry task must be a non-empty string")
            digest = task_hash(task)
            if recorded != digest:
                raise SeedQueryError(
                    f"seed query fixture entry task_sha256 mismatch: {recorded} != {digest}"
                )
            if not isinstance(entry.get("raw_output"), str):
                raise SeedQueryError("seed query fixture entry raw_output must be a string")
            self.entries[digest] = dict(entry)

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "CachedSeedQueryGenerator":
        try:
            raw_bytes = Path(path).read_bytes()
        except OSError as error:
            raise SeedQueryError(f"cannot read seed queries {path}: {error}") from error
        try:
            fixture = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SeedQueryError(f"seed queries is not valid JSON: {error}") from error
        return cls(fixture, hashlib.sha256(raw_bytes).hexdigest())

    def generate(self, task: str) -> SeedQuerySet:
        digest = task_hash(task)
        entry = self.entries.get(digest)
        if entry is None:
            raise SeedQueryError(f"no cached seed queries for task {task!r} (sha256 {digest})")
        raw_terms = entry.get("terms")
        if not isinstance(raw_terms, list):
            raise SeedQueryError(f"seed query fixture entry terms must be a list: {digest}")
        terms = []
        for item in raw_terms:
            if not isinstance(item, Mapping):
                raise SeedQueryError(f"seed query fixture term must be an object: {digest}")
            term = item.get("term")
            surface = item.get("surface")
            if not isinstance(term, str) or not term:
                raise SeedQueryError(f"seed query fixture term must be a non-empty string: {digest}")
            if surface not in ("content", "path"):
                raise SeedQueryError(f"seed query fixture surface must be content or path: {digest}")
            terms.append(SeedTerm(term=term, surface=surface))
        generator = dict(self.generator)
        generator["fixture_sha256"] = self.fixture_sha256
        generator["raw_output"] = entry["raw_output"]
        return SeedQuerySet(source="cache", terms=tuple(terms), generator=generator)


def resolve_seed_queries(
    scenario: Scenario,
    cached: SeedQueryGenerator,
) -> Tuple[Scenario, SeedQuerySet]:
    generator = ExplicitSeedQueries(scenario.seed_terms) if scenario.seed_terms else cached
    seed_set = generator.generate(scenario.task)
    return dataclasses.replace(scenario, seed_terms=seed_set.terms), seed_set
