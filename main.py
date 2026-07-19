from flask import render_template, request, jsonify, redirect, url_for, session
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from config import (
    app, BASE_DIR, _data_dir, HISTORY_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI, OWNER_EMAIL, IS_PROD,
)
from ans.data.storage import (
    load_users, save_users, load_memory, save_memory,
    load_messages, save_messages, load_chats, save_chats,
    get_user_chats, save_user_chats, load_user_history, save_user_history,
    get_chat_history, save_chat_history, auto_delete_old_chats,
)
from ans.auth.google import login_required, owner_required, is_owner, exchange_code_for_token, get_google_user_info
from ans.ai.core import (
    reasoning_search, reason_about, search_wikipedia, search_wikipedia_search,
    search_duckduckgo, search_fact, search_all_sources, extract_known_answer,
    learn_fact, extract_search_term, web_search_and_respond, format_reasoned_answer,
    _get_last_user_topic, _last_ai_asked_sources, _apply_detail, detect_intent,
    respond_with_flask_model, respond_with_gapi_model, respond_with_modify_model,
    get_image_for_topic, format_wiki_result,
)
from ans.ai.knowledge import MODEL_INFO, KNOWLEDGE_BASE, CONCEPT_DB, FACTS_DB
from ans.tools.draw import generate_svg
from ans.tools.calculator import safe_calc
from ans.utils.helpers import normalize_text


@app.route("/api/sources", methods=["POST"])
def api_sources():
    try:
        data = request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"sources": []})
        sources = search_all_sources(query)
        return jsonify({"sources": sources})
    except Exception:
        return jsonify({"sources": []})


@app.route("/api/draw", methods=["POST"])
def api_draw():
    try:
        data = request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"svg": "", "error": "Dime que dibujar"})
        svg = generate_svg(query)
        return jsonify({"svg": svg, "query": query})
    except Exception:
        return jsonify({"svg": "", "error": "Error al dibujar"})


@app.route("/api/users", methods=["GET"])
@login_required
def api_users_list():
    users = load_users()
    user_list = list(users.get("users", {}).values())
    return jsonify({"users": user_list})


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    try:
        data = request.get_json(silent=True) or {}
        expr = data.get("expr", "").strip()
        if not expr:
            return jsonify({"result": None, "error": "Expresion vacia"})
        allowed = re.compile(r'^[\d\s\+\-\*/\(\)\.\%\*\*]+$')
        if not allowed.match(expr):
            return jsonify({"result": None, "error": "Expresion invalida"})
        result = eval(expr, {"__builtins__": {}}, {})
        return jsonify({"result": result, "expr": expr})
    except Exception as e:
        return jsonify({"result": None, "error": str(e)})


@app.route("/api/contact", methods=["POST"])
def api_contact():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "Anonimo").strip()
        email = data.get("email", "").strip()
        message = data.get("message", "").strip()
        tipo = data.get("type", "sugerencia")
        if not message:
            return jsonify({"ok": False, "error": "Escribe un mensaje"})
        msgs = load_messages()
        msgs.setdefault("messages", []).append({
            "name": name,
            "email": email,
            "message": message,
            "type": tipo,
            "date": datetime.now().isoformat(),
        })
        save_messages(msgs)
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False, "error": "Error al enviar"})


@app.route("/contacto")
def contacto():
    return render_template("contacto.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    try:
        data = request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"error": "Query vacia"}), 400
        wiki_result = search_wikipedia(query)
        search_results = search_wikipedia_search(query)
        response = {
            "query": query,
            "summary": format_wiki_result(wiki_result),
            "results": search_results[:3],
            "found": wiki_result is not None and bool(wiki_result.get("extract")),
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e), "found": False}), 500


@app.route("/calc")
@login_required
def calc():
    return render_template("calc.html")


@app.route("/convert")
@login_required
def convert():
    return render_template("convert.html")


@app.route("/mail")
@login_required
def mail():
    return render_template("mail.html")


_GAME_TEMPLATES = {
    "tictac": "juegos/tictac.html", "snake": "juegos/snake.html",
    "memory": "juegos/memory.html", "ahorcado": "juegos/ahorcado.html",
}

@app.route("/games")
@login_required
def games_panel():
    return render_template("juegos/panel.html")


@app.route("/games/<name>")
@login_required
def games_play(name):
    tpl = _GAME_TEMPLATES.get(name)
    if not tpl:
        return redirect(url_for("games_panel"))
    return render_template(tpl)


_APP_TEMPLATES = {
    "draw": "draw.html", "notes": "notes.html", "weather": "weather.html",
    "scan": "scan.html", "wallet": "wallet.html", "music": "music.html",
    "maps": "maps.html", "backup": "backup.html",
}

@app.route("/app/<name>")
@login_required
def app_router(name):
    tpl = _APP_TEMPLATES.get(name)
    if not tpl:
        return redirect(url_for("herramientas"))
    return render_template(tpl)


@app.route("/herramientas")
@login_required
def herramientas():
    return render_template("Herramientas.html")


