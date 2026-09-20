import os
import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_DIR = Path(__file__).resolve().parent
WATCH_EXTENSIONS = {".py", ".env"}
IGNORE_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}

class BotReloader(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.process = None
        self.last_restart = 0
        self.debounce_seconds = 1.0  # Защита от частых перезапусков при множественном сохранении
        self.start_bot()

    def start_bot(self):
        """Запуск процесса бота"""
        if self.process and self.process.poll() is None:
            self.stop_bot()

        print("\n" + "=" * 50)
        print("🚀 [AutoReload] Запуск Telegram-бота...")
        print("=" * 50 + "\n")
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        self.process = subprocess.Popen(
            [sys.executable, str(PROJECT_DIR / "main.py")],
            cwd=str(PROJECT_DIR),
            env=env
        )

    def stop_bot(self):
        """Остановка текущего процесса бота"""
        if self.process and self.process.poll() is None:
            print("🛑 [AutoReload] Остановка предыдущего процесса бота...")
            try:
                # На Windows завершаем процесс и его дочерние элементы
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], 
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    self.process.kill()

    def on_any_event(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        
        # Игнорируем временные файлы и базы данных
        if any(ignored in file_path.parts for ignored in IGNORE_DIRS):
            return
        if file_path.name.endswith((".db", ".db-journal", ".tmp")):
            return

        # Проверяем расширения (.py, .env)
        if file_path.suffix in WATCH_EXTENSIONS or file_path.name == ".env":
            now = time.time()
            if now - self.last_restart >= self.debounce_seconds:
                self.last_restart = now
                print(f"\n🔄 [AutoReload] Обнаружено изменение в: {file_path.name}")
                print("🔄 [AutoReload] Перезапуск бота...\n")
                self.start_bot()

def main():
    reloader = BotReloader()
    observer = Observer()
    observer.schedule(reloader, path=str(PROJECT_DIR), recursive=True)
    observer.start()

    print(f"👀 [AutoReload] Отслеживание изменений в: {PROJECT_DIR}")
    print("💡 При любом изменении .py или .env файлов бот будет автоматически перезапущен.\n")

    try:
        while True:
            time.sleep(1)
            # Если бот упал сам, но мы не перезапускали
            if reloader.process and reloader.process.poll() is not None:
                # Процесс завершился
                pass
    except KeyboardInterrupt:
        print("\n👋 Остановка наблюдателя и бота...")
        observer.stop()
        reloader.stop_bot()
    observer.join()

if __name__ == "__main__":
    main()
