import json
import os
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    USER_FILE, MEMORY_FILE, HISTORY_DIR, CHATS_FILE, MESSAGES_FILE,
    KV_REST_API_URL, KV_REST_API_TOKEN,
)


def kv_available():
    return bool(KV_REST_API_URL and KV_REST_API_TOKEN)


def kv_get(key):
    if not kv_available():
        return None
    try:
        url = f"{KV_REST_API_URL}/get/{key}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("result")
    except Exception:
        return None


def kv_set(key, value):
    if not kv_available():
        return False
    try:
        url = f"{KV_REST_API_URL}/set/{key}"
        body = json.dumps(value).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {KV_REST_API_TOKEN}",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True
    except Exception:
        return False


def kv_delete(key):
    if not kv_available():
        return False
    try:
        url = f"{KV_REST_API_URL}/del/{key}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"})
        req.method = "POST"
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True
    except Exception:
        return False


def kv_exists(key):
    if not kv_available():
        return False
    try:
        url = f"{KV_REST_API_URL}/exists/{key}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("result", 0) > 0
    except Exception:
        return False


def load_users():
    if kv_available():
        data = kv_get("ans_users")
        if data is not None:
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass
            if isinstance(data, dict):
                return data
    if USER_FILE.exists():
        try:
            return json.loads(USER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"users": {}}


def save_users(users):
    if kv_available():
        kv_set("ans_users", json.dumps(users))
    try:
        USER_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_memory():
    if kv_available():
        data = kv_get("ans_memory")
        if data is not None:
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass
            if isinstance(data, dict):
                data.setdefault("learned", {})
                return data
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("learned", {})
                return data
        except Exception:
            pass
    return {"learned": {}}


def save_memory(memory):
    if kv_available():
        kv_set("ans_memory", json.dumps(memory))
    try:
        MEMORY_FILE.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_messages():
    if MESSAGES_FILE.exists():
        try:
            return json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"messages": []}


def save_messages(msgs):
    try:
        MESSAGES_FILE.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_chats():
    if CHATS_FILE.exists():
        try:
            return json.loads(CHATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_chats(chats):
    try:
        CHATS_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_user_chats(user_id):
    chats = load_chats()
    return chats.get(user_id, [])


def save_user_chats(user_id, user_chats):
    chats = load_chats()
    chats[user_id] = user_chats
    save_chats(chats)


def load_user_history(user_id, modelo):
    if kv_available():
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
        key = f"ans_hist_{safe_id}_{modelo}"
        data = kv_get(key)
        if data is not None:
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except Exception:
                    pass
            if isinstance(data, list):
                return data
    HISTORY_DIR.mkdir(exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
    path = HISTORY_DIR / f"{safe_id}_{modelo}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_user_history(user_id, modelo, history):
    if kv_available():
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
        key = f"ans_hist_{safe_id}_{modelo}"
        kv_set(key, json.dumps(history[-200:]))
    try:
        HISTORY_DIR.mkdir(exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
        path = HISTORY_DIR / f"{safe_id}_{modelo}.json"
        path.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_chat_history(user_id, chat_id):
    path = HISTORY_DIR / f"{user_id}_{chat_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_chat_history(user_id, chat_id, history):
    HISTORY_DIR.mkdir(exist_ok=True)
    path = HISTORY_DIR / f"{user_id}_{chat_id}.json"
    try:
        path.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def auto_delete_old_chats():
    chats = load_chats()
    changed = False
    cutoff = datetime.now() - timedelta(days=10)
    for user_id in list(chats.keys()):
        user_chats = chats[user_id]
        kept = []
        for ch in user_chats:
            try:
                created = datetime.fromisoformat(ch.get("created_at", ""))
                if created < cutoff:
                    history_path = HISTORY_DIR / f"{user_id}_{ch['id']}.json"
                    if history_path.exists():
                        try:
                            history_path.unlink()
                        except Exception:
                            pass
                    changed = True
                    continue
            except Exception:
                pass
            kept.append(ch)
        if len(kept) != len(user_chats):
            chats[user_id] = kept
            changed = True
    if changed:
        save_chats(chats)