@app.route("/admin")
@login_required
@owner_required
def admin():
    users = load_users()
    memory = load_memory()
    learned = memory.get("learned", {})
    user_list = list(users.get("users", {}).values())
    concept_count = len(KNOWLEDGE_BASE)
    memory_count = len(learned)
    blocked = memory.get("blocked", [])
    messages = load_messages().get("messages", [])
    history_files = []
    if HISTORY_DIR.exists():
        for f in sorted(HISTORY_DIR.iterdir(), reverse=True)[:50]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                history_files.append({"name": f.name, "size": len(data), "updated": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
            except Exception:
                history_files.append({"name": f.name, "size": 0, "updated": ""})
    # Token data for all users
    tokens_data = _load_tokens()
    token_list = []
    for uid, tok in tokens_data.items():
        u = users.get("users", {}).get(uid, {})
        token_list.append({
            "id": uid,
            "name": u.get("name", uid),
            "email": u.get("email", ""),
            "picture": u.get("picture", ""),
            "balance": tok.get("balance", 0),
            "total_earned": tok.get("total_earned", 0),
            "total_spent": tok.get("total_spent", 0),
            "missions": tok.get("missions", {}),
            "missions_date": tok.get("missions_date", ""),
        })
    return render_template("admin.html", users=user_list, concepts=concept_count, memory=memory_count, history_files=history_files, memory_items=list(learned.items())[:100], blocked=blocked, messages=messages, facts_count=len(FACTS_DB), tokens=token_list, daily_missions=DAILY_MISSIONS)


@app.route("/admin/delete-memory-item", methods=["POST"])
@login_required
@owner_required
def delete_memory_item():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    if key:
        memory = load_memory()
        memory.get("learned", {}).pop(key, None)
        save_memory(memory)
    return jsonify({"ok": True})


@app.route("/admin/clear-memory", methods=["POST"])
@login_required
@owner_required
def clear_memory():
    save_memory({"learned": {}, "blocked": []})
    return jsonify({"ok": True})


@app.route("/admin/block-user", methods=["POST"])
@login_required
@owner_required
def block_user():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    if email:
        memory = load_memory()
        memory.setdefault("blocked", [])
        if email not in memory["blocked"]:
            memory["blocked"].append(email)
        save_memory(memory)
    return jsonify({"ok": True})


@app.route("/admin/unblock-user", methods=["POST"])
@login_required
@owner_required
def unblock_user():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    if email:
        memory = load_memory()
        memory.setdefault("blocked", [])
        memory["blocked"] = [e for e in memory["blocked"] if e != email]
        save_memory(memory)
    return jsonify({"ok": True})


@app.route("/admin/model-history/<modelo>")
@login_required
@owner_required
def admin_model_history(modelo):
    users = load_users()
    histories = []
    if HISTORY_DIR.exists():
        for f in HISTORY_DIR.iterdir():
            if modelo in f.name:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    user_id = f.name.replace(f"_{modelo}.json", "").replace("_", " ")
                    histories.append({"user": user_id, "messages": len(data), "file": f.name, "content": data[-20:]})
                except Exception:
                    pass
    return jsonify(histories)


@app.route("/admin/delete-history", methods=["POST"])
@login_required
@owner_required
def delete_history():
    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "")
    if filename and HISTORY_DIR.exists():
        path = HISTORY_DIR / filename
        if path.exists():
            path.unlink()
    return jsonify({"ok": True})


@app.route("/admin/clear-all-history", methods=["POST"])
@login_required
@owner_required
def clear_all_history():
    if HISTORY_DIR.exists():
        for f in HISTORY_DIR.iterdir():
            f.unlink()
    return jsonify({"ok": True})


@app.route("/api/admin/users", methods=["GET"])
@login_required
@owner_required
def admin_users():
    users = load_users()
    return jsonify(users)


@app.route("/api/admin/memory", methods=["GET"])
@login_required
@owner_required
def admin_memory():
    memory = load_memory()
    return jsonify(memory)


@app.route("/api/admin/stats", methods=["GET"])
@login_required
@owner_required
def admin_stats():
    memory = load_memory()
    users = load_users()
    user_count = len(users.get("users", {}))
    learned_count = len(memory.get("learned", {}))
    history_count = 0
    if HISTORY_DIR.exists():
        history_count = sum(1 for _ in HISTORY_DIR.iterdir())
    return jsonify({
        "users": user_count,
        "learned": learned_count,
        "concepts": len(KNOWLEDGE_BASE),
        "history_files": history_count,
    })


@app.route("/api/chats", methods=["GET"])
@login_required
def api_list_chats():
    user = session.get("user", {})
    user_id = user.get("id", "anonymous")
    auto_delete_old_chats()
    user_chats = get_user_chats(user_id)
    return jsonify({"chats": user_chats})


@app.route("/api/chats", methods=["POST"])
@login_required
def api_create_chat():
    user = session.get("user", {})
    user_id = user.get("id", "anonymous")
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip() or "Nuevo chat"
    modelo = data.get("modelo", "flask")
    chat_id = str(uuid.uuid4())[:8]
    chat_entry = {
        "id": chat_id,
        "name": name,
        "model": modelo,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    user_chats = get_user_chats(user_id)
    user_chats.insert(0, chat_entry)
    save_user_chats(user_id, user_chats)
    return jsonify({"chat": chat_entry})


@app.route("/api/chats/<chat_id>", methods=["PUT"])
@login_required
def api_rename_chat(chat_id):
    user = session.get("user", {})
    user_id = user.get("id", "anonymous")
    data = request.get_json(silent=True) or {}
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Nombre requerido"}), 400
    user_chats = get_user_chats(user_id)
    for ch in user_chats:
        if ch["id"] == chat_id:
            ch["name"] = new_name
            ch["updated_at"] = datetime.now().isoformat()
            save_user_chats(user_id, user_chats)
            return jsonify({"ok": True})
    return jsonify({"error": "Chat no encontrado"}), 404


@app.route("/api/chats/<chat_id>", methods=["DELETE"])
@login_required
def api_delete_chat(chat_id):
    user = session.get("user", {})
    user_id = user.get("id", "anonymous")
    user_chats = get_user_chats(user_id)
    user_chats = [ch for ch in user_chats if ch["id"] != chat_id]
    save_user_chats(user_id, user_chats)
    history_path = HISTORY_DIR / f"{user_id}_{chat_id}.json"
    if history_path.exists():
        try:
            history_path.unlink()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/history", methods=["GET"])
@login_required
def get_history():
    user = session.get("user", {})
    modelo = request.args.get("modelo", "flask")
    chat_id = request.args.get("chat_id", "")
    user_id = user.get("id", "anonymous")
    if chat_id:
        history = get_chat_history(user_id, chat_id)
    else:
        history = load_user_history(user_id, modelo)
    return jsonify({"history": history})


@app.route("/api/history", methods=["POST"])
@login_required
def save_history():
    user = session.get("user", {})
    data = request.get_json(silent=True) or {}
    modelo = data.get("modelo", "flask")
    chat_id = data.get("chat_id", "")
    historial = data.get("historial", [])
    user_id = user.get("id", "anonymous")
    if chat_id:
        save_chat_history(user_id, chat_id, historial)
        user_chats = get_user_chats(user_id)
        for ch in user_chats:
            if ch["id"] == chat_id:
                ch["updated_at"] = datetime.now().isoformat()
                save_user_chats(user_id, user_chats)
                break
    else:
        save_user_history(user_id, modelo, historial)
    return jsonify({"ok": True})


@app.route("/api/history/clear", methods=["POST"])
@login_required
def clear_history():
    user = session.get("user", {})
    data = request.get_json(silent=True) or {}
    modelo = data.get("modelo", "flask")
    chat_id = data.get("chat_id", "")
    user_id = user.get("id", "anonymous")
    if chat_id:
        save_chat_history(user_id, chat_id, [])
    else:
        save_user_history(user_id, modelo, [])
    return jsonify({"ok": True})


@app.route("/login")
def login():
    if "user" in session:
        return redirect(url_for("herramientas"))
    google_configured = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    return render_template("login.html", google_configured=google_configured)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


@app.route("/auth/google/login")
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return redirect(url_for("login"))
    if GOOGLE_REDIRECT_URI:
        redirect_uri = GOOGLE_REDIRECT_URI
    else:
        base_url = request.host_url.rstrip("/")
        base_url = base_url.replace("127.0.0.1", "localhost").replace("0.0.0.0", "localhost")
        redirect_uri = f"{base_url}/auth/google/callback"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "display": "popup",
    }
    session["google_redirect_uri"] = redirect_uri
    import urllib.parse
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(url)


@app.route("/auth/google/callback")
def google_callback():
    try:
        code = request.args.get("code")
        if not code:
            return redirect(url_for("login"))
        token_data = exchange_code_for_token(code)
        if not token_data:
            return redirect(url_for("login"))
        user_info = get_google_user_info(token_data.get("access_token"))
        if not user_info:
            return redirect(url_for("login"))
        users = load_users()
        google_id = user_info.get("id")
        email = user_info.get("email", "")
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")
        if google_id not in users.get("users", {}):
            users.setdefault("users", {})[google_id] = {
                "email": email,
                "name": name,
                "picture": picture,
                "created": datetime.now().isoformat(),
            }
            save_users(users)
        session["user"] = {
            "id": google_id,
            "email": email,
            "name": name,
            "picture": picture,
        }
        return redirect(url_for("herramientas"))
    except Exception:
        return redirect(url_for("login"))


@app.route("/")
def home():
    return redirect(url_for("inicio"))


@app.route("/inicio")
def inicio():
    return render_template("index.html")


@app.route("/acerca--de--nosotros")
def acerca_de_nosotros():
    return render_template("acerca-de-nosotros.html")


@app.route("/asistente")
def asistente():
    return render_template("asistente_ai.html")


@app.route("/AI-worspase")
@login_required
def hm():
    user = session.get("user", {})
    return render_template("hm.html", user=user, is_owner=is_owner())


CHAT_FILES_DIR = _data_dir / "chat_files"

@app.route("/api/chat/upload", methods=["POST"])
@login_required
def chat_upload():
    if "file" not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Archivo vacío"}), 400
    ext = Path(f.filename).suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mp3", ".wav", ".ogg", ".pdf", ".txt", ".zip"}
    if ext not in allowed:
        return jsonify({"error": f"Formato {ext} no soportado"}), 400
    CHAT_FILES_DIR.mkdir(parents=True, exist_ok=True)
    fid = "cf_" + uuid.uuid4().hex[:12] + ext
    fpath = CHAT_FILES_DIR / fid
    f.save(str(fpath))
    fsize = fpath.stat().st_size
    ftype = "image" if ext in {".jpg",".jpeg",".png",".gif",".webp"} else "video" if ext in {".mp4",".mov",".webm"} else "audio" if ext in {".mp3",".wav",".ogg"} else "file"
    return jsonify({"ok": True, "file_id": fid, "name": f.filename, "type": ftype, "size": fsize, "ext": ext})


@app.route("/api/chat/file/<file_id>")
@login_required
def chat_serve_file(file_id):
    from flask import send_file
    safe = Path(file_id).name
    fpath = CHAT_FILES_DIR / safe
    if not fpath.exists():
        return "Archivo no encontrado", 404
    mime_map = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".gif":"image/gif",".webp":"image/webp",
                ".mp4":"video/mp4",".mov":"video/quicktime",".webm":"video/webm",
                ".mp3":"audio/mpeg",".wav":"audio/wav",".ogg":"audio/ogg",
                ".pdf":"application/pdf",".txt":"text/plain",".zip":"application/zip"}
    mime = mime_map.get(fpath.suffix.lower(), "application/octet-stream")
    return send_file(str(fpath), mimetype=mime)


