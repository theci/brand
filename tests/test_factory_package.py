"""factory_package: 공장 제출 패키지(커버 + 제품표준서 zip) 테스트."""

from __future__ import annotations

import io
import zipfile

from brandlab.factory_package import build_package, factory_cover, zip_package
from brandlab.loader import BrandLab, load_all_batches, load_all_stability


def _formula(lab, slug="basic-lotion", version=2):
    return next(f for f in lab.formulas if f.slug == slug and f.version == version)


def test_cover_contains_key_sections():
    lab = BrandLab.load()
    cover = factory_cover(_formula(lab), lab, units=1000)
    assert "공장 제출 패키지" in cover
    assert "MOQ" in cover
    assert "NDA" in cover  # 영업비밀 주의
    assert "방부력" in cover  # 물 제품 필수 항목


def test_build_package_files():
    lab = BrandLab.load()
    f = _formula(lab)
    files = build_package(
        f, lab, units=1000,
        stability=load_all_stability(), batches=load_all_batches(),
    )
    assert "00_공장제출_안내.md" in files
    assert f"01_제품표준서_{f.slug}_v{f.version}.md" in files
    # 제품표준서에는 전성분·처방 등이 들어있어야 한다(dossier 위임)
    assert len(files[f"01_제품표준서_{f.slug}_v{f.version}.md"]) > 200


def test_zip_package_roundtrip():
    lab = BrandLab.load()
    files = build_package(_formula(lab), lab, units=500)
    data = zip_package(files)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert names == set(files)
        # 압축 해제 내용이 원본과 일치
        for name, content in files.items():
            assert zf.read(name).decode("utf-8") == content
