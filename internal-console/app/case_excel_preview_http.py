"""Ephemeral upload adapter. Never stores a workbook, candidate or task."""
from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from .case_excel_preview import MAX_FILE, PreviewError, preview_workbook


async def preview_upload(request: Request):
    headers = {'Cache-Control': 'private, no-store'}
    def reject(code, message, status=422):
        return JSONResponse({'detail': {'code': code, 'message': message}}, status_code=status, headers=headers)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() not in {
        'application/octet-stream', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    }:
        return reject('EXCEL_PREVIEW_CONTENT_TYPE', '请选择 V0.3 的 XLSX 文件。', 415)
    length = request.headers.get('content-length')
    if length is not None:
        if not length.isascii() or not length.isdecimal():
            return reject('EXCEL_PREVIEW_LENGTH_INVALID', '文件长度无效。')
        if len(length) > 10 or int(length) > MAX_FILE:
            return reject('FILE_BUDGET_EXCEEDED', '文件超过当前预检的 5 MiB 输入上限。', 413)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FILE:
            return reject('FILE_BUDGET_EXCEEDED', '文件超过当前预检的 5 MiB 输入上限。', 413)
        body.extend(chunk)
    if not body:
        return reject('EXCEL_PREVIEW_EMPTY', '文件为空，请重新选择。')
    try:
        result = await run_in_threadpool(preview_workbook, bytes(body))
    except PreviewError as exc:
        return reject(exc.code, '文件未通过 V0.3 模板或安全校验，请核对原文件后重试。')
    return JSONResponse({'preview': result}, headers=headers)
