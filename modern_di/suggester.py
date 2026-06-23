import difflib
import typing


def close_matches(target: str, candidates: typing.Iterable[str], *, n: int, cutoff: float = 0.6) -> list[str]:
    """Fuzzy-match ``target`` against ``candidates``; best ``n`` at/above ``cutoff``.

    Thin wrapper over ``difflib.get_close_matches`` so the similarity cutoff and
    its tuning live in one place, and the matching is unit-testable without
    raising an error.
    """
    return difflib.get_close_matches(target, list(candidates), n=n, cutoff=cutoff)
