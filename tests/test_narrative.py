"""narrative: 개발 서사(타임라인·콘텐츠 소재) 테스트."""

from __future__ import annotations

from brandlab.core.models import BrandCore
from brandlab.loader import (
    BrandLab,
    iter_doe_paths,
    load_all_batches,
    load_all_stability,
    load_doe,
)
from brandlab.narrative import content_seeds, seed_to_prompt, timeline


def _ctx():
    lab = BrandLab.load()
    doe = [load_doe(p) for p in iter_doe_paths()]
    return lab, load_all_batches(), doe, load_all_stability()


def test_timeline_has_version_events_sorted():
    lab, batches, doe, stab = _ctx()
    ev = timeline("basic-lotion", lab, batches=batches, doe=doe, stability=stab)
    assert ev
    assert any(e.kind == "버전" and "v2" in e.title for e in ev)
    # 날짜 있는 이벤트가 없는 이벤트보다 앞
    dated = [i for i, e in enumerate(ev) if e.date is not None]
    undated = [i for i, e in enumerate(ev) if e.date is None]
    if dated and undated:
        assert max(dated) < min(undated)


def test_content_seeds_failure_and_reason():
    lab, batches, doe, stab = _ctx()
    seeds = content_seeds("basic-lotion", lab, batches=batches, doe=doe, stability=stab)
    formats = {s.format_no for s in seeds}
    assert 11 in formats  # 실패담 (v1→v2 개선)
    assert 3 in formats  # 만든 이유(항상)
    assert 1 in formats  # 성분 해부


def test_doe_seed_present_for_lotion():
    lab, batches, doe, stab = _ctx()
    seeds = content_seeds("basic-lotion", lab, doe=doe)
    assert any(s.format_no == 5 for s in seeds)  # DOE 있으면 미신 깨기


def test_seed_to_prompt_has_rules_and_realshot():
    lab, batches, doe, stab = _ctx()
    seed = content_seeds("basic-lotion", lab)[0]
    p = seed_to_prompt(seed, BrandCore(brand_name="오브제"))
    assert "필수 준수" in p
    assert "미백" in p  # 기능성 금지 규칙
    assert "실촬영" in p  # 제품 실물 실촬영 안내


def test_timeline_unknown_slug_empty():
    lab, *_ = _ctx()
    assert timeline("nope-slug", lab) == []
