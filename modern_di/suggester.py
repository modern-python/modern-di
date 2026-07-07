import difflib
import typing


def close_matches(target: str, candidates: typing.Iterable[str], *, n: int, cutoff: float = 0.6) -> list[str]:
    """Fuzzy-match ``target`` against ``candidates``; best ``n`` at/above ``cutoff``.

    Thin wrapper over ``difflib.get_close_matches``.
    """
    return difflib.get_close_matches(target, list(candidates), n=n, cutoff=cutoff)
