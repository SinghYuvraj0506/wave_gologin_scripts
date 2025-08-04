from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GL_API_TOKEN: str
    TASK_ID: str
    BRIGHTDATA_USER_NAME: str
    BRIGHTDATA_PASSWORD: str
    BRIGHTDATA_ZONE: str
    WEBHOOK_SECRET: str
    WEBHOOK_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid"
    )

Config = Settings()
