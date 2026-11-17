import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import URL

from .demo_target import validate_demo_target


def environment_values():
    return {**dotenv_values(Path(__file__).resolve().parents[1] / ".env"), **os.environ}


class RuntimeSettings(BaseModel):
    environment: Literal['development', 'production'] = 'development'
    demo_mode: bool = False
    cors_origins: list[str] = []
    serve_frontend: bool = False


def get_runtime_settings() -> RuntimeSettings:
    values = environment_values()
    try:
        settings = RuntimeSettings(
            environment=values.get('APP_ENV', 'development'),
            demo_mode=values.get('FINFLOW_DEMO_MODE', 'false'),
            cors_origins=[item.strip() for item in values.get('CORS_ORIGINS', '').split(',') if item.strip()],
            serve_frontend=values.get('FINFLOW_SERVE_FRONTEND', 'false'),
        )
        for origin in settings.cors_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path
                    or parsed.query or parsed.fragment or parsed.username or parsed.password
                    or '*' in origin or (settings.environment == 'production' and parsed.scheme != 'https')):
                raise ValueError()
        if settings.environment == 'production' and not settings.demo_mode:
            raise ValueError()
        # Public mode cannot accidentally expose this checkout's existing database.
        if settings.demo_mode:
            validate_demo_target(values.get('DB_NAME'), values.get('DB_HOST'),
                                 values.get('DB_USER'), values.get('DB_PORT'),
                                 values.get('FINFLOW_SUPABASE_PROJECT_REF'))
        return settings
    except (ValueError, TypeError):
        raise RuntimeError('Invalid runtime configuration. Production requires FINFLOW_DEMO_MODE=true; '
                           'demo mode requires finflow_demo or an explicitly confirmed Supabase target; '
                           'CORS origins must be explicit '
                           'origins (HTTPS in production), without trailing slashes.') from None


class Settings(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    name: str
    user: str
    password: SecretStr
    sslmode: Literal['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'] = 'prefer'
    sslrootcert: str | None = None

    @property
    def database_url(self) -> URL:
        return URL.create("postgresql+psycopg", username=self.user,
                          password=self.password.get_secret_value(), host=self.host,
                          port=self.port, database=self.name,
                          query={'sslmode': self.sslmode, **({'sslrootcert': self.sslrootcert} if self.sslrootcert else {})})


def get_settings() -> Settings:
    values = environment_values()
    try:
        runtime = get_runtime_settings()
        settings = Settings(host=values["DB_HOST"], port=values["DB_PORT"],
                            name=values["DB_NAME"], user=values["DB_USER"],
                            password=values["DB_PASSWORD"],
                            sslmode=values.get('DB_SSLMODE', 'verify-full' if runtime.environment == 'production' else 'prefer'),
                            sslrootcert=values.get('DB_SSLROOTCERT') or ('system' if runtime.environment == 'production' else None))
        if (runtime.environment == 'production' or (runtime.demo_mode and settings.name == 'postgres')) and settings.sslmode != 'verify-full':
            raise ValueError()
        if runtime.environment == 'production':
            expected_user = 'finflow_reader'
            if settings.name == 'postgres' and settings.host.endswith('.pooler.supabase.com'):
                expected_user += '.' + values['FINFLOW_SUPABASE_PROJECT_REF']
            if settings.user != expected_user:
                raise ValueError()
        if not all((settings.host, settings.name, settings.user, settings.password.get_secret_value())):
            raise ValueError()
        return settings
    except (KeyError, ValueError, TypeError):
        raise RuntimeError('Invalid database configuration. Check DB_* settings. '
                           'Production requires the finflow_reader runtime user '
                           '(with the confirmed project suffix for Supabase session pooling).') from None
