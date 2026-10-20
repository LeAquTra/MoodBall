"""SQLite 连接级 PRAGMA：WAL + 忙等 + 外键。"""

from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created)
def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    cursor = connection.cursor()
    for pragma in (
        "PRAGMA journal_mode=WAL;",
        "PRAGMA synchronous=NORMAL;",
        "PRAGMA foreign_keys=ON;",
        "PRAGMA busy_timeout=5000;",
        "PRAGMA cache_size=-20000;",
    ):
        try:
            cursor.execute(pragma)
        except Exception:  # pragma: no cover - 只影响性能，不影响主流程
            pass
