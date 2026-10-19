# -*- coding: utf-8 -*-
"""제품개발 마스터 엑셀 1장 — 개발 기록을 '살아있는 파일'로 관리.

카드 아키타입 레시피·원료 사전·역설계의 핵심을, 1인 개발자가 매일 여는 단 하나의
워크북으로 압축한다. 보유 원료(data/inventory.yaml) 기반 초안 레시피 + 재고/제조/
실험을 수식으로 연계한다.

시트(8):
  1) 읽어보기   사용법 · 이슈 대응 루프 · 안정성 설명
  2) 레시피     제품별 카드(컨셉·설계이유·특징·원료표+설명·만드는법)  [읽기용]
  2-b) 트러블슈팅  증상→원인→조정→왜 (이슈 나면 어디를·뭘 바꾸나)
  3) 원료       현재고 = 최초보유 + 구매 + 조정 − 제조사용 (전부 자동 수식)
  3-b) 도구     보유·추천 장비/소모품 모음(보유·메모는 보존)
  4) 입출고     구매·조정 원장(append)  [네가 사면 한 줄]
  5) 개발일지   만든 배치 + 실험 판정(append)  [만들면 제품+배치량g 한 줄 → 재고 차감]
  6) 처방       레시피 %를 표로 — 재고 연계 수식 엔진

설계 원칙(나중에 안 갈아엎게):
  · Excel 표(Table)+구조적 참조 → 행 추가 시 수식/필터/드롭다운 자동 확장.
  · 재생성해도 입출고·개발일지(사용자 기록)는 보존, 참조 시트만 다시 그림.
  · 조인 키 = 원료 한글명 / 제품명. 재고 흐름: 구매(입출고) + 조정 − 제조사용(개발일지×처방).

산출: 제품개발_마스터.xlsx (리포 루트)
사용: uv run python scripts/dev_master.py
⚠ %·공정·pH는 설계·연습 기준(예시). 실제 제조 전 원료 TDS·pH·방부력(챌린지)·
   사용기한·전성분 검증. 화장품이라 '치료·완화·항염·살균' 표방 금지.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import openpyxl
import yaml
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "제품개발_마스터.xlsx"

# ── 보유 원료 메타(한글명·INCI·상·역할) — 시트가 자급되도록 직접 정의 ──────────
# phase: A 수상 / B 유상 / C 냉각첨가 / pH 조절. safe=히어로(말라세지아-세이프)
ING: dict[str, dict] = {
    "water":          dict(ko="정제수", inci="Water", phase="A", role="용제", safe=True),
    "glycerin":       dict(ko="글리세린", inci="Glycerin", phase="A", role="보습(폴리올)", safe=True),
    "betaine":        dict(ko="베타인", inci="Betaine", phase="A", role="보습", safe=True),
    "niacinamide":    dict(ko="나이아신아마이드", inci="Niacinamide", phase="A", role="활성·피지/장벽/톤", safe=True),
    "allantoin":      dict(ko="알란토인", inci="Allantoin", phase="A", role="진정", safe=True),
    "beta-glucan":    dict(ko="베타글루칸", inci="Beta-Glucan", phase="A", role="진정·보습", safe=True),
    "zinc-pca":       dict(ko="아연피카", inci="Zinc PCA", phase="A", role="피지조절", safe=True),
    "propanediol":    dict(ko="프로판디올", inci="Propanediol", phase="A", role="보습+방부보조", safe=True),
    "xanthan-gum":    dict(ko="잔탄검", inci="Xanthan Gum", phase="A", role="점증(글리세린 선분산)", safe=True),
    "multi-hyaluronic-acid": dict(ko="다중 히알루론산", inci="Hyaluronic Acids", phase="A", role="보습(층별 수분)", safe=True),
    "montanov-68":    dict(ko="몬타노브68", inci="Cetearyl Alcohol & Cetearyl Glucoside", phase="B", role="유화제(세이프)", safe=True),
    "cetyl-alcohol":  dict(ko="세틸알코올", inci="Cetyl Alcohol", phase="B", role="공유화·점도·바디", safe=True),
    "squalane":       dict(ko="스쿠알란", inci="Squalane", phase="B", role="에몰리언트(경량·세이프)", safe=True),
    "mct":            dict(ko="MCT오일", inci="Caprylic/Capric Triglyceride", phase="B", role="에몰리언트(경량·세이프)", safe=True),
    "dimethicone":    dict(ko="디메치콘", inci="Dimethicone", phase="B", role="실키·보호막", safe=True),
    "tocopherol":     dict(ko="토코페롤(비타민E)", inci="Tocopherol", phase="B", role="항산화(산패 방지)", safe=True),
    "jojoba-oil":     dict(ko="호호바오일", inci="Simmondsia Chinensis Seed Oil", phase="B", role="에몰리언트", safe=False),
    "shea-butter":    dict(ko="시어버터", inci="Butyrospermum Parkii Butter", phase="B", role="에몰리언트(리치)", safe=False),
    "olive-emulsifying-wax": dict(ko="올리브유화왁스", inci="Cetearyl Olivate & Sorbitan Olivate", phase="B", role="유화제", safe=False),
    "madecassoside":  dict(ko="마데카소사이드", inci="Madecassoside", phase="C", role="진정 활성", safe=True),
    "panthenol":      dict(ko="판테놀(B5)", inci="Panthenol", phase="C", role="보습·진정", safe=True),
    "green-tea-extract": dict(ko="녹차추출물", inci="Camellia Sinensis Leaf Extract", phase="C", role="항산화·피지(EGCG)", safe=True),
    "phenoxyethanol": dict(ko="페녹시에탄올", inci="Phenoxyethanol", phase="C", role="방부제(한도 1%)", safe=True),
    "hexanediol":     dict(ko="1,2-헥산다이올", inci="1,2-Hexanediol", phase="C", role="방부 부스터·보습", safe=True),
    "citric-acid":    dict(ko="구연산", inci="Citric Acid", phase="pH", role="pH 조절(희석액 q.s.)", safe=True),
    # 가용화제(미보유·신규구매) — 워시오프 클렌징용. C8/C10 유래라 말라세지아-세이프.
    "polyglyceryl-4-caprate": dict(ko="폴리글리세릴-4 카프레이트", inci="Polyglyceryl-4 Caprate", phase="B", role="가용화제(세이프 C10·★신규구매)", safe=True),
    "caprylyl-capryl-glucoside": dict(ko="카프릴릴/카프릴 글루코사이드", inci="Caprylyl/Capryl Glucoside", phase="B", role="가용화제·세정(세이프 C8/C10·★신규구매)", safe=True),
}


def ing(id_: str) -> dict:
    return ING.get(id_, dict(ko=id_, inci="", phase="?", role="", safe=True))


# ── 원료가 하는 일(쉬운 설명) — 처음 보는 사람도 이해하도록 ──────────────────────
WHY: dict[str, str] = {
    "water": "모든 성분을 녹이는 바탕(제품의 대부분을 차지).",
    "glycerin": "수분을 끌어당기는 대표 보습제. 잔탄검을 미리 개는 매개로도 쓴다.",
    "propanediol": "보습하면서 방부를 거드는 보조 폴리올.",
    "betaine": "순한 보습제.",
    "niacinamide": "비타민B3. 피지·모공·피부톤·장벽을 두루 돕는 대표 활성.",
    "allantoin": "자극을 가라앉히는 진정 성분.",
    "beta-glucan": "진정+수분. 예민한 피부를 달랜다.",
    "zinc-pca": "피지(기름기)를 조절해 번들거림을 줄인다.",
    "xanthan-gum": "천연 점증제. 젤·에멀전에 점도와 안정성을 준다(글리세린에 선분산).",
    "multi-hyaluronic-acid": "분자 크기별 히알루론산으로 층층이 수분 충전(유분 없이 보습).",
    "montanov-68": "물과 기름을 섞어주는 유화제(글루코사이드계·세이프).",
    "cetyl-alcohol": "유화를 안정화하고 바디·발림감을 주는 지방알코올.",
    "squalane": "가볍고 안정적인 보습 오일. 피부 유래라 순함(세이프).",
    "mct": "아주 가벼운 오일. 세정·발림 베이스(C8/C10·세이프).",
    "dimethicone": "실키한 발림과 얇은 보호막을 주는 실리콘.",
    "tocopherol": "비타민E. 오일 산패(산화)를 막는 항산화제.",
    "madecassoside": "병풀(시카)의 진정 핵심 성분.",
    "panthenol": "프로비타민B5. 보습·진정·장벽 회복.",
    "green-tea-extract": "녹차 폴리페놀(EGCG). 항산화·피지·진정.",
    "phenoxyethanol": "세균·곰팡이를 막는 방부제(물 든 제품엔 필수).",
    "hexanediol": "방부를 돕고 보습도 하는 부스터.",
    "citric-acid": "산도(pH)를 피부에 맞게 낮추는 조절제.",
    "polyglyceryl-4-caprate": "오일이 물을 만나면 유백색으로 풀려 헹궈지게 하는 가용화제(C10·세이프).",
    "caprylyl-capryl-glucoside": "순한 세정·가용화 보조(C8/C10·세이프).",
}

# ── 고정 역할(통제 어휘 11종) — 원료·트러블슈팅이 같은 값을 써 필터로 엮인다 ──────
CROLE: dict[str, str] = {
    "water": "용제",
    "glycerin": "보습", "betaine": "보습", "propanediol": "보습", "multi-hyaluronic-acid": "보습",
    "niacinamide": "활성", "allantoin": "활성", "beta-glucan": "활성", "zinc-pca": "활성",
    "madecassoside": "활성", "panthenol": "활성", "green-tea-extract": "활성",
    "xanthan-gum": "점증제",
    "montanov-68": "유화제", "olive-emulsifying-wax": "유화제",
    "cetyl-alcohol": "유상·에몰리언트", "squalane": "유상·에몰리언트", "mct": "유상·에몰리언트",
    "jojoba-oil": "유상·에몰리언트", "shea-butter": "유상·에몰리언트",
    "dimethicone": "감촉·실리콘",
    "tocopherol": "항산화제",
    "phenoxyethanol": "방부제", "hexanediol": "방부제",
    "citric-acid": "pH조절",
    "polyglyceryl-4-caprate": "가용화제", "caprylyl-capryl-glucoside": "가용화제",
}
# 역할별 상세 설명(무엇을 하고, 이슈 때 어디로 조정). 트러블슈팅 '관련 역할'과 연결.
ROLE_DESC: dict[str, str] = {
    "용제": "제품의 바탕이 되는 물. 전체 양·농도를 맞추는 '잔량(마지막에 100g 채움)'으로 쓴다. 되기엔 직접 관여 안 함.",
    "보습": "수분을 끌어당기거나 붙잡아 촉촉하게(글리세린·베타인·프로판디올·히알루론산). 너무 끈적하면 종류를 바꾸거나 %↓.",
    "활성": "효능을 내는 성분(피지·진정·톤 등). 따갑/자극 나면 고농도 활성(나이아신아마이드 등)부터 %↓, 민감하면 2%부터 올려가며 테스트.",
    "유화제": "물과 기름이 분리 안 되게 잡아준다(몬타노브68). 층분리 나면 ①온도 ②호모 먼저, 그래도면 %↑.",
    "점증제": "되기(점도)를 만든다(잔탄검). 묽으면 0.1%p↑, 되면↓. 반드시 글리세린에 선분산 후 물에(뭉침 방지).",
    "유상·에몰리언트": "오일·지방알코올로 발림·영양·바디를 준다(스쿠알란·MCT·세틸알코올). 무겁/번들이면 %↓, 묽으면 세틸↑.",
    "감촉·실리콘": "매끈한 발림과 얇은 보호막(디메치콘). 산뜻함 필요하면 소폭↑, 헹굼성 떨어지면↓.",
    "항산화제": "오일이 산패(쩐내)하는 걸 늦춘다(토코페롤). 쩐내·변색 나면 0.5~1% 추가, 차광 보관.",
    "방부제": "세균·곰팡이를 막는다(페녹시에탄올+헥산다이올). 물 든 제품 필수. 오염 나면 함량·소독 점검.",
    "pH조절": "산도를 피부에 맞춘다(구연산, 목표 5.0~5.5). 높으면 산 한 방울씩, 낮으면 정제수로 희석.",
    "향료": "향을 입히는 성분(에센셜오일·향료). 냉각 단계에 소량, 리브온은 보수적으로(IFRA·알러젠 한도 확인). ★다도기는 '무향'이 원칙 — 향 자극을 피하려 기본 미사용(필요 시에만).",
    "가용화제": "오일이 물을 만나면 유백색으로 풀려 헹궈지게 한다(워시오프 클렌징). 안 헹궈지면 %↑.",
}
# 역할 드롭다운/필터용 고정 순서(원료 '역할' 칸 검증에 사용)
ROLES = ["용제", "보습", "활성", "유화제", "점증제", "유상·에몰리언트", "감촉·실리콘",
         "향료", "방부제", "항산화제", "pH조절", "가용화제"]


def crole(id_: str) -> str:
    return CROLE.get(id_, ing(id_)["role"])


# ── 제형별 '만드는 법'(제품 블록 안에 인라인으로 들어감) — 초보자용 상세 ─────────
# 준비물: 전자저울(0.01g)·유리비커 2개·유리막대/미니핸드블렌더·온도계·pH스트립(or미터)
#        ·알코올(70~75%)·계량 종이컵·일회용 장갑. 모두 알코올 소독 후 시작.
METHOD_STEPS: dict[str, list[str]] = {
    "비유화": [
        "① 준비: 도구·용기·손을 70% 알코올로 소독. 100g 배치면 전량이 수상이라 250mL 비커 1개(계량·혼합 겸용) + 소량 계량용 작은 종이컵/유산지. %가 곧 그램(83.5% = 83.5g).",
        "② 히알루론산(분말)은 미리 불린다: 수상용 정제수 일부에 솔솔 뿌려 1~2시간(되도록 전날) 두면 투명 젤처럼 된다. 바로 넣으면 안 녹아 뭉친다.",
        "③ (젤·앰플) 잔탄검 선분산: 잔탄검을 글리세린(+프로판디올)에 넣고 막대로 개어 '된죽'을 만든다. 이 상태로 정제수에 부으며 저어야 피시아이(쌀알 덩어리)가 안 생긴다.",
        "④ 나머지 정제수에 수용성 활성을 하나씩 녹인다: 나이아신아마이드→알란토인→베타글루칸→아연PCA 순. 알란토인은 잘 안 녹으니 충분히 저어 완전 용해(미세 가루가 안 보일 때까지). HS5Pro 자석교반으로 저으면 편하고, 안 녹으면 40~45℃로 살짝 데워도 된다.",
        "⑤ ③과 ④를 합쳐 균일하게 섞는다(맑고 덩어리 없는 상태).",
        "⑥ 40℃ 이하로 식었으면 열에 약한 냉각군을 넣는다: 판테놀·마데카소사이드·녹차추출물·방부제(페녹시에탄올+헥산다이올). 녹차는 갈변 전 마지막에.",
        "⑦ pH 측정 → 목표 5.0~5.5. 높으면 구연산 희석액(물:구연산≈9:1)을 한 방울씩 떨어뜨리며 다시 측정. 한 번에 많이 넣지 말 것(확 떨어진다).",
        "⑧ (젤) 점도 확인: 묽으면 잔탄검을 0.1%씩만 더(③처럼 선분산). 저을 때 생긴 기포는 1~2시간 정치하면 빠진다.",
        "⑨ 소독한 용기에 충전. 라벨에 날짜·버전. 1개월 내 사용.",
        "★ 흔한 실수: HA 안 불림 / 잔탄 피시아이 / pH 측정 생략 / 방부제 빠뜨림(물 든 제품은 필수).",
    ],
    "무수닦기": [
        "① 준비: 용기·도구를 '완전히 말린다'(물 한 방울만 섞여도 무수 제형이 상한다). 오일 전량 담을 250mL 비커 1개.",
        "② 오일을 계량해 비커에 넣는다: MCT·스쿠알란·디메치콘. 가열 불필요(상온에서 다 섞인다).",
        "③ 유리막대로 30초~1분 고루 섞는다. 디메치콘이 바닥에 깔리기 쉬우니 충분히.",
        "④ 토코페롤(비타민E)을 넣어 산패를 늦춘다. 마지막에 가볍게 섞는다.",
        "⑤ 무수라 방부제는 필요 없다. 펌프/드롭퍼 용기에 담고 차광·서늘 보관.",
        "⑥ 사용법: 마른 얼굴에 적당량 올려 1분 마사지(메이크업·피지가 녹는다) → 화장솜·티슈로 닦아낸다. 물로 헹궈지지 않는 타입이다.",
        "★ 주의: 개봉·사용 중 물 유입 금지(펌프 권장). 오일 냄새가 변하면(쩐내) 산패 신호 → 폐기.",
    ],
    "무수워시오프": [
        "① 준비: 용기·도구를 완전히 말린다(무수). 오일+가용화제 전량 담을 250mL 비커 1개.",
        "② 오일 계량: MCT·스쿠알란·디메치콘.",
        "③ 가용화제(폴리글리세릴-4 카프레이트)를 16~20% 넣고 상온에서 고루 섞는다 — 이게 물을 만나면 유백색으로 풀리게 하는 핵심.",
        "④ 토코페롤을 넣어 마무리.",
        "⑤ ★유화 테스트(중요): 손바닥에 소량 덜고 물 몇 방울을 떨어뜨려 비벼본다. 뽀얗게 유백색으로 변하면 성공. 그대로 기름막이면 가용화제를 1%씩 올린다.",
        "⑥ 사용법: 마른 얼굴에 마사지 → 손에 물을 묻혀 한 번 더 비비면 유백색 유화 → 미온수로 헹군다.",
        "⑦ 튜닝: 가용화제가 적으면 안 헹궈지고 미끈, 많으면 당기고 눈시림. 디메치콘이 많으면 헹굼이 떨어진다 — 한 축씩 조정하며 ⑤ 테스트 반복.",
        "★ 주의: 가용화제는 아직 미보유(★구매 필요). 무수라 방부 불필요하나 물 유입은 막는다.",
    ],
    "유화": [  # 내 장비 기준: HS5Pro(가열 자력교반)·HZ-400(호모)·OC-15S(오버헤드)·LC-8S(원심)
        "① 준비·동선: 도구·용기·교반날을 70% 알코올로 소독. 비커는 100g 배치 기준 수상 A=250mL(HS5Pro 위), 유상 B=100mL(중탕용), 냉각 C는 유산지/소형 비커에 계량(200g면 500mL/250mL). ★가열·유화·냄새나는 계량은 '클린벤치 밖'(환기), 식힌 뒤 충전·마무리만 클린벤치 안.",
        "② 상 나눠 계량: 수상 A(정제수·글리세린·판테놀·검) / 유상 B(오일·세틸알코올·몬타노브68) / 냉각 C(보존제·향·열 약한 활성)는 대기. 검은 글리세린에 선분산.",
        "③ 수상 A 가열: HS5Pro 비커에 자석교반자(stir bar)를 넣고 중속 교반 + ★온도 프로브를 'A 액체'에 꽂아 70~75℃ 제어(상판 온도 아님).",
        "④ 유상 B 가열: 냄비 중탕으로 70~75℃까지 '용해'(교반보다 완전 용해가 중요). 별도 디지털 온도계로 B 확인(감 X). (항온수조 OB-2Pro는 아직 미보유라 중탕으로 대체)",
        "⑤ 두 상 70~75℃에서 약 20분 유지(완전 용해+미생물 부담↓). 시계접시·뚜껑으로 덮어 증발을 줄이고, 합치기 직전 줄어든 무게만큼 뜨거운 정제수로 보충.",
        "⑥ 합치기 전: 수상의 자석교반자를 회수 막대로 빼둔다(호모 날 충돌 방지). 두 상 온도를 ±5℃로 맞춘다(어긋나면 유화가 안 붙는다).",
        "⑦ 유화(HZ-400): 유상 B를 수상 A에 부으며 호모나이저 날이 충분히 잠기게 세우고 2~5분 고속. 비커 벽 따라 천천히 이동해 전체를 균질화. ★유화는 오직 호모 몫 — 마그네틱·손젓기는 전단이 부족해 분리된다.",
        "⑧ '붙으면'(뽀얀 크림색) 호모를 멈춘다. 오래 돌리면 기포·점도 저하 → 바로 냉각 교반으로 전환.",
        "⑨ 냉각 교반(OC-15S): 오버헤드 패들을 바닥서 1~2cm 띄우고 저속으로 40℃까지. 소용돌이가 깊으면 공기를 말아 기포가 된다. 묽은 로션은 HS5Pro 마그네틱만으로도 가능.",
        "⑩ 40℃ 이하서 냉각첨가 C: 보존제(페녹시+헥산다이올)·향·열 약한 활성. 뜨거울 때 넣으면 날아가거나 변질된다.",
        "⑪ pH: 30℃대~실온에서 pH미터(교정 후)로 측정 → 5.0~5.5로 보정(구연산 희석액 한 방울씩, 다시 측정). 증발분은 정제수로 총량 100g 맞춤.",
        "⑫ ★당일 유화 판정(LC-8S 원심): 15mL 튜브에 ~10g씩 2개(무게 대칭) → 3,000rpm·30분 → 분리층(오일링/크리밍/침전) mm 확인 → 개발일지 '분리mm'에 숫자로 기록. 0이면 안정성 큐로, 있으면 튜닝/접기.",
        "⑬ 충전·안정성: 클린벤치 안에서 소독한 용기에 충전. 투명 바이알에 4조건(45℃·실온·4℃·냉동융해)+대조군 소분, 1·2·4·8주 관찰(45℃는 발효기/인큐베이터).",
        "★ 크림(유상↑): 유상 완전 용해에 시간 더 / 호모는 '더 짧게 확실히'(점도 높아 기포 위험) / 오버헤드 냉각은 '더 길게'(굳기 전 C 투입).",
        "★ 흔한 실수: 두 상 온도 안 맞춤(분리) / 자석바 안 빼고 호모(충돌) / 호모 과다(기포·점도↓) / 식기 전 C 투입(열 파괴).",
    ],
}

# pH 스트립 읽는 법 — 물로 만드는 제형(비유화·유화)에 공통 삽입 ─────────────────
_PH_GUIDE = [
    "★ pH 스트립 읽는 법:",
    "– 스트립을 액에 1초 담갔다 빼고, 10~15초 뒤(설명서 시간) 색이 멈췄을 때 '자연광'에서 통에 인쇄된 색표와 맞춘다(형광등 아래는 색이 왜곡된다).",
    "– 색표 두 칸 사이로 보이면 중간값으로 읽는다(예: 5와 5.5 사이면 ≈5.2). 0.2~0.5 눈금의 정밀 스트립을 권장.",
    "– 크림·젤처럼 되직해 색이 안 보이면 정제수와 1:1로 풀어서 잰다(묽혀도 pH는 거의 그대로).",
    "– 색이 금세 바래니 빼서 오래 두지 말고 바로 판독. 젖은 손·금속이 스트립에 닿지 않게.",
    "– 목표 5.0~5.5. 더 정확히는 pH 미터(보정액으로 교정 후 사용). 스트립은 ±0.3 오차가 정상이다.",
]
# 마지막 '★ 흔한 실수' 줄 바로 앞에 끼워 넣어, 모든 단계 뒤 + 실수 요약 앞에 오게 한다.
for _k in ("비유화", "유화"):
    _steps = METHOD_STEPS[_k]
    METHOD_STEPS[_k] = _steps[:-1] + _PH_GUIDE + _steps[-1:]

# 계량·비커 — 처음 하는 사람용 공통 블록. 각 방법의 ①(준비) 바로 뒤에 끼운다.
_WEIGH = [
    "★ 계량·비커 (처음이면 꼭 — 100g 배치 기준):",
    "– 저울 2개를 나눠 쓴다: 정제수·오일처럼 많은 양은 벤치저울(0.1g 단위), 활성·검·보존제·향처럼 1% 이하 소량은 정밀저울(0.01g 단위). 소량을 큰 저울로 재면 오차가 처방을 망친다.",
    "– 분말·점성 원료: 저울에 유산지(칭량지)를 깔고 → 영점(TARE 버튼) → 원료를 담는다. 글리세린·오일 같은 액체는 '받을 비커'를 올리고 TARE 후 바로 부어 넣는다(유산지에 눌어붙음 방지).",
    "– 정제수는 '맨 마지막에 100g을 맞추는 잔량'으로 넣는다(다른 걸 다 더하고 남는 양).",
    "– 비커 크기 = 내용물의 약 2~2.5배(가열·교반 때 넘침 방지). 200g 배치면 한 단계 큰 비커로.",
    "– 흘리면 닦고 다시. 통에 손·젖은 도구 넣지 않기(오염). 소량은 깨끗한 스패출러로.",
]
for _k in METHOD_STEPS:
    _s = METHOD_STEPS[_k]
    METHOD_STEPS[_k] = _s[:1] + _WEIGH + _s[1:]

# ── 초안 레시피 7종 (보유 원료 기반 · 합 100 · 쉬움→어려움) ─────────────────────
RECIPES = [
    dict(
        slug="sebum-calm-toner", name="시크 진정 토너", type="토너(비유화)",
        difficulty="① 쉬움 — 유화 없음, 첫 실험용", method="비유화",
        concept="지성·예민용 무향 수분 토너. 유분 0 — 녹차·나이아신아마이드로 피지·진정.",
        features=["산뜻·무유분 수분", "말라세지아-세이프(오일 없음)", "무향"],
        design=[
            "지성·예민 피부엔 기름보다 '가벼운 수분 + 진정'이 먼저다 → 유분 0으로 설계.",
            "수용성 활성만 모았다: 나이아신아마이드(피지·톤)·녹차(항산화)·시카·베타글루칸(진정).",
            "가열·유화가 없어 가장 쉬운 첫 실험 — 실패해도 배우는 비용이 작다.",
            "피부와 같은 약산성(pH 5.0~5.5)으로 맞춰 자극을 줄인다.",
        ],
        lines=[
            ("water", "A", 83.5, "베이스"),
            ("glycerin", "A", 4.0, ""),
            ("propanediol", "A", 3.0, ""),
            ("niacinamide", "A", 2.0, "완전 용해 확인"),
            ("allantoin", "A", 0.3, ""),
            ("beta-glucan", "A", 1.0, ""),
            ("multi-hyaluronic-acid", "A", 0.5, "미리 불려 사용"),
            ("panthenol", "C", 1.0, ""),
            ("green-tea-extract", "C", 2.0, "차광·냉장분, 갈변 주의"),
            ("madecassoside", "C", 1.0, ""),
            ("phenoxyethanol", "C", 0.5, ""),
            ("hexanediol", "C", 1.0, ""),
            ("citric-acid", "pH", 0.2, "pH 5.0~5.5 q.s."),
        ],
    ),
    dict(
        slug="sebum-calm-ampoule", name="진정 밸런스 앰플", type="앰플(비유화·고농축)",
        difficulty="② 토너 변주 — 활성 농도↑, 유화 없음", method="비유화",
        concept="고농축 수분·진정·피지 앰플. 토너와 같은 공정, 활성만 끌어올린 무유분 세럼.",
        features=["고농축 진정·피지", "무유분·가벼운 세럼", "말라세지아-세이프", "무향"],
        design=[
            "토너와 '같은 물 베이스'지만 활성 농도를 끌어올린 집중 케어 버전.",
            "나이아신아마이드 4%·베타글루칸 2% 등 핵심만 농축 — 유분 없이 무겁지 않게.",
            "잔탄검 아주 소량으로 '세럼 같은' 약간의 점도를 준다.",
            "민감하면 활성%를 낮게 시작해 내 피부 반응을 보며 올린다.",
        ],
        lines=[
            ("water", "A", 78.8, "베이스"),
            ("glycerin", "A", 4.0, ""),
            ("propanediol", "A", 3.0, ""),
            ("niacinamide", "A", 4.0, "고농축(민감 시 2%부터)"),
            ("zinc-pca", "A", 1.0, "피지"),
            ("allantoin", "A", 0.3, ""),
            ("beta-glucan", "A", 2.0, "진정 고농축"),
            ("multi-hyaluronic-acid", "A", 1.0, "미리 불려 사용"),
            ("xanthan-gum", "A", 0.3, "앰플 점도(글리세린 선분산)"),
            ("madecassoside", "C", 1.0, ""),
            ("panthenol", "C", 1.0, ""),
            ("green-tea-extract", "C", 2.0, ""),
            ("phenoxyethanol", "C", 0.5, ""),
            ("hexanediol", "C", 1.0, ""),
            ("citric-acid", "pH", 0.1, "pH 5.0~5.5 q.s."),
        ],
    ),
    dict(
        slug="soothing-gel", name="진정 수분 젤", type="젤(비유화·점증)",
        difficulty="③ 점증 연습 — 잔탄검 분산", method="비유화",
        concept="끈적임 적은 수분 젤. 잔탄검 점증 감각 익히기(글리세린 선분산 필수).",
        features=["가벼운 젤 텍스처", "무유분", "점증 학습용"],
        design=[
            "오일 없이 '점증제(잔탄검)'만으로 젤 텍스처를 만드는 연습.",
            "핵심 기술: 잔탄검을 글리세린에 미리 개어 넣기 — 물에 바로 넣으면 덩어리진다.",
            "끈적임이 적어 지성 피부가 쓰기 좋은 수분 공급형.",
            "점도는 잔탄검 양으로 조절한다(0.1%씩).",
        ],
        lines=[
            ("water", "A", 84.9, "베이스"),
            ("glycerin", "A", 4.0, "잔탄검 선분산 매개"),
            ("propanediol", "A", 3.0, ""),
            ("xanthan-gum", "A", 0.6, "★글리세린에 개어 넣기(덩어리 방지)"),
            ("niacinamide", "A", 2.0, ""),
            ("allantoin", "A", 0.3, ""),
            ("beta-glucan", "A", 1.0, ""),
            ("multi-hyaluronic-acid", "A", 0.5, ""),
            ("madecassoside", "C", 1.0, ""),
            ("panthenol", "C", 1.0, ""),
            ("phenoxyethanol", "C", 0.5, ""),
            ("hexanediol", "C", 1.0, ""),
            ("citric-acid", "pH", 0.2, "pH 5.0~5.5 q.s."),
        ],
    ),
    dict(
        slug="sebum-calm-cleansing-oil", name="딥 클렌징 오일 (닦아내기)", type="클렌징오일(무수)",
        difficulty="④ 무수 오일 블렌딩 — 가열·유화·방부 없음", method="무수닦기",
        concept="말라세지아-세이프 오일만으로 메이크업·피지를 녹이는 닦아내기 오일. 무수라 방부 불필요.",
        features=["무수(물 0)·방부 불필요", "말라세지아-세이프 오일만", "★닦아내기(wipe-off)"],
        design=[
            "물 없이 오일만 → 세균이 못 자라 방부제가 필요 없는 가장 단순한 제형.",
            "말라세지아가 못 먹는 C8/C10 오일(MCT·스쿠알란)만 써 트러블 피부에도 안전.",
            "가용화제가 없어 물에 안 풀린다 → 티슈로 닦아내는 용도(클렌징 1단계).",
            "디메치콘으로 발림과 잔여감을 다듬는다.",
        ],
        lines=[
            ("mct", "B", 60.0, "경량 세정 베이스(C8/C10, 세이프)"),
            ("squalane", "B", 25.0, "컨디셔닝·경량"),
            ("dimethicone", "B", 14.0, "슬립·잔여감 저감"),
            ("tocopherol", "B", 1.0, "산화 방지"),
        ],
    ),
    dict(
        slug="sebum-calm-wash-cleansing-oil", name="워시오프 클렌징 오일", type="클렌징오일(무수·가용화)",
        difficulty="⑤ 무수+가용화제 — 물 만나면 유백색 유화·헹굼", method="무수워시오프",
        concept="오일에 가용화제를 넣어, 물 접촉 시 유백색으로 유화돼 헹궈지는 워시오프 클렌징 오일.",
        features=["물로 헹굼(워시오프)", "말라세지아-세이프(C8/C10 가용화제)", "무향", "★가용화제 1종 신규 구매 필요"],
        design=[
            "닦아내기 오일에 '가용화제'를 더해, 물을 만나면 유백색으로 풀려 헹궈지게 만든 버전.",
            "가용화제도 C8/C10(세이프)로 골라 브랜드 원칙 유지 — 지방산 유래(폴리소르베이트80·PEG-7글리세릴코코에이트)는 세이프 회색지대라 제외.",
            "가용화제 양이 '헹굼성'의 핵심 변수 → 16~20%에서 실험으로 튜닝.",
            "무수라 방부 불필요하나 물 유입은 막는다(펌프·드롭퍼 용기).",
        ],
        lines=[
            ("mct", "B", 54.0, "세정 베이스(C8/C10, 세이프)"),
            ("squalane", "B", 24.0, "컨디셔닝·경량"),
            ("polyglyceryl-4-caprate", "B", 18.0, "★가용화제(신규구매) 16~20% 튜닝"),
            ("dimethicone", "B", 3.0, "슬립(많으면 헹굼 저하)"),
            ("tocopherol", "B", 1.0, "산화 방지"),
        ],
    ),
    dict(
        slug="sebum-calm-lotion", name="밸런스 진정 로션", type="로션(유화·경량)",
        difficulty="⑥ 유화 입문 — 오일 ~8%, 가벼운 에멀전", method="유화",
        concept="크림보다 가벼운 유화 입문. 유상 비율 낮춰 분리 위험 줄인 연습용.",
        features=["가벼운 로션", "말라세지아-세이프 오일만", "무향"],
        design=[
            "물과 기름을 '유화제로 섞는' 첫 에멀전 — 기름을 ~8%로 낮춰 분리 위험을 줄였다.",
            "수상(A)·유상(B)을 같은 온도(70~75℃)로 데워 섞고, 식히며 안정화한다.",
            "오일은 전부 세이프(스쿠알란·MCT·디메치콘). 활성·진정 철학은 크림과 같다.",
            "잔탄검 소량으로 에멀전을 더 안정화한다.",
        ],
        lines=[
            ("water", "A", 71.8, "베이스"),
            ("glycerin", "A", 4.0, ""),
            ("propanediol", "A", 3.0, ""),
            ("niacinamide", "A", 2.0, ""),
            ("allantoin", "A", 0.3, ""),
            ("beta-glucan", "A", 1.0, ""),
            ("zinc-pca", "A", 0.5, ""),
            ("multi-hyaluronic-acid", "A", 0.5, ""),
            ("xanthan-gum", "A", 0.2, "안정화(글리세린 선분산)"),
            ("montanov-68", "B", 3.0, "유화제"),
            ("cetyl-alcohol", "B", 1.0, ""),
            ("squalane", "B", 3.0, ""),
            ("mct", "B", 2.0, ""),
            ("dimethicone", "B", 2.0, ""),
            ("madecassoside", "C", 1.0, ""),
            ("panthenol", "C", 1.0, ""),
            ("green-tea-extract", "C", 2.0, ""),
            ("phenoxyethanol", "C", 0.5, ""),
            ("hexanediol", "C", 1.0, ""),
            ("citric-acid", "pH", 0.2, "pH 5.0~5.5 q.s."),
        ],
    ),
    dict(
        slug="sebum-calm-cream", name="시크 진정 밸런스 크림 (히어로)", type="크림(유화·리치)",
        difficulty="⑦ 유화 완성 — 히어로 v2, 오일 ~17%", method="유화",
        concept="히어로 제품. 지성·예민 피부 무향 진정 밸런스 크림(sebum-calm-cream v2).",
        features=["진정·보습 밸런스", "말라세지아-세이프 전면 적용", "무향", "50mL 자(jar)"],
        design=[
            "브랜드 히어로 — 진정·보습·피지의 균형을 잡은 완성형.",
            "말라세지아-세이프 전면 적용: C11~24 지방산 오일(올리브·코코넛·호호바·버터) 배제, 무향.",
            "층층이 설계: 활성(나이아신아마이드·아연PCA·시카·녹차)+보습(HA·글리세린)+세이프 에몰리언트(스쿠알란·MCT·디메치콘).",
            "가장 난도 높은 완전 유화 — 토너→젤→로션을 거쳐 오면 자연스럽다.",
        ],
        lines=[
            ("water", "A", 63.5, "베이스"),
            ("glycerin", "A", 5.0, ""),
            ("niacinamide", "A", 2.0, ""),
            ("allantoin", "A", 0.5, ""),
            ("beta-glucan", "A", 1.0, ""),
            ("zinc-pca", "A", 1.0, ""),
            ("propanediol", "A", 3.0, "v2 펜틸렌글라이콜 → 보유 프로판디올 대체"),
            ("xanthan-gum", "A", 0.3, "글리세린 선분산"),
            ("multi-hyaluronic-acid", "A", 1.0, ""),
            ("montanov-68", "B", 4.0, "유화제(세이프)"),
            ("cetyl-alcohol", "B", 2.0, ""),
            ("squalane", "B", 5.0, ""),
            ("mct", "B", 3.0, ""),
            ("dimethicone", "B", 3.0, ""),
            ("madecassoside", "C", 1.0, "v2 센텔라추출물 → 보유 마데카소사이드 대체"),
            ("panthenol", "C", 1.0, ""),
            ("green-tea-extract", "C", 2.0, ""),
            ("phenoxyethanol", "C", 0.7, ""),
            ("hexanediol", "C", 1.0, ""),
        ],
    ),
    dict(
        slug="sebum-calm-cream-minimal", name="시크 진정 크림 (미니멀 3종)", type="크림(유화·리치)",
        difficulty="⑧ 미니멀 변주 — 히어로에서 활성 3종만", method="유화",
        concept="히어로 크림을 활성 핵심 3종으로 좁힌 미니멀 버전. 베이스(유화·보습·방부)는 히어로 v2와 동일, 활성만 나이아신아마이드·시카·베타글루칸으로 집중.",
        features=["활성 3종 미니멀", "말라세지아-세이프", "무향", "히어로 v2 베이스 동일"],
        design=[
            "히어로 v2에서 활성을 '핵심 3종'으로 좁힌 미니멀 버전 — 유화·보습·방부 베이스는 그대로 둔다.",
            "활성 3종만 남긴다: 나이아신아마이드(피지·장벽·톤) · 마데카소사이드(시카 진정) · 베타글루칸(진정+수분).",
            "역할이 겹치던 아연PCA·알란토인·판테놀과, 갈변 리스크가 있는 녹차추출물은 뺐다.",
            "활성이 적을수록 자극 변수·갈변 리스크가 줄고, 무엇이 효과를 냈는지 해석이 쉽다 — '정직한' 처방 훈련.",
            "뺀 자리는 정제수로 채워 합 100% 유지(유상 ~17%·세이프 에몰리언트 구성은 히어로와 동일).",
        ],
        lines=[
            ("water", "A", 64.8, "베이스(q.s. 100%)"),
            ("glycerin", "A", 5.0, ""),
            ("niacinamide", "A", 4.0, "핵심 활성 ①(민감 시 2%부터 시작)"),
            ("beta-glucan", "A", 2.0, "핵심 활성 ②(진정+수분)"),
            ("propanediol", "A", 3.0, ""),
            ("xanthan-gum", "A", 0.3, "글리세린 선분산"),
            ("multi-hyaluronic-acid", "A", 1.0, "미리 불려 사용"),
            ("montanov-68", "B", 4.0, "유화제(세이프)"),
            ("cetyl-alcohol", "B", 2.0, ""),
            ("squalane", "B", 5.0, ""),
            ("mct", "B", 3.0, ""),
            ("dimethicone", "B", 3.0, ""),
            ("madecassoside", "C", 1.0, "핵심 활성 ③(시카 진정)"),
            ("phenoxyethanol", "C", 0.7, ""),
            ("hexanediol", "C", 1.0, ""),
            ("citric-acid", "pH", 0.2, "pH 5.0~5.5 q.s."),
        ],
    ),
]

READ_ME: list[tuple[str, list[str]]] = [
    ("이 파일이 하는 일", [
        "플랫폼 전부를 열지 않고, 매일 여는 '단 하나'의 개발 기록.",
        "레시피는 내가(Claude) 짠 초안 — 실험하며 한 축씩 수정해 너의 것으로 만든다.",
        "레시피는 '지금 보유한 원료'만으로 만들 수 있게 설계(미보유는 ★표시).",
        "각 시트 1행=제목, 2행=그 시트 설명·컬럼 뜻. 처음엔 2행부터 읽으면 된다.",
    ]),
    ("처음이라면 — 이렇게 시작 (5분)", [
        "① '레시피' 시트 맨 위 ①번 '시크 진정 토너'부터. 가장 쉽고(유화 없음) 실패 비용이 작다.",
        "② 100g로 만든다 — 레시피 %가 곧 그램(83.5% = 83.5g). 계량·순서는 카드의 '만드는 법'에 다 있다.",
        "③ 다 만들면 '개발일지'에 한 줄: 날짜·제품·배치량g·사용감·판정.",
        "④ 아쉬운 점(끈적·묽음 등) 있으면 '트러블슈팅'에서 고칠 곳을 찾아 '다음 아이디어'에 적는다.",
        "⑤ 다음엔 그 한 가지만 바꿔 다시 만든다. 이 반복이 개발의 전부다.",
    ]),
    ("시트 8개 지도", [
        "읽어보기 : (지금 이 시트) 사용법·흐름·용어.",
        "레시피 : 제품별 카드(컨셉·설계이유·원료설명·만드는법). 읽기용.",
        "트러블슈팅 : 이슈가 나면 어디를·뭘 바꾸나(증상→원인→조정→관련역할). 필터로 본다.",
        "원료   : 현재고가 자동 계산되는 재고판. 역할(고정 12종)로 필터.",
        "도구   : 보유·추천 장비/소모품 모음(필터). '보유'·'메모'는 네가 고쳐도 보존.",
        "입출고 : 원료를 사거나(구매) 버릴 때(조정) 한 줄씩 쌓는 장부.",
        "개발일지 : 배치를 만들고 평가한 기록(제품+배치량g 적으면 재고가 빠진다).",
        "처방   : 레시피 %를 표로 — 재고 연계용 수식 엔진(거의 안 봐도 됨).",
    ]),
    ("전체 흐름 한눈에", [
        "[만들기] 레시피 고름 → 만듦 → 개발일지에 기록(사용감·분리mm·pH·판정).",
        "[고치기] 이슈 → 트러블슈팅에서 '관련 역할' 확인 → 원료 시트에서 그 역할로 필터 → 바꿀 원료 선택 → 다음 아이디어.",
        "[사기]   원료 사면 → 입출고 한 줄(구매) → 원료 '현재고' 자동 ↑.",
        "[재고]   만들면 → 개발일지 배치량g → 쓴 원료가 처방 %대로 자동 ↓.",
    ]),
    ("★ 재고가 자동으로 맞춰지는 원리", [
        "현재고 = 최초보유 + 구매(입출고) + 조정(입출고) − 제조사용(개발일지 배치량 × 처방%).",
        "원료를 사면 → '입출고'에 [날짜·원료·구매·수량g] 한 줄.",
        "제품을 만들면 → '개발일지'에 [날짜·제품·배치량g] 한 줄 → 쓴 원료가 자동 차감.",
        "흘리거나 버리면 → '입출고'에 구분 '조정', 수량g에 음수(-).",
        "현재고가 빨갛게(음수) 뜨면 그 원료는 '사야 함' 신호.",
    ]),
    ("매일 쓰는 법", [
        "① 필터: 각 표 머리글의 ▼ 버튼으로 상·제품·판정·역할 등으로 걸러 본다.",
        "② 새 줄: 표 맨 아래 줄에 바로 입력하면 수식·드롭다운이 자동으로 따라 확장된다.",
        "③ 한 번에 한 변수만 바꾼다 — 그래야 뭐가 효과였는지 안다.",
        "④ 실패도 '접기'로 기록 — 안 되는 방향을 지우는 것도 전진.",
    ]),
    ("이슈가 나면 — 이렇게 고친다 (핵심 루프)", [
        "개발일지에 사용감·이슈·분리mm·pH를 적는다 → '트러블슈팅'에서 그 증상 줄을 찾는다.",
        "그 줄의 '관련 역할'(예: 끈적임→보습)을 보고 → '원료' 시트에서 역할=그 값으로 필터 → 바꿀 후보 원료가 한눈에.",
        "'조정'대로 한 축만 골라 개발일지 '다음 아이디어'에 적는다(예: 글리세린 1%p↓ + 베타인으로 대체).",
        "다음에 만들 땐 그 '다음 아이디어'가 이번 배치의 '바꾼것', '기준(base)'엔 직전 버전을 적는다.",
        "접힌 것도 '이 방향은 아니다' 데이터 — 지우지 말고 남긴다.",
    ]),
    ("원료 '역할' 12종 (필터·트러블슈팅 공통 어휘)", [
        "용제 = 바탕 물. / 보습 = 수분 잡기(글리세린·베타인·HA). / 활성 = 효능(피지·진정·톤).",
        "유화제 = 물·기름 섞기(몬타노브68). / 점증제 = 되기 만들기(잔탄검). / 유상·에몰리언트 = 오일·지방알코올.",
        "감촉·실리콘 = 매끈함(디메치콘). / 향료 = 향(다도기는 무향 원칙). / 방부제 = 세균·곰팡이 방지.",
        "항산화제 = 산패 방지(토코페롤). / pH조절 = 산도 맞춤(구연산). / 가용화제 = 오일을 물에 풀기(워시오프).",
        "→ 자세한 '역할 설명'은 원료 시트의 E열에 역할마다 붙어 있다.",
    ]),
    ("안정성 테스트란 (45℃·RT·4℃·동결융해)", [
        "제품이 '시간이 지나도 안 변하는지' 보는 시험. 같은 배치를 조건별로 나눠 두고 1·2·4·8주 관찰한다.",
        "45℃=고온(가속). 더우면 변질이 빨라져 '미래를 미리' 본다 — 분리·변색·냄새·pH 변화가 여기서 먼저 터진다.",
        "RT=Room Temperature(상온)=실제 사용 근사·대조군. 4℃=냉장(굳음·결정). 동결융해=얼렸다 녹였다 반복(유화 견고성).",
        "둘 곳: 45℃는 발효기/인큐베이터, RT는 직사광 없는 서랍, 4℃·냉동은 냉장고. 투명 바이알에 담아 눈으로 비교.",
        "개발일지 예시 '안정성 45C/RT 등록' = 이 배치를 45℃와 상온에 넣어 안정성 관찰을 시작한다는 뜻.",
    ]),
    ("초보 용어 사전", [
        "수상(A)=물에 녹는 것(물·보습·수용성 활성) / 유상(B)=기름에 녹는 것(오일·유화제·지방알코올) / 냉각첨가(C)=식힌 뒤 넣는 열에 약한 것(방부·향·일부 활성).",
        "유화 = 물과 기름을 유화제+강한 교반(호모)으로 안 갈라지게 섞는 것(로션·크림).",
        "%p(퍼센트포인트) = 배합 % 숫자를 그만큼 올리/내리기(글리세린 5%→4% = 1%p↓).",
        "배치 = 한 번에 만드는 양(연습은 100g). base = 이번 실험의 출발 버전.",
        "선분산 = 검(잔탄)을 물에 넣기 전 글리세린에 미리 개어 두는 것(뭉침·피시아이 방지).",
        "리브온 = 씻어내지 않고 피부에 남는 제품(토너·크림) → 향·보존을 더 보수적으로.",
        "말라세지아-세이프 = 피부 효모가 먹는 C11~24 지방산 오일을 뺀 것(우리 오일=스쿠알란·MCT·디메치콘).",
        "pH = 산성/염기성 척도(0~14). 피부는 약산성 5 안팎. 물 든 제품만 측정.",
    ]),
    ("레시피를 늘리고 싶을 때", [
        "나(Claude)에게 말하면 레시피 카드 + 처방 표 + (새 원료면) 원료 행을 추가해 재생성한다.",
        "재생성해도 네가 적은 '입출고·개발일지'와 도구 '보유·메모'는 그대로 보존된다.",
        "직접 늘릴 땐: 처방 표에 [제품·원료·상·퍼센트] 행을 추가하면 재고 연계가 자동으로 걸린다.",
    ]),
    ("핵심 제약 (브랜드 = 다도기 지성·진정)", [
        "말라세지아-세이프: C11~24 지방산 오일 배제(스쿠알란·MCT·디메치콘만).",
        "무향: 향료 자극 배제. 화장품 표방 규칙: 치료·완화·항염·살균·병명 금지.",
        "pH 4.5~6.0(이 레시피 5.0~5.5), 물 든 제품은 반드시 방부, 소량 제조·1개월 내 사용.",
    ]),
    ("안전·위생 (꼭)", [
        "작업 전 70% 알코올로 도구·용기·손 소독 — 미생물이 자가제조 최대 리스크.",
        "소량(50~100g)으로, 라벨·기록 철저, 가열·향 작업은 환기되는 곳에서.",
        "자가제조는 R&D(개발)용 — 판매는 처방 완성 후 공장(OEM/ODM) 통해. 규제는 식약처 기준 재확인.",
    ]),
    ("창업·OEM 실무 시트 (스터디 밖)", [
        "OEM 개발의뢰서 : 공장에 보낼 '제품개발의뢰서(RFQ)' 한 장. 첫 제품=히어로 '시크 진정 밸런스 크림' 예시가 채워져 있다 — 고쳐 쓰기만.",
        "공장엔 PPT 발표가 아니라 이 스펙 시트를 PDF로 보낸다. 레퍼런스 제품 실물/사진을 같이 준비하면 전달이 가장 정확.",
        "줘도 되는 것 = 제형·성분·용량 등 스펙(견적에 필요) / 아껴야 할 것 = 마케팅·채널·매출 계획. 진짜 해자는 상표권('다도기' 출원).",
        "견적은 항목별로(개발비·샘플비·수량별 단가·MOQ·리드타임·처방 독점·시험성적서). 뭉뚱그린 견적·구두 약속·과도한 선금은 경계 신호.",
        "시트 아래쪽에 공장 첫 문의용 이메일·카톡 템플릿 포함 — 복사해서 바로 쓴다. (이 시트는 scripts/oem_brief.py로 생성·갱신)",
    ]),
]

# ── 도구 모음 (장비·소모품) — 홈랩 장비구축 가이드 §10 기준 ──────────────────────
# (분류, 도구, 권장규격·모델, 용도, 보유기본). 보유 값: 보유/추천/소모품/필수
TOOLS: list[tuple[str, str, str, str, str]] = [
    ("계량", "정밀 저울", "0.01g(필요시 0.001g)·최대 ~200g", "활성·검·보존제·향 등 1% 이하 소량 계량", "보유"),
    ("계량", "벤치 저울", "0.1g·최대 2~3kg", "정제수·오일·베이스 등 대량 계량", "추천"),
    ("계량", "유산지(칭량지)·약포지", "소모품", "분말 깔고 TARE 계량(비커 안 더럽힘)", "소모품"),
    ("계량", "스패출러·약수저", "스테인리스", "원료 덜기", "보유"),
    ("계량", "메스실린더", "50·100mL", "액체 부피 참고(정밀은 저울로)", "추천"),
    ("가열·교반", "가열 자력교반기(핫플+스터러)", "HS5Pro + 온도프로브", "수상 가열·70~75℃ 유지·자석교반", "보유"),
    ("가열·교반", "자석교반자 + 회수막대", "PTFE 바", "교반 / 뜨거운 비커서 바 회수", "보유"),
    ("가열·교반", "중탕 냄비", "주방용", "유상 간접 가열(항온수조 대체)", "보유"),
    ("가열·교반", "디지털 온도계 2개", "프로브형", "수상=프로브, 유상=별도 온도계", "추천"),
    ("가열·교반", "시계접시·비커뚜껑", "유리", "가열 중 물 증발 방지", "추천"),
    ("가열·교반", "비커집게·내열장갑", "—", "70~75℃ 화상 방지", "추천"),
    ("유화·냉각", "호모나이저", "HZ-400", "유화(고전단) 전용 — 유화는 이것만", "보유"),
    ("유화·냉각", "오버헤드 교반기 + 패들", "OC-15S + 임펠러·클램프", "냉각 교반(저속·길게), 크림 필수", "보유"),
    ("측정·판정", "pH 미터", "+ 교정버퍼 4·7 + 보관액", "로션·크림 pH 측정·보정", "보유"),
    ("측정·판정", "pH 스트립", "0.2~0.5 눈금", "간이 pH(미터 백업)", "추천"),
    ("측정·판정", "원심분리기", "LC-8S(저속 8×15mL)", "당일 유화 분리 판정(분리mm)", "보유"),
    ("측정·판정", "15mL 코니컬 튜브 + 랙", "눈금 있는 것", "원심 샘플(10g×2 대칭)", "소모품"),
    ("유리기구", "비커", "100·250·500mL 각 2~3개", "계량·가열·혼합", "보유"),
    ("유리기구", "유리막대", "—", "젓기·검 선분산 개기", "보유"),
    ("소분·보관", "투명 유리 바이알", "20~30mL 다수", "안정성 소분(4조건+대조군)", "보유"),
    ("소분·보관", "시제품 용기", "로션=펌프/튜브, 크림=자/에어리스", "완제품 충전", "추천"),
    ("소분·보관", "스포이드", "일회용 PE / 유리(향 전용)", "소량·pH 적정", "소모품"),
    ("소분·보관", "라벨지 + 유성마커", "—", "배치·조건·날짜 기록", "소모품"),
    ("세척·위생", "70% 에탄올 + 분무기", "소모품", "도구·용기·손 소독(제일 중요)", "소모품"),
    ("세척·위생", "병솔·시험관솔", "호모헤드 전용솔 포함", "비커·튜브·호모헤드 세척", "보유"),
    ("세척·위생", "페그(젖병) 건조대", "—", "거꾸로 꽂아 완전 건조", "추천"),
    ("세척·위생", "정제수/증류수", "소모품", "최종 헹굼·처방 용수(수돗물 금지)", "소모품"),
    ("안정성 환경", "45℃ 인큐베이터/발효기", "챔버형", "가속 안정성 보관(45℃)", "보유"),
    ("안정성 환경", "냉장(4℃)·냉동", "주방 냉장고", "저온·동결융해 안정성", "보유"),
    ("안정성 환경", "컴프레서 와인셀러 15℃", "펠티어 말고 컴프레서", "원료 냉암 보관(여름 대비)", "추천"),
    ("안전", "ABC 분말 소화기", "작업 반경 내", "에탄올·발열 화재 대비", "추천"),
    ("안전", "니트릴 장갑·보안경", "소모품", "향료·산·열 보호", "소모품"),
    ("안전", "환기(창문/국소배기)", "—", "증기 배출(에탄올·향 작업)", "필수"),
]

# ── 트러블슈팅 (증상→원인→조정→관련역할→왜) — 제조 가이드 §5 + 보유 팔레트 기반 ──
# %p = 퍼센트포인트(배합% 숫자를 그만큼 ↑/↓). 조정은 '한 번에 하나만'.
# '관련 역할'은 원료 시트의 고정 역할값과 같다 → 거기서 그 역할로 필터해 원료를 고른다.
TROUBLE: list[tuple[str, str, str, str, str, str]] = [
    ("유화안정", "층분리 — 물·기름이 갈라짐", "두 상 온도 안 맞음 / 유화 부족 / 유화제 부족",
     "①두 상 70~75℃ ±5℃로 다시 맞춰 유화 ②호모(HZ-400) 더 오래·날 충분히 잠기게 ③그래도면 유화제(몬타노브68) 0.5%p↑",
     "유화제", "유화는 온도·전단(호모)·유화제 세 박자. 하나씩 점검."),
    ("유화안정", "시간 지나 윗면 기름뜸(오일링)·크리밍", "유화 약함 / 점도 낮아 기름방울이 뜸",
     "점증제(잔탄검) 0.1%p↑ 먼저. 그래도면 유화제 소폭↑", "점증제", "점도가 높으면 기름방울이 떠오르지 못한다."),
    ("텍스처", "너무 묽다", "점증·유상 부족",
     "잔탄검 0.1%p↑ 또는 세틸알코올 0.5%p↑ (둘 중 하나만)", "점증제 / 유상·에몰리언트", "점증제·지방알코올이 '되기'를 만든다."),
    ("텍스처", "너무 되다·뻑뻑", "점증·유상 과다",
     "잔탄검 또는 세틸알코올 0.1~0.5%p↓, 줄인 만큼 정제수↑", "점증제 / 유상·에몰리언트", "되기를 만든 걸 반대로 줄인다."),
    ("텍스처", "뭉침(피시아이, 쌀알 덩어리)", "검(잔탄)을 물에 바로 넣음",
     "잔탄검을 글리세린에 먼저 개어(선분산) 넣기", "점증제", "검은 물 만나기 전에 분산시켜야 안 뭉친다."),
    ("피부감", "끈적인다", "글리세린(폴리올) 과다",
     "글리세린 1%p↓ + 그만큼 베타인/프로판디올로 대체  ← (문서의 그 예시!)", "보습", "같은 보습이라도 폴리올 종류를 바꾸면 끈적임↓."),
    ("피부감", "무겁다·번들거림(지성엔 특히)", "오일·유화제 과다",
     "오일(스쿠알란/MCT) 1~2%p↓, 산뜻함 필요하면 디메치콘 소폭↑", "유상·에몰리언트 / 감촉·실리콘", "유분을 줄이고 실리콘으로 매끈함만 유지."),
    ("피부감", "밀린다(하얗게 말림·피딩)", "점증제·고분자 겹침 / 도포량 많음",
     "잔탄검 소폭↓ 또는 한 번에 바르는 양 줄이기", "점증제", "고분자가 겹치면 비비면서 밀려 나온다."),
    ("피부감", "자극·따가움", "활성 농도 높음 / pH 낮음",
     "나이아신아마이드 등 활성 %↓(2%부터 시작), pH 5.0~5.5 확인", "활성 / pH조절", "민감 피부는 농도·산도를 낮춰 적응시킨다."),
    ("pH", "pH 높다(>6)", "산 부족",
     "구연산 희석액(물:구연산 9:1) 한 방울씩 + 재측정", "pH조절", "피부는 약산성(5.0~5.5)이 편하다."),
    ("pH", "pH 낮다(<4.5)", "산 과다",
     "정제수로 약간 희석. 보통 레시피대로면 이 문제는 잘 안 난다", "pH조절 / 용제", "과도한 산은 자극이 된다."),
    ("방부·오염", "곰팡이·점액·시큼한 냄새(물 제품)", "방부 부족 / 소독 미흡",
     "방부(페녹시에탄올+헥산다이올) 들어갔는지 확인, 도구 소독 철저, 1개월 내 사용", "방부제", "물+영양(글리세린·추출물)=미생물 배지."),
    ("산패", "쩐내 — 기름 냄새가 변함", "오일 산화",
     "토코페롤 0.5~1% 추가, 차광·서늘 보관, 신선한 오일 사용", "항산화제", "항산화제가 산패를 늦춘다."),
    ("향·색", "배치마다 냄새·색이 다름", "도구에 향·색 이염 / 원료 로트 차이",
     "향·색 도구는 전용으로, 알코올 선세척, 같은 로트 사용", "(공정·도구)", "숨은 변수를 없애야 재현된다."),
    ("기포", "거품·기포가 많다", "과교반·공기 유입",
     "저속으로 바꾸고, 잔열에 30분~1시간 정치", "(공정)", "소용돌이가 깊으면 공기를 말아 넣는다."),
]

# ── 스타일 ─────────────────────────────────────────────────────────────────────
NAVY = "FF1F3A5F"
LBLUE = "FFDCE6F1"
GREY = "FFF2F2F2"
ORANGE = "FFFCE4D6"
REDFILL = PatternFill("solid", fgColor="FFFFC7CE")
PHASE_FILL = {"A": "FFDCE6F1", "B": "FFFCE4D6", "C": "FFE2EFDA", "pH": "FFF2F2F2", "?": "FFFFFFFF"}

thin = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
H = Font(bold=True, color="FFFFFFFF", size=11)
B = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
CEN = Alignment(horizontal="center", vertical="center")
REC_W = [20, 28, 5, 6, 7, 66]  # 레시피 카드 열폭(A..F)


def _rowheight(text: str, width_units: float, size: int = 11) -> float:
    per_line = max(10, int(width_units / 2))
    lines = max(1, math.ceil(len(str(text)) / per_line))
    return lines * (size + 4) + 2


def _title(ws, text: str, span: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    c = ws.cell(1, 1, text)
    c.font = Font(bold=True, size=14, color="FFFFFFFF")
    c.fill = PatternFill("solid", fgColor=NAVY)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30


def _header(ws, row: int, headers: list[str]) -> None:
    for j, h in enumerate(headers, 1):
        c = ws.cell(row, j, h)
        c.font = H
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = CEN
        c.border = BORDER


def _band(ws, r: int, text: str, fill: str, *, span: int = 6, bold: bool = True,
          color: str | None = None, size: int = 11, indent: int = 1, height: float | None = None) -> int:
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=span)
    c = ws.cell(r, 1, text)
    c.alignment = Alignment(wrap_text=True, vertical="center", indent=indent)
    c.fill = PatternFill("solid", fgColor=fill)
    c.font = Font(bold=bold, color=color or "FF000000", size=size)
    ws.row_dimensions[r].height = height or _rowheight(text, sum(REC_W[:span]), size)
    return r + 1


def _sheet_head(ws, title: str, desc: str, heads: list[str], widths: list[int]) -> int:
    """표 시트의 머리: 1행 제목 · 2행 설명띠(이 시트는 뭐·컬럼 뜻) · 3행 헤더.

    첫 데이터 행 번호(4)를 돌려준다. 열폭을 먼저 적용해 설명띠 높이를 맞춘다.
    """
    n = len(heads)
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    _title(ws, title, n)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
    c = ws.cell(2, 1, desc)
    c.alignment = Alignment(wrap_text=True, vertical="top", indent=1)
    c.fill = PatternFill("solid", fgColor=GREY)
    c.font = Font(size=10, color="FF404040")
    ws.row_dimensions[2].height = _rowheight(desc, sum(widths), 10)
    _header(ws, 3, heads)
    return 4


def _add_table(ws, name: str, top: int, bottom: int, ncols: int) -> None:
    """머리글 top행 + 데이터/빈칸 bottom행까지를 Excel 표로(필터·자동확장)."""
    ref = f"A{top}:{get_column_letter(ncols)}{bottom}"
    t = Table(displayName=name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)


def _dropdown(ws, formula1: str, cell_range: str) -> None:
    dv = DataValidation(type="list", formula1=formula1, allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(cell_range)


def _read_old(sheet: str) -> list[dict] | None:
    """기존 파일의 사용자 데이터(입출고·개발일지)를 '헤더 이름' 기준으로 읽는다.

    이름 기준이라 나중에 컬럼을 끼우거나 순서를 바꿔도 기록이 안 밀린다.
    헤더 행은 '셀 2개 이상 채워진 첫 행'으로 자동 탐지 — 설명띠(1칸만 채움)가
    2행에 있든 없든(구/신 레이아웃) 모두 호환.
    """
    if not OUT.exists():
        return None
    try:
        old = openpyxl.load_workbook(OUT, data_only=True, read_only=True)
    except Exception:
        return None
    if sheet not in old.sheetnames:
        old.close()
        return None
    rows = list(old[sheet].iter_rows(min_row=2, values_only=True))
    old.close()
    hdr = next((i for i, row in enumerate(rows)
                if sum(1 for v in row if v not in (None, "")) >= 2), None)
    if hdr is None:
        return None
    heads = [str(h).strip() if h is not None else "" for h in rows[hdr]]
    out: list[dict] = []
    for row in rows[hdr + 1:]:
        if all(v in (None, "") for v in row):
            continue
        out.append({heads[i]: row[i] for i in range(min(len(heads), len(row))) if heads[i]})
    return out


# 생성기가 매번 다시 그리는 시트(이 집합 밖의 시트는 '수작업 자산'으로 간주해 보존).
GENERATED_SHEETS = {"읽어보기", "레시피", "트러블슈팅", "원료", "도구", "입출고", "개발일지", "처방"}


def _copy_cell(src, dst) -> None:
    """값·스타일·하이퍼링크를 다른 워크북 셀로 그대로 옮긴다(스타일 객체는 복제)."""
    from copy import copy as _cp
    dst.value = src.value
    if src.has_style:
        dst.font = _cp(src.font)
        dst.fill = _cp(src.fill)
        dst.border = _cp(src.border)
        dst.alignment = _cp(src.alignment)
        dst.number_format = src.number_format
        dst.protection = _cp(src.protection)
    if src.hyperlink is not None:
        dst.hyperlink = _cp(src.hyperlink)


def _copy_sheet(src, dst) -> None:
    """워크북 간 시트 통째 복사(값·스타일·병합·치수·고정틀·이미지). 표/수식 없는 단순 시트용."""
    for row in src.iter_rows():
        for cell in row:
            if cell.value is None and not cell.has_style:
                continue
            _copy_cell(cell, dst.cell(row=cell.row, column=cell.column))
    for rng in src.merged_cells.ranges:
        dst.merge_cells(str(rng))
    for key, dim in src.column_dimensions.items():
        d = dst.column_dimensions[key]
        d.width, d.hidden = dim.width, dim.hidden
    for idx, dim in src.row_dimensions.items():
        d = dst.row_dimensions[idx]
        d.height, d.hidden = dim.height, dim.hidden
    dst.freeze_panes = src.freeze_panes
    dst.sheet_view.showGridLines = src.sheet_view.showGridLines
    for img in list(getattr(src, "_images", [])):
        dst.add_image(img)


def _preserve_from_old(wb) -> list[str]:
    """재생성으로 사라질 '수작업 자산'을 옛 파일에서 새 워크북으로 이식한다.

    생성기가 안 만드는 것 두 가지: ① 레시피 공정이미지(+G열 '▶' 링크) ② 추가 시트(시험 등).
    레시피 1~7 레이아웃은 재생성해도 동일 → 이미지(OneCellAnchor)·G열이 같은 행에 들어맞는다.
    저장(OUT 덮어쓰기) 직전에 호출해야 옛 파일을 읽을 수 있다. 보존한 항목 요약을 돌려준다.
    """
    if not OUT.exists():
        return []
    try:
        old = openpyxl.load_workbook(OUT)
    except Exception:
        return []
    done: list[str] = []
    # ① 레시피: 공정이미지 + 생성기가 안 쓰는 G열 이후(링크 등) 보존
    if "레시피" in old.sheetnames and "레시피" in wb.sheetnames:
        old_rec, new_rec = old["레시피"], wb["레시피"]
        imgs = list(getattr(old_rec, "_images", []))
        for img in imgs:
            new_rec.add_image(img)
        for row in old_rec.iter_rows(min_col=7):  # G열(7)~
            for cell in row:
                if cell.value is None and not cell.has_style:
                    continue
                _copy_cell(cell, new_rec.cell(row=cell.row, column=cell.column))
        for key, dim in old_rec.column_dimensions.items():
            if openpyxl.utils.column_index_from_string(key) >= 7:
                new_rec.column_dimensions[key].width = dim.width
        if imgs:
            done.append(f"레시피 공정이미지 {len(imgs)}개")
    # ①-b 그 외 생성 시트(트러블슈팅 등)의 수작업 이미지도 보존(레이아웃 안정 → 같은 앵커에 들어맞음)
    for name in ("트러블슈팅",):
        if name in old.sheetnames and name in wb.sheetnames:
            oimgs = list(getattr(old[name], "_images", []))
            for img in oimgs:
                wb[name].add_image(img)
            if oimgs:
                done.append(f"{name} 이미지 {len(oimgs)}개")
    # ② 생성기가 안 만드는 추가 시트 통째 복사(시험 시트 등)
    for name in old.sheetnames:
        if name in GENERATED_SHEETS or name in wb.sheetnames:
            continue
        _copy_sheet(old[name], wb.create_sheet(name))
        done.append(f"시트 '{name}'")
    return done


def build() -> Path:
    inv = yaml.safe_load((ROOT / "data" / "inventory.yaml").read_text(encoding="utf-8"))
    inv_items = {i["id"]: i for i in inv.get("ingredients", [])}

    # 원료 마스터 = 보유 원료 ∪ 레시피에 등장하는 원료(미보유는 최초보유 0)
    recipe_ids = {id_ for rec in RECIPES for (id_, *_rest) in rec["lines"]}
    all_ids = list(dict.fromkeys(list(inv_items.keys()) + [i for i in recipe_ids if i not in inv_items]))
    order = {"A": 0, "B": 1, "C": 2, "pH": 3, "?": 9}
    all_ids.sort(key=lambda i: (order.get(ing(i)["phase"], 9), ing(i)["ko"]))

    product_names = [r["name"] for r in RECIPES]
    DV_PROD = '"' + ",".join(product_names) + '"'

    # 보존 대상(사용자 기록). 신규 파일이면 개발일지는 trials.yaml로 시드.
    old_ledger = _read_old("입출고")
    old_log = _read_old("개발일지")
    # 도구 '보유·메모'는 사용자가 고칠 수 있으니 도구명으로 보존(재생성 시 덮지 않음)
    old_tools = {d.get("도구"): d for d in (_read_old("도구") or []) if d.get("도구")}

    wb = openpyxl.Workbook()

    # ── 1) 읽어보기 ──
    ws = wb.active
    ws.title = "읽어보기"
    _title(ws, "제품개발 마스터 — 읽어보기", 2)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 92
    r = 3
    for section, items in READ_ME:
        c = ws.cell(r, 1, section)
        c.font = B
        c.fill = PatternFill("solid", fgColor=LBLUE)
        c.alignment = WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        r += 1
        for it in items:
            ws.cell(r, 1, "·").alignment = CEN
            cc = ws.cell(r, 2, it)
            cc.alignment = WRAP
            ws.row_dimensions[r].height = _rowheight(it, 92)
            r += 1
        r += 1
    ws.cell(r, 2, "⚠ %·공정·pH는 설계·연습 기준(예시). 제조 전 TDS·pH·방부력·사용기한·전성분 검증. 화장품 표방 규칙 준수.").font = Font(italic=True, color="FFC00000")

    # ── 2) 레시피 (카드) ──
    ws = wb.create_sheet("레시피")
    _title(ws, "레시피 초안 — 제품마다 왜·무엇·어떻게 (100g 배치 = %가 그램)", 6)
    for j, w in enumerate(REC_W, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    r = 3
    for rec in RECIPES:
        r = _band(ws, r, f"[{rec['difficulty']}]   {rec['name']}   ·   {rec['type']}   ·   {rec['slug']}",
                  NAVY, bold=True, color="FFFFFFFF", size=12, height=26)
        r = _band(ws, r, f"컨셉 │ {rec['concept']}", GREY, bold=False)
        r = _band(ws, r, "설계 이유 (왜 이렇게 만들었나)", LBLUE, bold=True)
        for d in rec["design"]:
            r = _band(ws, r, f"· {d}", "FFFFFFFF", bold=False, indent=2)
        r = _band(ws, r, "특징 │ " + "  ·  ".join(rec["features"]), GREY, bold=False)
        _header(ws, r, ["원료", "INCI", "상", "%", "g(100g)", "이 원료가 하는 일"])
        r += 1
        total = 0.0
        for id_, phase, pct, note in rec["lines"]:
            m = ing(id_)
            total += pct
            why = WHY.get(id_, m["role"])
            if note:
                why = f"{why}  ※{note}"
            vals = [m["ko"], m["inci"], phase, pct, pct, why]
            for j, v in enumerate(vals, 1):
                c = ws.cell(r, j, v)
                c.border = BORDER
                c.alignment = WRAP if j in (2, 6) else (CEN if j in (3, 4, 5) else Alignment(vertical="top"))
            ws.cell(r, 3).fill = PatternFill("solid", fgColor=PHASE_FILL.get(phase, "FFFFFFFF"))
            ws.row_dimensions[r].height = _rowheight(why, REC_W[5])
            r += 1
        for j in range(1, 7):
            ws.cell(r, j).border = BORDER
            ws.cell(r, j).fill = PatternFill("solid", fgColor=LBLUE)
        ws.cell(r, 1, "합계").font = B
        ws.cell(r, 4, round(total, 1)).font = B
        ws.cell(r, 5, round(total, 1)).font = B
        ws.cell(r, 4).alignment = CEN
        ws.cell(r, 5).alignment = CEN
        r += 1
        r = _band(ws, r, "만드는 법", LBLUE, bold=True)
        for step in METHOD_STEPS[rec["method"]]:
            r = _band(ws, r, step, "FFFFFFFF", bold=False, indent=2)
        r += 1
    # ── 확장 사다리 플래그 (레시피 없음 — 히어로 검증 후 착수) ──
    r = _band(ws, r, "[⑨ (확장) 무수 밤·스틱 — 레시피는 히어로 검증·판매 후 착수]", ORANGE, bold=True)
    r = _band(ws, r, "· 물이 없어 방부·유화 부담이 낮아 1인 제조에 현실적 — 읽어보기 '확장 로드맵'의 확장 1순위.",
              GREY, bold=False, indent=2)
    r = _band(ws, r, "· 지금 승부처는 히어로 크림 하나. 무수 밤은 히어로가 물리 배치·검증·판매된 뒤 설계한다(지금 벌리면 분산).",
              GREY, bold=False, indent=2)
    ws.freeze_panes = "A3"

    # ── 2-b) 트러블슈팅 (이슈 → 어디를·뭘 바꾼다) ──
    ws = wb.create_sheet("트러블슈팅")
    heads = ["유형", "증상(이슈)", "원인", "조정 — 한 번에 하나만", "관련 역할", "왜"]
    desc = ("개발일지에 적은 '사용감·이슈'가 여기 '증상'과 맞는 걸 찾아 '조정'대로 한 축만 바꾼다 → 그 조정을 "
            "개발일지 '다음 아이디어'에 적고 다시 만든다.   ┃ '관련 역할'은 원료 시트의 '역할' 값과 같다 — "
            "원료 시트에서 그 역할로 필터하면 바꿀 후보 원료가 한눈에. ┃ %p=퍼센트포인트(%숫자를 그만큼↑/↓). ★한 번에 하나만.")
    first = _sheet_head(ws, "트러블슈팅 — 이슈가 나면 어디를·뭘 바꾸나", desc, heads,
                        [12, 24, 22, 38, 20, 28])
    r = first
    for typ, sym, cause, fix, role, why in TROUBLE:
        for j, v in enumerate([typ, sym, cause, fix, role, why], 1):
            cc = ws.cell(r, j, v)
            cc.border = BORDER
            cc.alignment = CEN if j == 1 else WRAP
        r += 1
    _add_table(ws, "트러블슈팅표", 3, r - 1, len(heads))
    # 표 아래: 불량 판정 레퍼런스 이미지 라벨(이미지는 _preserve로 행 21 앵커에 재이식)
    _band(ws, r + 1, "▼ 불량 판정 레퍼런스 — 만든 결과를 눈으로 대조 "
          "(①정상 ②층분리 ③오일링·크리밍 ④피시아이 ⑤이물질오염 ⑥기포)",
          LBLUE, bold=True, span=6, height=22)
    ws.freeze_panes = "C4"

    # ── 3) 원료 (재고 — 현재고 자동 수식) ──
    ws = wb.create_sheet("원료")
    heads = ["원료", "INCI", "상", "역할", "역할 설명", "세이프", "보관",
             "최초보유g", "구매g", "조정g", "제조사용g", "현재고g", "비고"]
    desc = ("지금 가진 원료와 '남은 양(현재고)'을 보는 재고판. 현재고는 자동 계산이라 직접 고치지 않는다 "
            "— 사면 '입출고', 쓰면 '개발일지'에 적으면 여기 숫자가 따라 움직인다.   "
            "┃ 역할=고정 11종(필터용) — 트러블슈팅 '관련 역할'과 같은 값이라, 이슈의 그 역할로 여기서 필터하면 바꿀 원료가 보인다. "
            "┃ 상=섞는 단계(A수상·B유상·C냉각·pH) · 세이프=히어로(말라세지아) 적합 O/X · "
            "현재고g=최초보유+구매+조정−제조사용(음수=빨강, 사야 함)")
    first = _sheet_head(ws, "원료 재고 — 현재고 = 최초보유 + 구매 + 조정 − 제조사용 (자동)", desc, heads,
                        [16, 28, 5, 14, 44, 7, 7, 10, 9, 9, 11, 11, 30])
    r = first
    for id_ in all_ids:
        m = ing(id_)
        data = inv_items.get(id_, {})
        init = data.get("on_hand_g", 0) or 0
        note = data.get("notes", "")
        if id_ not in inv_items:
            note = "★미보유(구매 필요)" + (f" · {note}" if note else "")
        role = crole(id_)
        ws.cell(r, 1, m["ko"])
        ws.cell(r, 2, m["inci"])
        ws.cell(r, 3, m["phase"])
        ws.cell(r, 4, role)
        ws.cell(r, 5, ROLE_DESC.get(role, ""))
        ws.cell(r, 6, "O" if m["safe"] else "X")
        ws.cell(r, 7, data.get("storage", ""))
        ws.cell(r, 8, init)
        ws.cell(r, 9, '=SUMIFS(입출고표[수량g],입출고표[원료],[@원료],입출고표[구분],"구매")')
        ws.cell(r, 10, '=SUMIFS(입출고표[수량g],입출고표[원료],[@원료],입출고표[구분],"조정")')
        ws.cell(r, 11, "=SUMIF(처방표[원료],[@원료],처방표[사용g])")
        ws.cell(r, 12, "=[@최초보유g]+[@구매g]+[@조정g]-[@제조사용g]")
        ws.cell(r, 13, note)
        for j in range(1, len(heads) + 1):
            cc = ws.cell(r, j)
            cc.border = BORDER
            cc.alignment = WRAP if j in (2, 5, 13) else (CEN if j in (3, 6, 7, 8, 9, 10, 11, 12) else Alignment(vertical="top"))
        ws.cell(r, 3).fill = PatternFill("solid", fgColor=PHASE_FILL.get(m["phase"], "FFFFFFFF"))
        if not m["safe"]:
            ws.cell(r, 6).fill = PatternFill("solid", fgColor=ORANGE)
        r += 1
    stock_last = r - 1
    _add_table(ws, "원료표", 3, stock_last, len(heads))
    _dropdown(ws, '"' + ",".join(ROLES) + '"', f"D{first}:D{stock_last}")  # 역할 고정 어휘(향료 포함)
    ws.conditional_formatting.add(f"L{first}:L{stock_last}",
                                  CellIsRule(operator="lessThan", formula=["0"], fill=REDFILL))
    ws.freeze_panes = "C4"

    # ── 3-b) 도구 (장비·소모품 모음) ──
    ws = wb.create_sheet("도구")
    heads = ["분류", "도구", "권장규격·모델", "용도", "보유", "메모"]
    desc = ("실험에 쓰는 장비·소모품 모음. 분류·보유로 필터해서 '뭘 더 사야 하나'를 본다. "
            "'보유'·'메모'는 네가 고쳐도 재생성 때 보존된다.   "
            "┃ 보유 값: 보유=가지고 있음 · 추천=있으면 좋음(필요 시 구매) · 소모품=떨어지면 보충 · 필수=없으면 시작 금지")
    first = _sheet_head(ws, "도구 모음 — 보유/추천 장비·소모품", desc, heads,
                        [12, 26, 26, 34, 8, 26])
    r = first
    for cat, name, spec, use, have in TOOLS:
        prev = old_tools.get(name)  # 사용자가 고친 보유·메모 보존
        vals = [cat, name, spec, use,
                (prev or {}).get("보유") or have,
                (prev or {}).get("메모") or ""]
        for j, v in enumerate(vals, 1):
            cc = ws.cell(r, j, v)
            cc.border = BORDER
            cc.alignment = CEN if j == 5 else WRAP if j in (3, 4, 6) else Alignment(vertical="top")
        r += 1
    tools_last = r - 1
    _add_table(ws, "도구표", 3, tools_last, len(heads))
    _dropdown(ws, '"보유,추천,소모품,필수,미보유"', f"E{first}:E{tools_last}")
    ws.freeze_panes = "C4"

    # ── 4) 입출고 (구매·조정 원장) ──
    ws = wb.create_sheet("입출고")
    heads = ["날짜", "원료", "구분", "수량g", "출처·단가", "메모"]
    desc = ("원료를 사거나(구매) 버릴 때(조정) 한 줄씩 쌓는 장부. 여기 적으면 '원료' 시트의 현재고가 자동으로 오르내린다.   "
            "┃ 컬럼: 날짜=기록일 · 원료=아래 칸 클릭해 드롭다운 선택 · 구분=구매 또는 조정 · "
            "수량g=구매는 +, 흘림·폐기는 −(음수)로 · 출처·단가=어디서 얼마에 · 메모=로트·개봉일 등")
    first = _sheet_head(ws, "입출고 — 사면 '구매', 버리면 '조정(음수)'. 한 줄씩 쌓기", desc, heads,
                        [13, 20, 9, 10, 22, 34])
    r = first
    for d in (old_ledger or []):
        for j, h in enumerate(heads, 1):
            ws.cell(r, j, d.get(h))
        r += 1
    blank_end = max(r - 1, first - 1) + 60  # 입력용 여유 줄
    for rr in range(first, blank_end + 1):
        for j in range(1, len(heads) + 1):
            ws.cell(rr, j).border = BORDER
    _add_table(ws, "입출고표", 3, blank_end, len(heads))
    _dropdown(ws, f"원료!$A${first}:$A${stock_last}", f"B{first}:B{blank_end}")
    _dropdown(ws, '"구매,조정"', f"C{first}:C{blank_end}")
    ws.freeze_panes = "A4"

    # ── 5) 개발일지 (배치 제조 + 실험 판정) ──
    ws = wb.create_sheet("개발일지")
    heads = ["날짜", "제품", "배치량g", "기준(base)", "바꾼것", "유화ok", "분리mm", "pH", "사용감", "이슈", "판정", "다음 아이디어"]
    desc = ("배치를 만들고 평가한 걸 한 줄씩 남기는 기록. '제품+배치량g'을 적으면 그 레시피대로 원료가 재고에서 자동 차감된다. "
            "한 번에 한 가지만 바꾼다.   ┃ 컬럼: 제품=드롭다운 · 배치량g=만든 총량(재고 차감의 핵심) · "
            "기준(base)=어느 버전에서 출발 · 바꾼것=이번에 바꾼 한 가지 · 유화ok=유화 성공(ok/실패) · "
            "분리mm=원심(LC-8S) 분리층, 0이면 안정 · pH=측정값(5.0~5.5) · 판정=keeper/튜닝/접기(접은 것도 데이터)")
    first = _sheet_head(ws, "개발일지 — 제품+배치량g 적으면 재고 자동 차감 · 분리mm=원심 판정(LC-8S)", desc, heads,
                        [13, 20, 9, 16, 24, 8, 8, 7, 20, 18, 10, 26])
    seeded: list[dict] = []
    if old_log is not None:
        seeded = old_log
    else:  # 신규 파일 → trials.yaml 시드
        tpath = ROOT / "experiments" / "trials.yaml"
        if tpath.exists():
            tdata = yaml.safe_load(tpath.read_text(encoding="utf-8")) or {}
            for t in tdata.get("trials", []) or []:
                em = t.get("emulsion_ok")
                seeded.append({
                    "날짜": t.get("date", ""), "기준(base)": t.get("base", ""),
                    "바꾼것": t.get("changed", ""),
                    "유화ok": "ok" if em is True else ("실패" if em is False else ""),
                    "pH": t.get("ph", ""), "사용감": t.get("sensory", ""),
                    "이슈": t.get("issues", ""), "판정": t.get("verdict", ""),
                    "다음 아이디어": t.get("next_idea", ""),
                })
    r = first
    for d in seeded:
        for j, h in enumerate(heads, 1):
            ws.cell(r, j, d.get(h))
        r += 1
    blank_end = max(r - 1, first - 1) + 60
    for rr in range(first, blank_end + 1):
        for j in range(1, len(heads) + 1):
            ws.cell(rr, j).border = BORDER
    _add_table(ws, "개발일지표", 3, blank_end, len(heads))
    # 열 위치: 제품 B · 유화ok F · 판정 K (분리mm 삽입으로 J→K)
    _dropdown(ws, DV_PROD, f"B{first}:B{blank_end}")
    _dropdown(ws, '"ok,실패"', f"F{first}:F{blank_end}")
    _dropdown(ws, '"keeper,튜닝,접기"', f"K{first}:K{blank_end}")
    ws.freeze_panes = "A4"

    # ── 6) 처방 (레시피 %를 표로 — 재고 연계 엔진) ──
    ws = wb.create_sheet("처방")
    heads = ["제품", "원료", "상", "퍼센트", "제조누계g", "사용g"]
    desc = ("레시피의 %를 표로 편 '재고 연계 엔진'. 보통은 안 봐도 된다(레시피는 '레시피' 시트에서 봄) — "
            "재고 자동 차감을 위해 존재한다.   ┃ 컬럼: 제품=제품명 · 원료=한글명 · 상=단계 · 퍼센트=배합% · "
            "제조누계g=개발일지에서 이 제품을 만든 배치량 합(자동) · 사용g=퍼센트×제조누계(원료 시트가 이 값을 빼감)")
    first = _sheet_head(ws, "처방 — 레시피 %의 표(재고 연계 엔진)", desc, heads,
                        [24, 22, 5, 9, 12, 10])
    r = first
    for rec in RECIPES:
        for id_, phase, pct, _note in rec["lines"]:
            ws.cell(r, 1, rec["name"])
            ws.cell(r, 2, ing(id_)["ko"])
            ws.cell(r, 3, phase)
            ws.cell(r, 4, pct)
            ws.cell(r, 5, "=SUMIF(개발일지표[제품],[@제품],개발일지표[배치량g])")
            ws.cell(r, 6, "=[@퍼센트]/100*[@제조누계g]")
            for j in range(1, 7):
                cc = ws.cell(r, j)
                cc.border = BORDER
                cc.alignment = CEN if j in (3, 4, 5, 6) else Alignment(vertical="top")
            ws.cell(r, 3).fill = PatternFill("solid", fgColor=PHASE_FILL.get(phase, "FFFFFFFF"))
            r += 1
    _add_table(ws, "처방표", 3, r - 1, 6)
    ws.freeze_panes = "A4"

    # ── 보존: 생성기가 안 만드는 수작업 자산(레시피 공정이미지 + 추가 시트)을 저장 직전 이식 ──
    preserved = _preserve_from_old(wb)

    try:
        wb.save(OUT)
    except PermissionError:
        print("⛔ 저장 실패 — 엑셀에서 '제품개발_마스터.xlsx'를 닫고 다시 실행하세요.")
        raise
    return OUT, preserved


if __name__ == "__main__":
    path, preserved = build()
    print("✅ 생성 →", path)
    print("   시트(8): 읽어보기 · 레시피 · 트러블슈팅 · 원료 · 도구 · 입출고 · 개발일지 · 처방")
    print("   재고=최초보유+구매+조정−제조사용(자동) · 입출고/개발일지 기록은 재생성해도 보존")
    if preserved:
        print("   보존(이식): " + " · ".join(preserved))