@app.route("/api/translate", methods=["POST"])
def api_translate():
    from ans.ai.translate import translate_text
    try:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "").strip()
        to_lang = data.get("to", "es")
        if not text:
            return jsonify({"error": "Texto requerido"}), 400
        if len(text) > 2000:
            return jsonify({"error": "Texto demasiado largo (max 2000 caracteres)"}), 400
        result = translate_text(text, to_lang)
        if result:
            return jsonify({"original": text, "translated": result, "to": to_lang})
        return jsonify({"error": "No se pudo traducir"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def ai_chat():
    try:
        data = request.get_json(silent=True) or {}
        historial = data.get("historial", [])
        mensaje_nuevo = data.get("mensaje", "")
        skip_token = data.get("skip_token", False)
        modelo = normalize_text(data.get("modelo", "flask"))
        chat_id = data.get("chat_id", "")
        auto_sources = data.get("auto_sources", False)
        auto_images = data.get("auto_images", True)
        deep_search = data.get("deep_search", False)
        detallado = data.get("detallado", True)
        archivo = data.get("archivo", None)
        memory = load_memory()
        user = session.get("user", {})
        user_email = user.get("email", "")
        blocked = memory.get("blocked", [])
        if user_email in blocked:
            return jsonify({"respuesta": "Tu cuenta ha sido bloqueada por el administrador.", "modelo": "Bloqueado"}), 403

        # Check token balance
        if not skip_token and "user" in session:
            uid = session["user"].get("id", "anon")
            cost = TOKEN_COST.get(modelo, 1)
            tok = _get_user_tokens(uid)
            tok = _ensure_missions(tok)
            if tok["balance"] < cost:
                return jsonify({"respuesta": f"🪙 Saldo insuficiente. Tienes {tok['balance']} tokens y necesitas {cost} para usar {modelo}. Completa misiones en el panel para ganar más.", "modelo": modelo, "source": "token_error"})

        # Handle "regalar" command: regalar @email cantidad
        texto_lower = mensaje_nuevo.lower().strip()
        if texto_lower.startswith("regalar ") and "user" in session:
            partes = mensaje_nuevo.split(None, 2)
            if len(partes) >= 3:
                target_str = partes[1].lstrip("@")
                try:
                    gift_amount = int(partes[2])
                except ValueError:
                    gift_amount = 0
                if gift_amount > 0:
                    uid_origen = session["user"].get("id", "anon")
                    users_data = load_users()
                    target_uid = None
                    target_name = target_str
                    for uid2, u in users_data.get("users", {}).items():
                        if u.get("email", "").lower() == target_str.lower() or u.get("name", "").lower() == target_str.lower():
                            target_uid = uid2
                            target_name = u.get("name", target_str)
                            break
                    if target_uid and target_uid != uid_origen:
                        tok_origen = _get_user_tokens(uid_origen)
                        tok_origen = _ensure_missions(tok_origen)
                        if tok_origen["balance"] >= gift_amount:
                            tok_origen["balance"] -= gift_amount
                            tok_origen["total_spent"] = tok_origen.get("total_spent", 0) + gift_amount
                            _save_user_tokens(uid_origen, tok_origen)
                            tok_dest = _get_user_tokens(target_uid)
                            tok_dest = _ensure_missions(tok_dest)
                            tok_dest["balance"] += gift_amount
                            tok_dest["total_earned"] = tok_dest.get("total_earned", 0) + gift_amount
                            _save_user_tokens(target_uid, tok_dest)
                            respuesta = f"🎁 Regalaste {gift_amount} 🪙 a {target_name}! Ahora tienes {tok_origen['balance']} 🪙"
                            modelo_nombre = MODEL_INFO[modelo]["name"]
                            source = "local"
                            if not skip_token and "user" in session:
                                uid = session["user"].get("id", "anon")
                                cost = TOKEN_COST.get(modelo, 1)
                                tok = _get_user_tokens(uid)
                                tok = _ensure_missions(tok)
                                if tok["balance"] >= cost:
                                    tok["balance"] -= cost
                                    tok["total_spent"] = tok.get("total_spent", 0) + cost
                                    _save_user_tokens(uid, tok)
                            respuesta = format_reasoned_answer(respuesta, mensaje_nuevo, modelo)
                            return jsonify({"respuesta": respuesta, "modelo": modelo_nombre, "source": source})
                        else:
                            respuesta = f"🪙 No tienes suficientes tokens. Tienes {tok_origen['balance']} y necesitas {gift_amount}."
                            modelo_nombre = MODEL_INFO[modelo]["name"]
                            source = "local"
                            if not skip_token and "user" in session:
                                uid = session["user"].get("id", "anon")
                                cost = TOKEN_COST.get(modelo, 1)
                                tok = _get_user_tokens(uid)
                                tok = _ensure_missions(tok)
                                if tok["balance"] >= cost:
                                    tok["balance"] -= cost
                                    tok["total_spent"] = tok.get("total_spent", 0) + cost
                                    _save_user_tokens(uid, tok)
                            respuesta = format_reasoned_answer(respuesta, mensaje_nuevo, modelo)
                            return jsonify({"respuesta": respuesta, "modelo": modelo_nombre, "source": source})
                    elif target_uid == uid_origen:
                        respuesta = "🤦 No puedes regalarte tokens a ti mismo."
                        return jsonify({"respuesta": respuesta, "modelo": MODEL_INFO[modelo]["name"], "source": "local"})
                    else:
                        respuesta = f"👤 No encontré a '{target_str}'. Asegúrate de usar su email exacto."
                        return jsonify({"respuesta": respuesta, "modelo": MODEL_INFO[modelo]["name"], "source": "local"})

        # Handle file attachment
        if archivo and archivo.get("file_id"):
            tipo = archivo.get("type", "archivo")
            nombre = archivo.get("name", "archivo")
            fid = archivo.get("file_id", "")
            if tipo == "image":
                file_mention = f"[📷 Imagen adjunta: {nombre}]({request.host_url}api/chat/file/{fid})"
            elif tipo == "video":
                file_mention = f"[🎬 Video adjunto: {nombre}]({request.host_url}api/chat/file/{fid})"
            elif tipo == "audio":
                file_mention = f"[🎵 Audio adjunto: {nombre}]({request.host_url}api/chat/file/{fid})"
            else:
                file_mention = f"[📎 Archivo adjunto: {nombre}]({request.host_url}api/chat/file/{fid})"
            if mensaje_nuevo:
                mensaje_nuevo = f"[{tipo.upper()}: {nombre}] {mensaje_nuevo}"
            else:
                mensaje_nuevo = f"Recibí un {tipo}: {nombre}"

        if modelo == "gapi":
            respuesta = respond_with_gapi_model(mensaje_nuevo, historial, memory, user)
            modelo_nombre = MODEL_INFO["gapi"]["name"]
            source = "gapi"
        elif modelo == "modify":
            respuesta = respond_with_modify_model(mensaje_nuevo, historial, memory, user)
            modelo_nombre = MODEL_INFO["modify"]["name"]
            source = "modify"
        else:
            session["auto_sources"] = auto_sources
            session["auto_images"] = auto_images
            session["deep_search"] = deep_search
            session["detallado"] = detallado
            respuesta = respond_with_flask_model(mensaje_nuevo, historial, memory, user)
            respuesta = _apply_detail(respuesta, detallado)
            modelo_nombre = MODEL_INFO["flask"]["name"]
            if "Fuentes web" in respuesta or "fuentes web" in respuesta.lower() or "Fuentes para" in respuesta:
                source = "web"
            elif "¿Quieres que busque fuentes" in respuesta or "¿Quieres que busque en la web" in respuesta:
                source = "ask"
            elif "Wikipedia" in respuesta:
                source = "wikipedia"
            elif "DuckDuckGo" in respuesta:
                source = "duckduckgo"
            elif "Curiosidad" in respuesta or "Datos" in respuesta:
                source = "facts"
            else:
                source = "local"

        # Deduct tokens
        if not skip_token and "user" in session:
            uid = session["user"].get("id", "anon")
            cost = TOKEN_COST.get(modelo, 1)
            tok = _get_user_tokens(uid)
            tok = _ensure_missions(tok)
            if tok["balance"] >= cost:
                tok["balance"] -= cost
                tok["total_spent"] = tok.get("total_spent", 0) + cost
                _save_user_tokens(uid, tok)

        respuesta = format_reasoned_answer(respuesta, mensaje_nuevo, modelo)
        return jsonify({"respuesta": respuesta, "modelo": modelo_nombre, "source": source})

    except Exception as e:
        print(f"Error critico en el nucleo: {e}")
        return jsonify({"respuesta": "Fallo en el nucleo neuronal. Revisa la terminal."}), 500


# ---------------------------------------------------------------------------
# Token system
# ---------------------------------------------------------------------------
TOKEN_FILE = _data_dir / "tokens.json"

DAILY_MISSIONS = [
    {"id": "use_weather", "name": "Revisar el clima", "icon": "🌤", "reward": 20},
    {"id": "use_music", "name": "Escuchar música", "icon": "🎵", "reward": 20},
    {"id": "use_games", "name": "Jugar un juego", "icon": "🎮", "reward": 20},
    {"id": "use_mail", "name": "Enviar mensaje", "icon": "💬", "reward": 20},
    {"id": "use_wallet", "name": "Agregar gasto o ingreso", "icon": "💳", "reward": 20},
    {"id": "use_draw", "name": "Dibujar algo", "icon": "🎨", "reward": 20},
    {"id": "use_calc", "name": "Usar calculadora", "icon": "🧮", "reward": 20},
    {"id": "use_notes", "name": "Escribir una nota", "icon": "📝", "reward": 20},
    {"id": "use_scan", "name": "Escanear algo", "icon": "📷", "reward": 20},
    {"id": "use_maps", "name": "Usar mapas", "icon": "🗺", "reward": 20},
    {"id": "use_convert", "name": "Convertir archivos", "icon": "🔄", "reward": 20},
    {"id": "use_backup", "name": "Respaldar datos", "icon": "💾", "reward": 20},
]

TOKEN_COST = {"flask": 1, "gapi": 3, "modify": 2}


def _load_tokens():
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_tokens_data(data):
    TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_user_tokens(user_id):
    data = _load_tokens()
    uid = _safe_id(user_id)
    return data.get(uid, {"balance": 100, "missions": {}, "total_earned": 0, "total_spent": 0})


def _save_user_tokens(user_id, tok_data):
    data = _load_tokens()
    uid = _safe_id(user_id)
    data[uid] = tok_data
    _save_tokens_data(data)


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _ensure_missions(tok):
    today = _today_str()
    if tok.get("missions_date") != today:
        tok["missions"] = {}
        tok["missions_date"] = today
    return tok


def _complete_mission_if_needed(mid, uid=None):
    if uid is None:
        uid = session.get("user", {}).get("id", "anon")
    mission = next((m for m in DAILY_MISSIONS if m["id"] == mid), None)
    if not mission:
        return
    tok = _get_user_tokens(uid)
    tok = _ensure_missions(tok)
    if mid not in tok.get("missions", {}):
        tok.setdefault("missions", {})[mid] = True
        tok["balance"] += mission["reward"]
        tok["total_earned"] += mission["reward"]
        _save_user_tokens(uid, tok)


# ---------------------------------------------------------------------------
# Mail, Music, Backup helpers
# ---------------------------------------------------------------------------
MAIL_DIR = _data_dir / "mail"
MUSIC_DIR = _data_dir / "music"
MUSIC_FILES_DIR = MUSIC_DIR / "files"
ALLOWED_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}


def _safe_id(raw):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw))


