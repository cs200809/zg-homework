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
    # MySQL（字符集 utf8mb4 以正确存储中文与 emoji）
    database_url: str = (
        "mysql+pymysql://root:12345678@127.0.0.1:3306/zg_tsp"
        "?charset=utf8mb4"
    )
    db_echo: bool = False

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
    # 文章上传（迭代 v2.1：支持 PDF / word）
    article_allowed_extensions: str = "pdf,docx"
    article_max_upload_mb: int = 10

    # --- 限流 ---
    register_rate_limit: int = 10
    action_rate_limit: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()]

    @property
    def article_allowed_extension_list(self) -> list[str]:
        """文章允许上传的扩展名（迭代 v2.1）。"""
        return [
            e.strip().lower()
            for e in self.article_allowed_extensions.split(",")
            if e.strip()
        ]


settings = Settings()