from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    kafka_bootstrap: str = Field(default="kafka:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    pg_db: str = Field(default="maintenance", alias="POSTGRES_DB")
    pg_user: str = Field(default="postgres", alias="POSTGRES_USER")
    pg_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    pg_host: str = Field(default="timescaledb", alias="POSTGRES_HOST")
    genai_model: str = Field(default="gpt-4.1")
    genai_timeout_s: int = Field(default=25)
    run_summary_dir: str = Field(default="outputs")
    pm_connector_backend: str = Field(default="mock")
    dev_allow_headers: bool = Field(default=False)
    maximo_base_url: str | None = Field(default=None)
    maximo_site: str = Field(default="BEDFORD")
    maximo_api_key: str | None = Field(default=None)
    maximo_timeout_s: int = Field(default=15)
    rag_vector_alpha: float = Field(default=0.6)

    @property
    def pg_dsn(self) -> str:
        return f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password} host={self.pg_host} port=5432"

    class Config:
        env_prefix = "MI_"
        extra = "allow"