def _mail_path(user_id):
    return MAIL_DIR / f"{_safe_id(user_id)}.json"


def _load_mail(user_id):
    p = _mail_path(user_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"contacts": [], "conversations": {}}


def _save_mail(user_id, data):
    MAIL_DIR.mkdir(parents=True, exist_ok=True)
    _mail_path(user_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_tracks():
    p = MUSIC_DIR / "tracks.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tracks": []}


def _save_tracks(data):
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    (MUSIC_DIR / "tracks.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _export_all():
    export = {
        "users": load_users(),
        "memory": load_memory(),
        "messages": load_messages(),
        "chats": load_chats(),
        "mail": {},
        "music": _load_tracks(),
        "exported_at": datetime.now().isoformat(),
    }
    if MAIL_DIR.exists():
        for f in MAIL_DIR.iterdir():
            if f.suffix == ".json":
                export["mail"][f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return export


# ---------------------------------------------------------------------------
# MAIL API
# ---------------------------------------------------------------------------
@app.route("/api/mail/contacts", methods=["GET"])
@login_required
def mail_list_contacts():
    user = session.get("user", {})
    uid = user.get("id", "anon")
    data = _load_mail(uid)
    return jsonify({"contacts": data.get("contacts", [])})


@app.route("/api/mail/contacts", methods=["POST"])
@login_required
def mail_add_contact():
    user = session.get("user", {})
    uid = user.get("id", "anon")
    body = request.get_json(silent=True) or {}
    email = body.get("email", "").strip()
    name = body.get("name", "").strip() or email.split("@")[0]
    if not email:
        return jsonify({"error": "Email requerido"}), 400
    data = _load_mail(uid)
    if any(c["email"] == email for c in data["contacts"]):
        return jsonify({"error": "Contacto ya existe"}), 409
    users = load_users()
    # If contact is a registered Google user, use their user_id as contact id
    cid = None
    contact = {"email": email, "name": name, "picture": "", "created": datetime.now().isoformat()}
    for gu_id, gu in users.get("users", {}).items():
        if gu.get("email", "").lower() == email.lower():
            cid = gu_id
            contact["id"] = gu_id
            contact["name"] = gu.get("name", name)
            contact["picture"] = gu.get("picture", "")
            break
    if not cid:
        cid = "c_" + uuid.uuid4().hex[:8]
        contact["id"] = cid
    data["contacts"].append(contact)
    data.setdefault("conversations", {})[cid] = []
    _save_mail(uid, data)
    return jsonify({"contact": contact})


@app.route("/api/mail/messages/<contact_id>", methods=["GET"])
@login_required
def mail_get_messages(contact_id):
    user = session.get("user", {})
    uid = user.get("id", "anon")
    data = _load_mail(uid)
    msgs = data.get("conversations", {}).get(contact_id, [])
    # Mark incoming messages as read
    changed = False
    for m in msgs:
        if m.get("unread"):
            m["unread"] = False
            changed = True
    if changed:
        _save_mail(uid, data)
    return jsonify({"messages": msgs})


@app.route("/api/mail/messages/<contact_id>", methods=["POST"])
@login_required
def mail_send_message(contact_id):
    user = session.get("user", {})
    uid = user.get("id", "anon")
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "Texto vacío"}), 400
    data = _load_mail(uid)
    data.setdefault("conversations", {}).setdefault(contact_id, [])
    now = datetime.now()
    msg = {
        "from": "me",
        "text": text,
        "time": now.strftime("%H:%M"),
        "date": now.isoformat(),
    }
    data["conversations"][contact_id].append(msg)
    _save_mail(uid, data)

    # Forward message to recipient if they are a registered user
    contact = next((c for c in data.get("contacts", []) if c["id"] == contact_id), None)
    if contact and contact.get("email"):
        users = load_users()
        recipient_uid = None
        for uid2, u in users.get("users", {}).items():
            if u.get("email", "").lower() == contact["email"].lower():
                recipient_uid = uid2
                break
        if recipient_uid:
            rdata = _load_mail(recipient_uid)
            sender_email = user.get("email", "")
            sender_name = user.get("name", "Usuario")
            # Find existing contact in recipient's list or create one
            existing = next((c for c in rdata.get("contacts", []) if c.get("email", "").lower() == sender_email.lower()), None)
            if existing:
                target_cid = existing["id"]
            else:
                target_cid = uid
                rdata.setdefault("contacts", []).append({
                    "id": uid, "email": sender_email,
                    "name": sender_name, "picture": user.get("picture", ""),
                    "created": now.isoformat(),
                })
            rdata.setdefault("conversations", {}).setdefault(target_cid, [])
            rmsg = {
                "from": uid,
                "from_name": sender_name,
                "from_email": sender_email,
                "text": text,
                "time": now.strftime("%H:%M"),
                "date": now.isoformat(),
                "unread": True,
            }
            rdata["conversations"][target_cid].append(rmsg)
            _save_mail(recipient_uid, rdata)

    return jsonify({"message": msg})


