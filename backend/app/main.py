from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_runtime_settings, get_settings
from .database import get_db
from .db_diagnostics import log_database_failure
from .transactions import router
from .financial_routes import router as financial_router
from .exchange_rates import RatesUnavailable
from .profiles import router as profiles_router


def create_app(runtime=None):
    runtime = runtime or get_runtime_settings()
    if runtime.environment == 'production':
        get_settings()  # Fail before serving if production DB/TLS configuration is invalid.
    application = FastAPI(title="FinFlow AI", description="Financial Analytics Backend", version="1.0.0")

    @application.middleware('http')
    async def demo_read_only(request, call_next):
        # Default-deny every unsafe method, including future routes. The assistant
        # POST only computes a response and never persists chat or financial data.
        allowed = request.method in {'GET', 'HEAD', 'OPTIONS'} or (
            request.method == 'POST' and request.url.path == '/api/assistant/query')
        if runtime.demo_mode and not allowed:
            return JSONResponse(status_code=403, content={'detail': {
                'code': 'demo_read_only', 'message': 'This fictional public demo is read-only.'}})
        return await call_next(request)

    application.add_middleware(CORSMiddleware, allow_origins=runtime.cors_origins,
                               allow_credentials=False, allow_methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
                               allow_headers=['Content-Type'])
    application.include_router(router)
    application.include_router(financial_router)
    application.include_router(profiles_router)

    @application.exception_handler(RatesUnavailable)
    async def rates_error_handler(request, exc):
        return JSONResponse(status_code=503, content={'detail': exc.detail})

    @application.exception_handler(SQLAlchemyError)
    async def database_error_handler(request, exc):
        log_database_failure(exc, getattr(request.state, 'database_stage', 'operation'))
        return JSONResponse(status_code=503, content={"detail": "Database operation unavailable"})

    @application.get('/healthz', include_in_schema=False)
    @application.get('/api/health')
    def health_check():
        return {"status": "healthy", "service": "FinFlow AI Backend"}

    @application.get('/api/readiness')
    def readiness(request: Request, db: Session = Depends(get_db)):
        request.state.database_stage = 'connect'
        db.connection()  # Separate connection/TLS/authentication failures from SQL failures.
        request.state.database_stage = 'readiness_probe'
        db.execute(text('SELECT 1'))
        request.state.database_stage = 'schema_revision'
        revision = db.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if revision != ['0003']:
            raise HTTPException(503, 'Database requires schema revision 0003')
        return {'status': 'ready', 'demo_mode': runtime.demo_mode}

    @application.get('/api/config')
    def public_config():
        return {'demo_mode': runtime.demo_mode}

    if runtime.serve_frontend:
        dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
        if not (dist / 'index.html').is_file() or not (dist / 'assets').is_dir():
            raise RuntimeError('Build frontend/dist before enabling FINFLOW_SERVE_FRONTEND.')
        application.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

        @application.get('/', include_in_schema=False)
        @application.get('/transactions', include_in_schema=False)
        @application.get('/analytics', include_in_schema=False)
        @application.get('/assistant', include_in_schema=False)
        def frontend():
            return FileResponse(dist / 'index.html')
    else:
        @application.get('/')
        def home():
            return {"message": "Welcome to FinFlow AI", "status": "Backend is running"}

    return application


app = create_app()
