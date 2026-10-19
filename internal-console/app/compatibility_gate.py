"""Console error projection over the single native Compatibility fence."""
import functools

from .canonical_gateway import CanonicalOperationError
from profile_compatibility_consumers_v1_1 import guarded as native_guarded
from profile_compatibility_contract_v1_1 import CompatibilityError
from operation_lock_v1 import OperationLockTimeout
from profile_compatibility_release_v1_1 import CONFIG, effective_runtime


def guarded(function):
    native = native_guarded(function)
    @functools.wraps(function)
    def call(*args, **kwargs):
        try:
            return native(*args, **kwargs)
        except (CompatibilityError, OperationLockTimeout) as exc:
            raise CanonicalOperationError('PROFILE_COMPATIBILITY_BLOCKED',
                '创作参考的兼容性批准或发布状态已变化，当前不能继续。',
                '请由兼容性审核人核对当前版本并完成发布激活；已保存的工作和历史记录会保留。') from exc
    return call


def checked_subprocess(function):
    """The actual child writer owns the long-lived fence; never lock across it."""
    @functools.wraps(function)
    def call(settings, *args, **kwargs):
        if (settings.pipeline_root / CONFIG).is_file():
            try:
                effective_runtime(settings.pipeline_root)
            except (CompatibilityError, OperationLockTimeout) as exc:
                raise CanonicalOperationError('PROFILE_COMPATIBILITY_BLOCKED',
                    '创作参考的兼容性批准或发布状态已变化，当前不能继续。',
                    '请核对并激活当前版本；已有记录会保留。') from exc
        return function(settings, *args, **kwargs)
    return call
