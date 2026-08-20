"""하위 호환 shim. 실제 정의는 brandlab.core.models 로 이동했다(P9 레짐 리팩터링).

기존 `from brandlab.models import ...` 경로를 유지하기 위해 재노출한다.
새 코드는 `from brandlab.core.models import ...` 를 사용하는 것을 권장한다.
"""

from brandlab.core.models import *  # noqa: F401,F403
