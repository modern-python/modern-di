import dataclasses
import difflib
import enum
import typing


@dataclasses.dataclass(frozen=True, slots=True)
class Suggestion:
    """A candidate the caller probably meant, as data.

    Carries no formatting: rendering a suggestion to a bullet is ``exceptions``' job, so
    one module owns the glyphs. ``scope`` is None when the suggestion names something with
    no provider behind it (a creator's keyword argument); ``reason`` is None when there is
    nothing to say beyond the name.
    """

    name: str
    reason: str | None = None
    scope: enum.IntEnum | None = None


def close_matches(target: str, candidates: typing.Iterable[str], *, n: int, cutoff: float = 0.6) -> list[str]:
    """Fuzzy-match ``target`` against ``candidates``; best ``n`` at/above ``cutoff``.

    Thin wrapper over ``difflib.get_close_matches``.
    """
    return difflib.get_close_matches(target, list(candidates), n=n, cutoff=cutoff)
