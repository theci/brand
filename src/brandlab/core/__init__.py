"""레짐(규제 레짐) 무관 핵심 로직.

어떤 법이 적용되든 동일한 것만 둔다: 데이터 모델, 배치 스케일링, 원가 계산.
규제별 로직은 brandlab.regimes 아래에 둔다.
"""

from . import costing, models, scaling

__all__ = ["models", "scaling", "costing"]