@app.route("/api/mail/users", methods=["GET"])
@login_required
def mail_known_users():
    users = load_users()
    user_list = [v for v in users.get("users", {}).values()]
    return jsonify({"users": user_list})


@app.route("/api/mail/poll", methods=["GET"])
@login_required
def mail_poll():
    """Check for new incoming messages (from other users)."""
    user = session.get("user", {})
    uid = user.get("id", "anon")
    data = _load_mail(uid)
    # Collect all conversations that have incoming unread messages
    incoming = {}
    for cid, msgs in data.get("conversations", {}).items():
        unread = [m for m in msgs if m.get("unread") and m.get("from") != "me"]
        if unread:
            incoming[cid] = unread
    # Find contacts for these conversations
    contacts_map = {c["id"]: c for c in data.get("contacts", [])}
    return jsonify({"incoming": incoming, "contacts": contacts_map})


# ---------------------------------------------------------------------------
# MUSIC API
# ---------------------------------------------------------------------------
@app.route("/api/music/tracks", methods=["GET"])
@login_required
def music_list_tracks():
    data = _load_tracks()
    return jsonify({"tracks": data["tracks"]})


@app.route("/api/music/upload", methods=["POST"])
@login_required
def music_upload():
    user = session.get("user", {})
    uid = _safe_id(user.get("id", "anon"))
    if "file" not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Archivo vacío"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_AUDIO:
        return jsonify({"error": f"Formato {ext} no soportado"}), 400
    MUSIC_FILES_DIR.mkdir(parents=True, exist_ok=True)
    tid = "t_" + uuid.uuid4().hex[:12]
    safe_name = tid + ext
    fpath = MUSIC_FILES_DIR / safe_name
    f.save(str(fpath))
    custom_name = (request.form.get("name", "") or Path(f.filename).stem).strip()
    data = _load_tracks()
    track = {
        "id": tid,
        "name": custom_name,
        "artist": user.get("name", "Anónimo"),
        "filename": safe_name,
        "ext": ext,
        "size": fpath.stat().st_size if fpath.exists() else 0,
        "uploaded_by": uid,
        "uploaded_at": datetime.now().isoformat(),
    }
    data["tracks"].append(track)
    _save_tracks(data)
    return jsonify({"track": track})


