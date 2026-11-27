from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_FILE = PROJECT_ROOT / "profiles.jsonl"
DATA_DIR = PROJECT_ROOT / "data"
CHAT_DIR = DATA_DIR / "chats"
MEMORY_DIR = DATA_DIR / "memory"
