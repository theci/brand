"""하위 호환 shim. 실제 정의는 brandlab.core.scaling 로 이동했다(P9 레짐 리팩터링).

새 코드는 `from brandlab.core.scaling import ...` 를 사용하는 것을 권장한다.
"""

from brandlab.core.scaling import *  # noqa: F401,F403