@app.route("/api/music/tracks/<tid>", methods=["PUT"])
@login_required
def music_rename_track(tid):
    body = request.get_json(silent=True) or {}
    new_name = body.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Nombre requerido"}), 400
    data = _load_tracks()
    for t in data["tracks"]:
        if t["id"] == tid:
            t["name"] = new_name
            _save_tracks(data)
            return jsonify({"track": t})
    return jsonify({"error": "Track no encontrado"}), 404


@app.route("/api/music/tracks/<tid>", methods=["DELETE"])
@login_required
def music_delete_track(tid):
    data = _load_tracks()
    for i, t in enumerate(data["tracks"]):
        if t["id"] == tid:
            fpath = MUSIC_FILES_DIR / t["filename"]
            if fpath.exists():
                try:
                    fpath.unlink()
                except Exception:
                    pass
            data["tracks"].pop(i)
            _save_tracks(data)
            return jsonify({"ok": True})
    return jsonify({"error": "Track no encontrado"}), 404


@app.route("/api/music/serve/<filename>")
@login_required
def music_serve(filename):
    from flask import send_file
    fpath = MUSIC_FILES_DIR / filename
    if not fpath.exists():
        return "Archivo no encontrado", 404
    return send_file(str(fpath), mimetype="audio/mpeg")


