"""应用配置：从环境变量 / .env 读取，禁止硬编码密钥。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 应用 ---
    app_name: str = "zg-tsp-server"
    env: str = "dev"
    debug: bool = False

    # --- 数据库 ---
    database_url: str = f"sqlite:///{BASE_DIR / 'app' / 'data' / 'zg_tsp.db'}"

    # --- JWT ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # --- 种子 ---
    admin_init_password: str | None = None

    # --- CORS ---
    cors_origins: str = "http://localhost:5173"

    # --- 上传 ---
    upload_dir: str = str(BASE_DIR / "app" / "uploads")
    max_upload_mb: int = 10
    allowed_extensions: str = "jpg,jpeg,png,pdf"

    # --- 限流 ---
    register_rate_limit: int = 10
    action_rate_limit: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()]


settings = Settings()