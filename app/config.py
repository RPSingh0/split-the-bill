from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fastapi_api_key: str
    database_url: str
    jwt_secret: str
    openai_model: str = "gpt-5.4-mini"
    gemini_model: str = "gemini-3.5-flash"


settings = Settings()
