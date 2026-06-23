from modern_di.suggester import close_matches


def test_exact_match_returned() -> None:
    result = close_matches("hello", ["hello", "world"], n=5)
    assert result == ["hello"]


def test_fuzzy_hit_at_or_above_cutoff_returned() -> None:
    # 'helo' vs 'hello': ratio=0.8889, well above 0.6
    result = close_matches("hello", ["helo", "world"], n=5)
    assert "helo" in result


def test_near_miss_below_cutoff_excluded() -> None:
    # 'world' vs 'hello': ratio=0.2000, well below 0.6
    result = close_matches("hello", ["world"], n=5)
    assert result == []


def test_n_cap_honoured() -> None:
    # Three candidates all >= 0.6; n=2 must return at most 2
    n = 2
    result = close_matches("hello", ["helo", "jello", "yello"], n=n)
    assert len(result) == n


def test_results_ordered_best_first() -> None:
    # 'helo' (0.8889) should precede 'jello' (0.8000)
    result = close_matches("hello", ["jello", "helo"], n=5)
    assert result == ["helo", "jello"]


def test_empty_candidates_returns_empty_list() -> None:
    result = close_matches("hello", [], n=5)
    assert result == []


def test_default_cutoff_is_0_6() -> None:
    # 'scope' vs 'rope': ratio=0.6667 (>= 0.6) -> included by default
    # 'scope' vs 'abc': ratio=0.0 (< 0.6) -> excluded by default
    result = close_matches("scope", ["rope", "abc"], n=5)
    assert "rope" in result
    assert "abc" not in result
