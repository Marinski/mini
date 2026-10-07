"""Suite registry: one instance per benchmark id."""

from __future__ import annotations

from bench.suites.base import Suite

_LOADED = False


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    from bench.suites import (  # noqa: F401
        context_caching_1,
        finqa,
        hello_world,
        human_eval,
        memory_recall_1,
        multi_turn_1,
        multi_turn_2,
        preserve_thinking_1,
    )

    _LOADED = True


def all_suites() -> dict[str, Suite]:
    _load()
    found: dict[str, Suite] = {}

    def walk(cls: type[Suite]) -> None:
        for sub in cls.__subclasses__():
            walk(sub)
            if sub.id and sub.__module__.startswith("bench.suites."):
                found[sub.id] = sub()

    walk(Suite)
    return found


def get_suite(suite_id: str) -> Suite:
    suites = all_suites()
    if suite_id not in suites:
        raise KeyError(f"unknown suite {suite_id!r}; have {', '.join(sorted(suites))}")
    return suites[suite_id]
