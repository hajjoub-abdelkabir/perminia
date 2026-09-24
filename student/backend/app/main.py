from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine
from app.student import router as student_router
from app.auth import AuthRequestGuard, router as auth_router
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

app = FastAPI(title="Sya9a Student API", version="0.1.0")
app.add_middleware(AuthRequestGuard)
app.include_router(student_router)
app.include_router(auth_router)
from app.lessons import router as lessons_router
app.include_router(lessons_router)
from app.journey import router as journey_router
from app.coach import router as coach_router
app.include_router(journey_router)
app.include_router(coach_router)
from app.training import router as training_router
app.include_router(training_router)
from app.daily_plan import router as daily_plan_router
app.include_router(daily_plan_router)
from app.notebook import router as notebook_router
app.include_router(notebook_router)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Validation responses must never echo passwords or submitted credentials.
    return JSONResponse(status_code=422, content={
        'detail': 'راجع المعطيات اللي دخلتي. الاسم خاصو يكون بين 2 و80 حرف، وكلمة السر ديال الحساب الجديد بين 12 و128 حرف.'
        if request.url.path.startswith('/api/v1/auth/') else 'Invalid request data'
    }, headers={'Cache-Control': 'no-store'})


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'الخدمة ما متاحةش دابا. عاود جرّب من بعد شوية.'},
                        headers={'Cache-Control': 'no-store'})


@app.get("/api/v1/health/live")
def live():
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def ready():
    try:
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT instance_id, created_at FROM app_bootstrap WHERE id = 1"
            )).one()
        return {
            "status": "ready",
            "database": "connected",
            "scope": "student",
            "instance_id": str(row.instance_id),
            "initialized_at": row.created_at.isoformat(),
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database or migration unavailable") from None

from app.school import router as school_router
app.include_router(school_router)
from app.chat import router as chat_router
app.include_router(chat_router)

# Optional compiled UI for the isolated local showcase, mounted after every API route.
import os
from fastapi.staticfiles import StaticFiles
if os.environ.get('PERMINIA_WEB_ROOT'):
    app.mount('/', StaticFiles(directory=os.environ['PERMINIA_WEB_ROOT'], html=True), name='web')
