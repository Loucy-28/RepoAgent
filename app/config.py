from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="repo_agent", alias="POSTGRES_USER")
    postgres_password: str = Field(default="repo_agent_pass", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="repo_agent", alias="POSTGRES_DB")

    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")

    sandbox_image: str = Field(default="repo-agent-sandbox", alias="SANDBOX_IMAGE")
    sandbox_memory_limit: str = Field(default="256m", alias="SANDBOX_MEMORY_LIMIT")
    sandbox_cpu_limit: float = Field(default=0.5, alias="SANDBOX_CPU_LIMIT")
    sandbox_timeout: int = Field(default=30, alias="SANDBOX_TIMEOUT")
    sandbox_network: str = Field(default="none", alias="SANDBOX_NETWORK")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_agent_iterations: int = Field(default=5, alias="MAX_AGENT_ITERATIONS")

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
