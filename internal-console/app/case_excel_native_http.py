"""Authenticated bounded DTO adapter. Case Intake retains the only writer."""
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from . import case_intake_service as intake
from . import case_excel_native as native
from .case_excel_import import ImportError
from .case_excel_import_http import body, failure, HEADERS


async def execute(request,settings,session,batch,row,schedule=None):
    class DTO:
        @staticmethod
        def model_validate(value):
            return native.checked(value,'NativeSubmissionInput' if schedule else 'NativePrepareInput')
    try:
        payload=await body(request,DTO)
        function=intake.submit_excel_native if schedule else intake.preview_excel_native
        args=(settings,session,batch,row,payload)+((schedule,) if schedule else ())
        return JSONResponse(await run_in_threadpool(function,*args),headers=HEADERS)
    except ImportError as exc:
        return failure(exc)
    except native.TaskSubmissionError as exc:
        return failure(ImportError(exc.code,409))
    except native.OperationLockTimeout:
        return failure(ImportError('EXCEL_NATIVE_BUSY',409))
    except RuntimeError:
        return failure(ImportError('EXCEL_NATIVE_CONFLICT',409))
    except OSError:
        return failure(ImportError('EXCEL_NATIVE_RECOVERY_REQUIRED',503))
