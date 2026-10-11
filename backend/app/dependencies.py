from redis import Redis
from sqlalchemy import text

from app.config import Settings
from app.database import make_engine


class DependencyProbe:
    def __init__(self, settings: Settings):
        self.engine = make_engine(settings)
        self.redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=settings.readiness_timeout_seconds,
            socket_timeout=settings.readiness_timeout_seconds,
        )

    def postgres(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def cache(self) -> None:
        self.redis.ping()

    def close(self) -> None:
        self.engine.dispose()
        self.redis.close()
