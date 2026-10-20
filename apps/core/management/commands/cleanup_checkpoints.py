"""清理 LangGraph 检查点：删除业务库里已经不存在的会话线程。"""

from __future__ import annotations

import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "清理 agent_checkpoints.sqlite3 中孤立或指定会话的检查点线程。"

    def add_arguments(self, parser):
        parser.add_argument("--orphan", action="store_true", help="删除业务库没有对应 Conversation 的 thread")
        parser.add_argument("--thread", type=str, default="", help="删除指定 thread_id")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        db_path = settings.CHECKPOINT_DB
        if not db_path.exists():
            self.stdout.write("检查点库不存在，无需清理。")
            return

        from apps.chat.models import Conversation

        live_threads = {str(item) for item in Conversation.objects.values_list("id", flat=True)}
        con = sqlite3.connect(str(db_path))
        try:
            threads = [row[0] for row in con.execute("SELECT DISTINCT thread_id FROM checkpoints")]
            targets: list[str] = []
            if options["thread"]:
                targets = [options["thread"]] if options["thread"] in threads else []
            elif options["orphan"]:
                targets = [thread for thread in threads if thread not in live_threads]
            else:
                self.stdout.write(
                    self.style.WARNING("需要 --orphan 或 --thread；当前只列出线程：\n" + "\n".join(threads))
                )
                return

            if options["dry_run"]:
                self.stdout.write("dry-run 目标：" + (", ".join(targets) or "无"))
                return

            for thread in targets:
                con.execute("DELETE FROM writes WHERE thread_id = ?", (thread,))
                con.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread,))
            con.commit()
            self.stdout.write(self.style.SUCCESS(f"已删除 {len(targets)} 个检查点线程"))
        finally:
            con.close()
