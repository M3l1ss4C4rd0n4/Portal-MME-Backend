"""Tests básicos para shared.decorators.cache"""

from shared.decorators.cache import cache, clear_cache, get_cache_stats


def test_cache_decorator():
    clear_cache()

    @cache(ttl_seconds=1)
    def double(x):
        return x * 2

    assert double(2) == 4
    assert double(2) == 4

    stats = get_cache_stats()
    assert stats["total_entries"] >= 1