# ---------------------------------------------------------------------------
# TOKENS API
# ---------------------------------------------------------------------------
@app.route("/api/tokens")
@login_required
def api_tokens():
    user = session.get("user", {})
    uid = user.get("id", "anon")
    tok = _get_user_tokens(uid)
    tok = _ensure_missions(tok)
    return jsonify({
        "balance": tok["balance"],
        "total_earned": tok["total_earned"],
        "total_spent": tok["total_spent"],
        "missions": tok.get("missions", {}),
        "missions_today": tok.get("missions_date", ""),
        "available_missions": [m for m in DAILY_MISSIONS if m["id"] not in tok.get("missions", {})],
        "costs": TOKEN_COST,
    })


@app.route("/api/tokens/complete-mission", methods=["POST"])
@login_required
def api_complete_mission():
    user = session.get("user", {})
    uid = user.get("id", "anon")
    body = request.get_json(silent=True) or {}
    mid = body.get("mission", "")
    if not mid or not any(m["id"] == mid for m in DAILY_MISSIONS):
        return jsonify({"error": "Misión inválida"}), 400
    tok = _get_user_tokens(uid)
    tok = _ensure_missions(tok)
    if mid in tok.get("missions", {}):
        return jsonify({"error": "Misión ya completada"}), 409
    mission = next(m for m in DAILY_MISSIONS if m["id"] == mid)
    tok.setdefault("missions", {})[mid] = True
    tok["balance"] += mission["reward"]
    tok["total_earned"] += mission["reward"]
    _save_user_tokens(uid, tok)
    return jsonify({"ok": True, "reward": mission["reward"], "balance": tok["balance"], "mission": mid})


