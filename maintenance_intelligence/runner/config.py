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
    prompt_canary_defaults_raw: str = Field(
        default='{"rca":"rca-canary-v1"}', alias="MI_PROMPT_CANARY_DEFAULTS"
    )
    prompt_canary_ratio: float = Field(default=0.1, alias="MI_PROMPT_CANARY_RATIO")
    rca_model_rates_raw: str = Field(
        default='{"gpt-4.1":{"per_1k_tokens_usd":0.01},"unset":{"per_1k_tokens_usd":0.0}}',
        alias="MI_RCA_MODEL_RATES",
    )
    rca_budget_caps_usd_raw: str = Field(
        default='{"daily":25.0,"weekly":100.0}', alias="MI_RCA_BUDGET_CAPS_USD"
    )
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

    @property
    def rca_model_rates(self) -> Dict[str, float]:
        try:
            data = json.loads(self.rca_model_rates_raw or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        parsed: Dict[str, float] = {}
        for model_name, raw_value in data.items():
            if isinstance(raw_value, (int, float)):
                parsed[model_name] = float(raw_value)
                continue
            if isinstance(raw_value, dict) and isinstance(
                raw_value.get("per_1k_tokens_usd"), (int, float)
            ):
                parsed[model_name] = float(raw_value["per_1k_tokens_usd"])
        return parsed

    @property
    def rca_budget_caps_usd(self) -> Dict[str, float]:
        try:
            data = json.loads(self.rca_budget_caps_usd_raw or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        parsed: Dict[str, float] = {}
        for window, raw_value in data.items():
            if isinstance(raw_value, (int, float)):
                parsed[window] = float(raw_value)
        return parsed

    class Config:
        env_prefix = "MI_"
        extra = "allow"
