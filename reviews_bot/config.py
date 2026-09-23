import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    admin_ids: List[int]
    reviews_channel_id: Optional[str]
    db_path: str = "database/reviews.db"
    # Режим работы бота: "polling" или "webhook"
    bot_mode: str = "polling"
    # Настройки Webhook
    webhook_url: Optional[str] = None
    webhook_path: str = "/webhook"
    webhook_secret_token: Optional[str] = None
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8080
    # Настройки Sentry / GlitchTip
    sentry_dsn: Optional[str] = None
    # Настройки защиты от спама (Rate Limiting)
    rate_limit_seconds: float = 0.7


def load_config() -> Config:
    bot_token = (
        os.getenv("REVIEWS_BOT_TOKEN", "").strip()
        or os.getenv("BOT_TOKEN_REVIEWS", "").strip()
        or "8842485074:AAH9qEJ7bpXF-EbtawCHOR3SLhxpgDCVQcw"
    )

    raw_admin_ids = os.getenv("ADMIN_IDS", "8554520733").strip()
    admin_ids: List[int] = []
    if raw_admin_ids:
        for part in raw_admin_ids.split(","):
            part = part.strip()
            if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
                admin_ids.append(int(part))
    if not admin_ids:
        admin_ids = [8554520733]

    reviews_channel = os.getenv("REVIEWS_CHANNEL_ID", "").strip() or None
    default_db = os.path.join(os.path.dirname(__file__), "database", "reviews.db")
    db_path = os.getenv("REVIEWS_DB_PATH", default_db).strip()

    # Режим работы: polling / webhook
    bot_mode = os.getenv("BOT_MODE", "polling").strip().lower()
    if bot_mode not in ("polling", "webhook"):
        bot_mode = "polling"

    webhook_url = os.getenv("WEBHOOK_URL", "").strip() or None
    webhook_path = os.getenv("WEBHOOK_PATH", "/webhook").strip()
    if not webhook_path.startswith("/"):
        webhook_path = f"/{webhook_path}"

    webhook_secret_token = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None
    webapp_host = os.getenv("WEBAPP_HOST", "0.0.0.0").strip()

    try:
        webapp_port = int(os.getenv("WEBAPP_PORT", "8080").strip())
    except ValueError:
        webapp_port = 8080

    sentry_dsn = os.getenv("SENTRY_DSN", "").strip() or None

    try:
        rate_limit_seconds = float(os.getenv("RATE_LIMIT_SECONDS", "0.7").strip())
    except ValueError:
        rate_limit_seconds = 0.7

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        reviews_channel_id=reviews_channel,
        db_path=db_path,
        bot_mode=bot_mode,
        webhook_url=webhook_url,
        webhook_path=webhook_path,
        webhook_secret_token=webhook_secret_token,
        webapp_host=webapp_host,
        webapp_port=webapp_port,
        sentry_dsn=sentry_dsn,
        rate_limit_seconds=rate_limit_seconds,
    )
