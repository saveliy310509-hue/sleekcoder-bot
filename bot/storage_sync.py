import os
import json
import base64
import asyncio
import logging
import urllib.request
import aiosqlite
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("storage_sync")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "saveliy310509-hue/sleekcoder-bot").strip()
BACKUP_PATH = "data/links_backup.json"

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_BACKUP_DIR = BASE_DIR / "data"
LOCAL_BACKUP_FILE = LOCAL_BACKUP_DIR / "links_backup.json"

def ensure_backup_dir():
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def fetch_github_backup() -> Optional[Dict[str, Any]]:
    """Получение резервной копии ссылок из GitHub API"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{BACKUP_PATH}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "User-Agent": "SleekCoderBot-Sync",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_b64 = data.get("content", "")
            if content_b64:
                content_str = base64.b64decode(content_b64).decode("utf-8")
                parsed = json.loads(content_str)
                logger.info(f"Успешно получена резервная копия из GitHub (ссылок: {len(parsed.get('links', []))})")
                return parsed
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.info("Файл резервной копии на GitHub еще не создан.")
        else:
            logger.warning(f"Ошибка загрузки резервной копии из GitHub (HTTP {e.code}): {e}")
    except Exception as e:
        logger.warning(f"Ошибка обращения к GitHub API: {e}")
    return None

def push_github_backup(data_dict: Dict[str, Any]):
    """Асинхронная отправка резервной копии на GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{BACKUP_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "User-Agent": "SleekCoderBot-Sync",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # 1. Получаем текущий SHA файла, если он существует
        sha = None
        try:
            req_get = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req_get, timeout=10) as resp:
                cur = json.loads(resp.read().decode("utf-8"))
                sha = cur.get("sha")
        except Exception:
            pass

        # 2. Формируем новое содержимое
        content_str = json.dumps(data_dict, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

        links_count = len(data_dict.get("links", []))
        payload = {
            "message": f"Auto-backup: {links_count} links persisted",
            "content": content_b64
        }
        if sha:
            payload["sha"] = sha

        req_put = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT"
        )
        with urllib.request.urlopen(req_put, timeout=15) as resp:
            logger.info(f"✅ Резервная копия ({links_count} ссылок) успешно сохранена на GitHub!")
    except Exception as e:
        logger.error(f"Не удалось отправить резервную копию на GitHub: {e}")

async def export_db_to_dict(db_path: Path) -> Dict[str, Any]:
    """Экспорт всех ссылок и текстов из SQLite в словарь"""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        links = []
        async with db.execute("SELECT * FROM links ORDER BY id ASC") as cur:
            for row in await cur.fetchall():
                links.append(dict(row))

        texts = []
        async with db.execute("SELECT * FROM bot_texts ORDER BY key ASC") as cur:
            for row in await cur.fetchall():
                texts.append(dict(row))

        return {
            "version": 1,
            "links": links,
            "texts": texts
        }

async def import_dict_to_db(db_path: Path, data: Dict[str, Any]) -> int:
    """Импорт ссылок и текстов из словаря в SQLite (без перезаписи более свежих кликов)"""
    imported_links = 0
    async with aiosqlite.connect(db_path) as db:
        for link in data.get("links", []):
            code = link.get("code")
            name = link.get("name")
            file_id = link.get("file_id")
            file_unique_id = link.get("file_unique_id")
            file_type = link.get("file_type", "document")
            caption = link.get("caption")
            clicks = link.get("clicks", 0)
            created_at = link.get("created_at")

            if not code or not file_id:
                continue

            await db.execute("""
                INSERT INTO links (code, name, file_id, file_unique_id, file_type, caption, clicks, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    file_id = excluded.file_id,
                    file_unique_id = excluded.file_unique_id,
                    file_type = excluded.file_type,
                    caption = excluded.caption,
                    clicks = MAX(links.clicks, excluded.clicks)
            """, (code, name, file_id, file_unique_id, file_type, caption, clicks, created_at))
            imported_links += 1

        for txt in data.get("texts", []):
            key = txt.get("key")
            title = txt.get("title", key)
            val = txt.get("value")
            if key and val:
                await db.execute("""
                    INSERT INTO bot_texts (key, title, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value
                """, (key, title, val))

        await db.commit()
    return imported_links

async def sync_on_startup(db_path: Path):
    """Синхронизация при старте бота: восстанавливает ссылки из GitHub / локального бэкапа"""
    ensure_backup_dir()

    # 1. Сначала пробуем получить свежий бэкап из GitHub
    cloud_data = None
    try:
        cloud_data = await asyncio.to_thread(fetch_github_backup)
    except Exception as e:
        logger.warning(f"Ошибка получения бэкапа из облака: {e}")

    # 2. Если удалось получить из GitHub, обновляем локальный файл
    if cloud_data and cloud_data.get("links"):
        try:
            with open(LOCAL_BACKUP_FILE, "w", encoding="utf-8") as f:
                json.dump(cloud_data, f, ensure_ascii=False, indent=2)
            logger.info("Локальный файл резервной копии обновлен данными из облака.")
        except Exception as e:
            logger.warning(f"Не удалось записать локальный файл бэкапа: {e}")

    # 3. Читаем локальный файл бэкапа, если облако недоступно
    backup_data = cloud_data
    if not backup_data and LOCAL_BACKUP_FILE.exists():
        try:
            with open(LOCAL_BACKUP_FILE, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
            logger.info(f"Загружен локальный бэкап (ссылок: {len(backup_data.get('links', []))})")
        except Exception as e:
            logger.warning(f"Ошибка чтения локального бэкапа: {e}")

    # 4. Восстанавливаем в базу данных
    if backup_data and backup_data.get("links"):
        count = await import_dict_to_db(db_path, backup_data)
        logger.info(f"✅ База данных успешно синхронизирована! Восстановлено/проверено ссылок: {count}")

    # 5. Всегда актуализируем резервную копию текущим состоянием базы
    current_data = await export_db_to_dict(db_path)
    if current_data.get("links"):
        await save_backup_now(db_path)

async def save_backup_now(db_path: Path):
    """Прямое сохранение бэкапа в локальный JSON и на GitHub"""
    ensure_backup_dir()
    try:
        data = await export_db_to_dict(db_path)
        with open(LOCAL_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(push_github_backup, data)
    except Exception as e:
        logger.error(f"Ошибка сохранения бэкапа: {e}")

def trigger_backup_save(db_path: Path):
    """Фоновый неблокирующий запуск сохранения бэкапа"""
    ensure_backup_dir()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(save_backup_now(db_path))
    except RuntimeError:
        asyncio.run(save_backup_now(db_path))
