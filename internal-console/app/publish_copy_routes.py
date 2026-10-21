"""Existing creation delivery page endpoints; no client-selected filesystem paths."""
from fastapi import Depends, Header, HTTPException, Body
from fastapi.responses import FileResponse
from .canonical_gateway import CanonicalOperationError
from .content_delivery_gateway import delivery_authorization
from . import publish_copy_gateway as gateway

def register_routes(app, settings, access, csrf, runner):
    @app.get('/api/publish-copy/capability')
    def capability(session=Depends(access)):
        return {'enabled': settings.publish_copy_enabled}

    def allowed(payload, keys):
        if not isinstance(payload, dict) or set(payload) - set(keys):
            raise HTTPException(422, detail={'code': 'PUBLISH_COPY_INPUT_INVALID', 'message': '提交内容需要重新核对。'})

    @app.get('/api/create/{request_id}/publish-copy')
    def state(request_id: str, session=Depends(access)):
        return {'state': gateway.project(settings, request_id)}

    @app.post('/api/create/{request_id}/publish-copy/generate')
    def generate(request_id: str, payload: dict = Body(default={}),
                 x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'), session=Depends(access)):
        csrf(session, x_csrf_token); allowed(payload, ['target_ids', 'expected_parent', 'retry_confirmation'])
        if payload.get('expected_parent') and payload.get('retry_confirmation') != 'explicit_retry_possible_additional_cost':
            raise HTTPException(422, detail={'code': 'PUBLISH_COPY_RETRY_CONFIRMATION_REQUIRED', 'message': '重新尝试可能产生额外费用，请明确确认。'})
        result = gateway.submit(settings, request_id, 'publish_copy_generate', int(session.user['id']),
            delivery_authorization(settings, session), target_ids=payload.get('target_ids'), expected_parent=payload.get('expected_parent'))
        if result['accepted']: runner.schedule(result['task']['task_id'])
        return result

    @app.post('/api/create/{request_id}/publish-copy/edit')
    def edit(request_id: str, payload: dict = Body(...),
             x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'), session=Depends(access)):
        csrf(session, x_csrf_token); allowed(payload, ['draft_ref', 'payload'])
        return {'result': gateway.native(settings, request_id, 'edit', **payload, authorization_context=delivery_authorization(settings, session))}

    @app.post('/api/create/{request_id}/publish-copy/confirm')
    def confirm(request_id: str, payload: dict = Body(...),
                x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'), session=Depends(access)):
        csrf(session, x_csrf_token); allowed(payload, ['draft_ref'])
        return {'result': gateway.native(settings, request_id, 'confirm', **payload, authorization_context=delivery_authorization(settings, session))}

    @app.post('/api/create/{request_id}/publish-copy/export')
    def export(request_id: str, x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'), session=Depends(access)):
        csrf(session, x_csrf_token)
        result = gateway.submit(settings, request_id, 'publish_copy_export', int(session.user['id']), delivery_authorization(settings, session))
        if result['accepted']: runner.schedule(result['task']['task_id'])
        return result

    @app.get('/api/create/{request_id}/publish-copy/excel/{delivery_id}')
    def download(request_id: str, delivery_id: str, session=Depends(access)):
        from publish_copy_contract_v1 import identifier
        identifier(delivery_id, r'[a-f0-9]{32}')
        current = gateway.native(settings, request_id, 'version',delivery_id=delivery_id)
        if not current:
            raise CanonicalOperationError('PUBLISH_COPY_DELIVERY_UNAVAILABLE', '这份交付当前不可下载。', '请核对当前有效交付版本。')
        return FileResponse(current['output_path'], filename='发布交付_' + request_id + '.xlsx',
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