@app.route("/admin/tokens/set", methods=["POST"])
@login_required
@owner_required
def admin_set_tokens():
    body = request.get_json(silent=True) or {}
    uid = body.get("user_id", "")
    amount = body.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    if not uid:
        return jsonify({"error": "Usuario requerido"}), 400
    tok = _get_user_tokens(uid)
    tok = _ensure_missions(tok)
    tok["balance"] = amount
    _save_user_tokens(uid, tok)
    return jsonify({"ok": True, "balance": tok["balance"]})


@app.route("/admin/tokens/add", methods=["POST"])
@login_required
@owner_required
def admin_add_tokens():
    body = request.get_json(silent=True) or {}
    uid = body.get("user_id", "")
    amount = body.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    if not uid:
        return jsonify({"error": "Usuario requerido"}), 400
    tok = _get_user_tokens(uid)
    tok = _ensure_missions(tok)
    tok["balance"] += amount
    if amount > 0:
        tok["total_earned"] += amount
    else:
        tok["total_spent"] = tok.get("total_spent", 0) + abs(amount)
    _save_user_tokens(uid, tok)
    return jsonify({"ok": True, "balance": tok["balance"], "added": amount})


@app.route("/admin/tokens/complete-mission", methods=["POST"])
@login_required
@owner_required
def admin_complete_mission():
    body = request.get_json(silent=True) or {}
    uid = body.get("user_id", "")
    mid = body.get("mission", "")
    if not uid or not mid:
        return jsonify({"error": "Usuario y misión requeridos"}), 400
    if not any(m["id"] == mid for m in DAILY_MISSIONS):
        return jsonify({"error": "Misión inválida"}), 400
    tok = _get_user_tokens(uid)
    tok = _ensure_missions(tok)
    if mid in tok.get("missions", {}):
        return jsonify({"error": "Misión ya completada"}), 409
    mission = next(m for m in DAILY_MISSIONS if m["id"] == mid)
    tok.setdefault("missions", {})[mid] = True
    tok["balance"] += mission["reward"]
    tok["total_earned"] += mission["reward"]
    _save_user_tokens(uid, tok)
    return jsonify({"ok": True, "reward": mission["reward"], "balance": tok["balance"], "mission": mid})


@app.route("/admin/tokens/reset-missions", methods=["POST"])
@login_required
@owner_required
def admin_reset_missions():
    body = request.get_json(silent=True) or {}
    uid = body.get("user_id", "")
    if not uid:
        return jsonify({"error": "Usuario requerido"}), 400
    tok = _get_user_tokens(uid)
    tok["missions"] = {}
    tok["missions_date"] = ""
    _save_user_tokens(uid, tok)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# BACKUP API
# ---------------------------------------------------------------------------
@app.route("/api/backup/export")
@login_required
def backup_export():
    export = _export_all()
    return jsonify(export)


@app.route("/api/backup/import", methods=["POST"])
@login_required
@owner_required
def backup_import():
    body = request.get_json(silent=True) or {}
    if "users" in body:
        save_users(body["users"])
    if "memory" in body:
        save_memory(body["memory"])
    if "messages" in body:
        save_messages(body["messages"])
    if "chats" in body:
        save_chats(body["chats"])
    if "music" in body:
        _save_tracks(body["music"])
    if "mail" in body and isinstance(body["mail"], dict):
        MAIL_DIR.mkdir(parents=True, exist_ok=True)
        for fname, fdata in body["mail"].items():
            (MAIL_DIR / f"{fname}.json").write_text(json.dumps(fdata, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True})


@app.route("/backup")
@login_required
def backup_page():
    return render_template("backup.html")


if __name__ == "__main__":
    print("--- Servidor ANS AI iniciado con motor local ---")
    app.run(debug=True)
