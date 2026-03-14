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

    @property
    def pg_dsn(self) -> str:
        return f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password} host={self.pg_host} port=5432"

    class Config:
        env_prefix = "MI_"
        extra = "allow"
