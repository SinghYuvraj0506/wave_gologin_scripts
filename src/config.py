from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GL_API_TOKEN: str
    TASK_ID: str
    SOAX_USER_NAME:str
    SOAX_PASSWORD:str
    SOAX_HOST:str
    SOAX_PORT:str
    EVOMI_USER_NAME:str
    EVOMI_PASSWORD:str
    EVOMI_HOST:str
    EVOMI_PORT:str
    PROXY_PROVIDER:str
    WEBHOOK_SECRET: str
    WEBHOOK_URL: str
    HEARTBEAT_INTERVAL: int

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid"
    )

Config = Settings()
