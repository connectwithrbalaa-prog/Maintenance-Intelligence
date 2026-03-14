import json
from typing import Any, Dict

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    kafka_bootstrap: str = Field(default="kafka:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    pg_db: str = Field(default="maintenance", alias="POSTGRES_DB")
    pg_user: str = Field(default="postgres", alias="POSTGRES_USER")
    pg_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    pg_host: str = Field(default="timescaledb", alias="POSTGRES_HOST")
    ttr_fallback_window_h: int = Field(default=24)
    multi_tenant: bool = Field(default=False, alias="MI_MULTI_TENANT")
    default_org: str = Field(default="default-org", alias="MI_DEFAULT_ORG")
    auth_mode: str = Field(default="none", alias="MI_AUTH_MODE")
    api_keys_raw: str = Field(default="{}", alias="MI_API_KEYS")
    kafka_tenant_mode: str = Field(default="message", alias="MI_KAFKA_TENANT_MODE")
    prompt_defaults_raw: str = Field(default='{"rca":"rca-default-v1"}', alias="MI_PROMPT_DEFAULTS")
    prompt_canary_defaults_raw: str = Field(default='{"rca":"rca-canary-v1"}', alias="MI_PROMPT_CANARY_DEFAULTS")
    prompt_canary_ratio: float = Field(default=0.1, alias="MI_PROMPT_CANARY_RATIO")
    genai_model: str = Field(default="gpt-4.1")
    genai_timeout_s: int = Field(default=25)
    run_summary_dir: str = Field(default="outputs")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    @property
    def pg_dsn(self) -> str:
        return f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password} host={self.pg_host} port=5432"

    @property
    def database_url(self) -> str:
        return self.pg_dsn

    @property
    def api_keys(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(self.api_keys_raw or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def prompt_defaults(self) -> Dict[str, str]:
        try:
            data = json.loads(self.prompt_defaults_raw or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def prompt_canary_defaults(self) -> Dict[str, str]:
        try:
            data = json.loads(self.prompt_canary_defaults_raw or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    class Config:
        env_prefix = "MI_"
        extra = "allow"
