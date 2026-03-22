from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    kafka_bootstrap: str = Field(default="kafka:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    pg_db: str = Field(default="maintenance", alias="POSTGRES_DB")
    pg_user: str = Field(default="postgres", alias="POSTGRES_USER")
    pg_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    pg_host: str = Field(default="timescaledb", alias="POSTGRES_HOST")
    pg_port: int = Field(default=5432, alias="POSTGRES_PORT")
    genai_model: str = Field(default="gpt-4.1")
    genai_timeout_s: int = Field(default=25)
    run_summary_dir: str = Field(default="outputs")
    pm_connector_backend: str = Field(default="mock")
    dev_allow_headers: bool = Field(default=False)
    auth_trust_forwarded_headers: bool = Field(default=False)
    auth_subject_header: str = Field(default="x-auth-request-user")
    auth_role_header: str = Field(default="x-auth-request-role")
    auth_org_header: str = Field(default="x-auth-request-org")
    auth_site_header: str = Field(default="x-auth-request-site")
    auth_sites_header: str = Field(default="x-auth-request-sites")
    pm_handoff_retry_attempts: int = Field(default=3)
    pm_handoff_retry_interval_s: float = Field(default=1.0)
    pm_handoff_max_attempts_per_proposal: int = Field(default=3)
    maximo_base_url: str | None = Field(default=None)
    maximo_site: str = Field(default="BEDFORD")
    maximo_api_key: str | None = Field(default=None)
    maximo_timeout_s: int = Field(default=15)
    sap_base_url: str | None = Field(default=None)
    sap_client: str | None = Field(default=None)
    sap_api_key: str | None = Field(default=None)
    sap_plant: str | None = Field(default=None)
    sap_timeout_s: int = Field(default=15)
    ingestion_tenant_id: str = Field(default="demo-og")
    ingestion_page_size: int = Field(default=100)
    rag_vector_alpha: float = Field(default=0.6)
    rca_fleet_wide_context: bool = Field(default=True)
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    edge_mode_enabled: bool = Field(default=False)
    edge_buffer_path: str = Field(default="outputs/edge/edge_buffer.sqlite3")
    edge_command_buffer_path: str = Field(default="outputs/edge/edge_command_buffer.sqlite3")
    edge_replay_batch_size: int = Field(default=100)
    edge_connectivity_check_interval_s: float = Field(default=5.0)
    edge_connectivity_timeout_s: int = Field(default=2)
    edge_buffer_max_events: int = Field(default=5000)

    @property
    def pg_dsn(self) -> str:
        return (
            f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password} "
            f"host={self.pg_host} port={self.pg_port}"
        )

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

    model_config = SettingsConfigDict(env_prefix="MI_", extra="allow")
