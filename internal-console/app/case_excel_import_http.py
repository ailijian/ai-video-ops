"""Bounded JSON adapter for the explicitly confirmed private-candidate save."""
import json

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from . import case_intake_service as intake
from .case_excel_import import ImportError, PrepareInput, SaveInput, RecoverInput, CancelInput

MAX_REQUEST = 8 * 1024 * 1024
HEADERS = {'Cache-Control': 'private, no-store'}


def failure(exc):
    messages = {
        'EXCEL_NATIVE_MEDIA_REQUIRED': '请先在导入记录中绑定与来源对应的有效视频，或恢复原获取方式。',
        'EXCEL_NATIVE_SUPPORTED_SOURCE_REQUIRED': '这条投稿缺少当前支持的原视频来源，请补充合法来源后再解析。',
        'EXCEL_NATIVE_PREVIEW_CHANGED': '来源、资格或原保存状态已变化，请重新核对解析内容。',
        'EXCEL_NATIVE_INTENT_CONFLICT': '同一解析操作已绑定其他内容，请保留并查回原操作。',
        'EXCEL_NATIVE_RECOVERY_REQUIRED': '解析提交尚未完成，请继续原操作；不会创建第二个任务。',
        'CASE_EXTERNAL_RESULT_UNKNOWN': '原分析结果未知，请核对原任务，不能重新派发模型。',
        'IMPORT_UPLOAD_REBIND_REQUIRED': '视频上传已过期、被使用或与此行来源不符，请明确重新绑定后核对。',
        'IMPORT_HEAD_CHANGED': '保存状态已变化，请重新读取并核对保存内容。',
        'IMPORT_INTENT_CONFLICT': '同一保存编号已用于不同内容，请保留原操作并重新核对。',
        'IMPORT_PREVIEW_CHANGED': '文件、解析版本或核对结果已变化，请重新核对保存内容。',
        'IMPORT_RECOVERY_REQUIRED': '已有未完成的保存，请先从原记录恢复或取消尚未保存的行。',
        'IMPORT_ACCESS_CHANGED': '登录权限已变化，请重新登录后继续。',
    }
    return JSONResponse({'detail': {'code': exc.code, 'message': messages.get(exc.code, '当前无法处理该投稿，请核对文件、来源及保存状态。')}}, status_code=exc.status, headers=HEADERS)


async def body(request, model):
    if request.headers.get('content-type', '').split(';')[0].lower().strip() != 'application/json':
        raise ImportError('IMPORT_CONTENT_TYPE_INVALID', 415)
    length = request.headers.get('content-length')
    if length is not None and (not length.isascii() or not length.isdecimal()):
        raise ImportError('IMPORT_LENGTH_INVALID', 422)
    if length is not None and (len(length) > 10 or int(length) > MAX_REQUEST):
        raise ImportError('IMPORT_BODY_TOO_LARGE', 413)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_REQUEST:
            raise ImportError('IMPORT_BODY_TOO_LARGE', 413)
        data.extend(chunk)
    try:
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError('Duplicate key')
                value[key] = item
            return value
        return model.model_validate(json.loads(data, object_pairs_hook=unique))
    except (ValueError, ValidationError, RecursionError) as exc:
        raise ImportError('IMPORT_INPUT_INVALID', 422) from exc


async def execute(request, settings, session, *, save=False, batch_id=None, cancel=False):
    try:
        model = CancelInput if cancel else RecoverInput if batch_id else SaveInput if save else PrepareInput
        payload = await body(request, model)
        if batch_id:
            function = intake.cancel_excel_import if cancel else intake.recover_excel_import
            result = await run_in_threadpool(function, settings, session, batch_id, payload)
        else:
            function = intake.save_excel_import if save else intake.prepare_excel_import
            result = await run_in_threadpool(function, settings, session, payload)
        return JSONResponse(result, headers=HEADERS)
    except ImportError as exc:
        return failure(exc)
    except OSError:
        return failure(ImportError('IMPORT_RECOVERY_REQUIRED', 503))
