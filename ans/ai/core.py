import random
import re
import json
import urllib.parse
import urllib.request
import html as html_lib
from datetime import datetime
from flask import session
from ans.utils.helpers import normalize_text, get_time_response, analyze_text
from ans.ai.knowledge import (
    MODEL_INFO, KNOWLEDGE_BASE, CONCEPT_DB, CONVERSATION_CONTEXT,
    GREETING_RESPONSES, PERSONALITY_RESPONSES, TECH_JOKE,
    REASONING_ENGINE, REASONING_PATTERNS, WHY_RESPONSES,
    DIFFICULTY_MAP, IMAGE_DB, FACTS_DB,
)
from ans.ai.translate import translate_text
from ans.ai.math_solver import (
    solve_basic_equation, solve_basic_math, solve_advanced_math,
    solve_algebra, solve_logarithms, _format_num,
)
from ans.data.storage import load_memory, save_memory


def reasoning_search(term):
    term_lower = normalize_text(term)
    best_key = None
    best_score = 0
    term_words = set(term_lower.split())
    for key in CONCEPT_DB:
        key_norm = normalize_text(key)
        if key_norm == term_lower:
            return key
        key_len = len(key_norm)
        term_len = len(term_lower)
        if key_len >= 4 and term_len >= 4:
            if key_norm in term_lower or term_lower in key_norm:
                score = min(key_len, term_len) / max(key_len, term_len)
                if score > best_score:
                    best_score = score
                    best_key = key
        key_words = set(key_norm.split())
        common = len(key_words & term_words)
        if common >= 1 and len(key_words) > 0:
            ratio = common / len(key_words)
            if ratio > best_score:
                best_score = ratio
                best_key = key
    if best_key and best_score > 0.3:
        return best_key
    return None


def reason_about(text, memory):
    lower = normalize_text(text)
    for pattern, handler_type in REASONING_PATTERNS:
        match = re.search(pattern, lower)
        if not match:
            continue

        if handler_type == "what_is":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**{term.title()}** es:\n\n{data['what']}\n\n"
                if data.get("purpose"):
                    resp += f"**Para que sirve:** {data['purpose']}\n\n"
                resp += "*Quieres saber como funciona o para que sirve en especifico?*"
                return resp

        elif handler_type == "how_works":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Como funciona {term.title()}:**\n\n{data['how']}\n\n"
                if data.get("examples"):
                    resp += "**Ejemplo:**\n"
                    resp += "\n".join(f"- `{ex}`" for ex in data["examples"][:2])
                return resp

        elif handler_type == "how_use":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Como se usa {term.title()}:**\n\n"
                if data.get("examples"):
                    resp += "\n".join(f"- `{ex}`" for ex in data["examples"])
                else:
                    resp += data.get("how", "No tengo ejemplos especificos.")
                return resp

        elif handler_type == "how_to":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Paso a paso - {term.title()}:**\n\n"
                resp += f"{data['what']}\n\n"
                if data.get("how"):
                    resp += f"**Proceso:** {data['how']}\n\n"
                if data.get("examples"):
                    resp += "**Ejemplos practicos:**\n"
                    resp += "\n".join(f"- `{ex}`" for ex in data["examples"])
                return resp

        elif handler_type == "why":
            reason_text = match.group(1).strip()
            for key, explanation in WHY_RESPONSES.items():
                if normalize_text(key) in reason_text or reason_text in normalize_text(key):
                    return explanation
            concept_key = reasoning_search(reason_text)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                if data.get("why"):
                    return f"**Por que {reason_text.title()}:**\n\n{data['why']}"
            return None

        elif handler_type == "purpose":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                return f"**Para que sirve {term.title()}:**\n\n{data.get('purpose', data.get('what', 'No tengo informacion.'))}"

        elif handler_type == "pros":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Ventajas de {term.title()}:**\n\n"
                resp += f"- {data.get('what', '')}\n"
                if data.get("difficulty"):
                    resp += f"- {data['difficulty']}\n"
                if data.get("purpose"):
                    resp += f"- Sirve para: {data['purpose']}\n"
                return resp

        elif handler_type == "cons":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Desventajas/limitaciones de {term.title()}:**\n\n"
                if data.get("difficulty"):
                    resp += f"- {data['difficulty']}\n"
                return resp

        elif handler_type == "example":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                if data.get("examples"):
                    resp = f"**Ejemplos de {term.title()}:**\n\n"
                    resp += "\n".join(f"- `{ex}`" for ex in data["examples"])
                    return resp

        elif handler_type == "summary":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Resumen de {term.title()}:**\n\n"
                resp += f"{data.get('what', '')}\n\n"
                if data.get("how"):
                    resp += f"**Como funciona:** {data['how']}\n\n"
                if data.get("purpose"):
                    resp += f"**Para que sirve:** {data['purpose']}\n\n"
                if data.get("difficulty"):
                    resp += f"**Nivel de dificultad:** {data['difficulty']}"
                return resp

        elif handler_type == "differences":
            term1 = match.group(1).strip()
            term2 = match.group(2).strip()
            key1 = reasoning_search(term1)
            key2 = reasoning_search(term2)
            if key1 and key2:
                d1 = CONCEPT_DB[key1]
                d2 = CONCEPT_DB[key2]
                resp = f"**Diferencias entre {term1.title()} y {term2.title()}:**\n\n"
                resp += f"**{term1.title()}:** {d1.get('what', 'N/A')}\n\n"
                resp += f"**{term2.title()}:** {d2.get('what', 'N/A')}\n\n"
                resp += f"**Diferencia clave:** {term1.title()} {d1.get('purpose', '')} mientras que {term2.title()} {d2.get('purpose', '')}."
                return resp

        elif handler_type == "difficulty":
            term = match.group(1).strip()
            concept_key = reasoning_search(term)
            if concept_key and concept_key in DIFFICULTY_MAP:
                return DIFFICULTY_MAP[concept_key]

        elif handler_type == "recommend":
            purpose = match.group(1).strip()
            purpose_lower = normalize_text(purpose)
            recommendations = []
            if any(w in purpose_lower for w in ["web", "pagina", "sitio"]):
                recommendations = ["HTML + CSS + JavaScript", "React o Vue para frontend", "Flask o Django para backend"]
            elif any(w in purpose_lower for w in ["ia", "inteligencia", "datos", "machine"]):
                recommendations = ["Python (el mas usado en IA)", "R para estadistica", "Julia para computacion cientifica"]
            elif any(w in purpose_lower for w in ["movil", "app", "celular"]):
                recommendations = ["JavaScript + React Native", "Dart + Flutter", "Kotlin (Android) / Swift (iOS)"]
            elif any(w in purpose_lower for w in ["juego", "videojuego"]):
                recommendations = ["C# + Unity", "C++ + Unreal Engine", "Python + Pygame (para empezar)"]
            elif any(w in purpose_lower for w in ["script", "automatizar", "tarea"]):
                recommendations = ["Python (el mejor para scripts)", "Bash para tareas de sistema"]
            elif any(w in purpose_lower for w in ["aprender", "primero", "empezar", "basico"]):
                recommendations = ["Python (facil y versatil)", "JavaScript (si te gusta la web)", "HTML + CSS (si quieres ver resultados visuales rapido)"]
            else:
                recommendations = ["Python (general y facil)", "JavaScript (web)", "Depende del contexto, preguntame algo mas especifico!"]
            resp = f"**Lenguajes recomendados para {purpose}:**\n\n"
            for i, rec in enumerate(recommendations, 1):
                resp += f"{i}. **{rec}**\n"
            return resp

        elif handler_type == "step_by_step":
            task = match.group(1).strip()
            concept_key = reasoning_search(task)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Como hacer/entender {task.title()} paso a paso:**\n\n"
                resp += f"1. Primero entiende que es: {data.get('what', 'N/A')}\n\n"
                if data.get("how"):
                    resp += f"2. Asi funciona: {data['how']}\n\n"
                if data.get("examples"):
                    resp += f"3. Ejemplo practico: `{data['examples'][0]}`\n\n"
                if data.get("difficulty"):
                    resp += f"4. Nivel: {data['difficulty']}"
                return resp

    return None


def search_wikipedia(query, lang="es"):
    try:
        encoded = urllib.parse.quote(query)
        summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(summary_url, headers={"User-Agent": "ANS-AI/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "title": data.get("title", query),
                "extract": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "thumbnail": data.get("thumbnail", {}).get("source", ""),
                "description": data.get("description", ""),
                "source": "Wikipedia",
            }
    except Exception:
        return None


def search_wikipedia_search(query, lang="es", limit=3):
    try:
        encoded = urllib.parse.quote(query)
        search_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&srlimit={limit}&format=json"
        req = urllib.request.Request(search_url, headers={"User-Agent": "ANS-AI/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = []
            for item in data.get("query", {}).get("search", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": re.sub(r"<[^>]+>", "", item.get("snippet", "")),
                    "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(item.get('title', '').replace(' ', '_'))}",
                })
            return results
    except Exception:
        return []


def get_image_for_topic(text):
    lower = normalize_text(text)
    best_key = None
    best_score = 0
    for key in IMAGE_DB:
        key_norm = normalize_text(key)
        if key_norm in lower or lower in key_norm:
            score = min(len(key_norm), len(lower)) / max(len(key_norm), len(lower))
            if score > best_score:
                best_score = score
                best_key = key
    if best_key and best_score > 0.3:
        return IMAGE_DB[best_key]
    return None


def format_wiki_result(wiki_data):
    if not wiki_data or not wiki_data.get("extract"):
        return None
    parts = []
    if wiki_data.get("thumbnail"):
        parts.append(
            f'<img src="{wiki_data["thumbnail"]}" style="width:100%;max-width:350px;border-radius:12px;margin-bottom:12px;">'
        )
    parts.append(f'<strong>{wiki_data["title"]}</strong>')
    if wiki_data.get("description"):
        parts.append(f'<em style="color:#98a8c3;">{wiki_data["description"]}</em>')
    parts.append(wiki_data["extract"])
    if wiki_data.get("url"):
        parts.append(f'\n\n[Fuente: Wikipedia]({wiki_data["url"]})')
    return "\n\n".join(parts)


def search_duckduckgo(query):
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "ANS-AI/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            abstract = data.get("AbstractText", "") or data.get("Definition", "")
            source = data.get("AbstractSource", "") or data.get("DefinitionSource", "")
            if abstract:
                return {"text": abstract, "source": source or "DuckDuckGo"}
            related = data.get("RelatedTopics", [])
            if related:
                topic = related[0]
                if isinstance(topic, dict) and "Text" in topic:
                    return {"text": topic["Text"], "source": "DuckDuckGo"}
    except Exception:
        pass
    return None


def search_fact(query):
    q = normalize_text(query)
    for key, val in FACTS_DB.items():
        if key in q or q in key:
            return {"text": val, "source": "Curiosidad"}
    return None


def search_all_sources(query):
    results = []
    wiki = search_wikipedia(query)
    if wiki and wiki.get("extract"):
        img = wiki.get("thumbnail") or get_image_for_topic(query)
        results.append({
            "text": wiki["extract"][:500], "source": "Wikipedia",
            "title": wiki.get("title", query), "url": wiki.get("url", ""),
            "image": img,
        })
    ddg = search_duckduckgo(query)
    if ddg:
        img = get_image_for_topic(query)
        results.append({"text": ddg["text"], "source": "DuckDuckGo", "image": img})
    fact = search_fact(query)
    if fact:
        img = get_image_for_topic(query)
        results.append({"text": fact["text"], "source": "Curiosidad", "image": img})
    if not wiki and not ddg and not fact:
        wiki_search = search_wikipedia_search(query)
        if wiki_search:
            for r in wiki_search[:2]:
                results.append({
                    "text": r["snippet"][:300], "source": "Wikipedia (resultado)",
                    "title": r["title"], "url": r["url"],
                    "image": get_image_for_topic(query),
                })
    return results


def extract_known_answer(query, memory):
    q = normalize_text(query)
    learned = memory.get("learned", {})
    q_words = set(q.split())
    best_match = None
    best_score = 0

    for source in (learned, KNOWLEDGE_BASE):
        for key, value in source.items():
            key_norm = normalize_text(key)
            if not key_norm:
                continue
            key_words = set(key_norm.split())
            common = len(key_words & q_words)
            if common > 0 and len(key_words) > 0:
                ratio = common / len(key_words)
                if ratio > best_score:
                    best_score = ratio
                    best_match = value
            if key_norm == q:
                best_score = 1.0
                best_match = value
                break

    if best_match and best_score > 0.3:
        return best_match
    return None


def learn_fact(text, memory):
    payload = text.split(":", 1)[1].strip()
    parts = payload.split("=", 1)
    if len(parts) < 2:
        return "Formato incorrecto. Usa: **aprende: concepto = definicion**"

    key = normalize_text(parts[0])
    value = parts[1].strip()
    if not key or not value:
        return "Necesito un concepto y una definicion valida."

    memory.setdefault("learned", {})[key] = value
    save_memory(memory)
    return f'Datos asimilados correctamente. Ahora se que **"{key}"** significa: "{value}".'


def extract_search_term(text):
    lower = normalize_text(text)
    stopwords = [
        "que", "es", "un", "una", "el", "la", "los", "las", "de", "del",
        "para", "como", "funciona", "significa", "hace", "sobre", "acerca",
        "cuales", "cual", "quien", "quienes", "donde", "cuando", "cuanto",
        "por que", "porque", "explica", "dame", "cuentame", "hablame",
        "dime", "quisiera", "saber", "informacion", "info", "datos",
        "es", "son", "esta", "estan", "hay", "puede", "pueden",
        "yo", "tu", "nosotros", "ellos", "esto", "eso",
        "con", "sin", "entre", "hasta", "desde", "por", "en",
        "escribir", "leer", "crear", "usar", "saber",
        "dificil", "complicado", "complejo", "facil", "aprender",
    ]
    cleaned = re.sub(r"[?¿!¡.,;:]", "", lower)
    words = cleaned.split()
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
    return " ".join(filtered) if filtered else cleaned.strip()


def web_search_and_respond(text, memory, auto_images=True, deep_search=False):
    search_term = extract_search_term(text)
    if not search_term or len(search_term) < 2:
        return None

    all_sources = search_all_sources(search_term)
    if not all_sources:
        return None

    memory.setdefault("learned", {})[normalize_text(search_term)] = all_sources[0]["text"][:500]
    save_memory(memory)

    lines = []
    added_image = False
    for src in all_sources:
        img = src.get("image")
        if img and auto_images and not added_image:
            lines.append(f'<img src="{img}" style="width:100%;max-width:350px;border-radius:12px;margin-bottom:12px;">')
            added_image = True

    lines.append(f"**Fuentes para: {search_term.title()}**\n")

    max_sources = 5 if deep_search else 3
    for i, src in enumerate(all_sources[:max_sources], 1):
        label = src.get("source", "Desconocida")
        text_src = src.get("text", "")[:400]
        title = src.get("title")
        url = src.get("url")
        header = f"**{i}. {label}:**"
        if title:
            header += f" *{title}*"
        lines.append(f"{header}\n{text_src}")
        if url:
            lines.append(f"[Fuente]({url})")
        lines.append("")

    if not any(s.get("source") == "Wikipedia" for s in all_sources):
        search_results = search_wikipedia_search(search_term, limit=5 if deep_search else 2)
        if search_results:
            lines.append("**Mas resultados de Wikipedia:**")
            for r in search_results[:3 if deep_search else 2]:
                lines.append(f"- **{r['title']}**: {r['snippet'][:100]}...")

    if deep_search:
        lines.append("\n*Busqueda profunda activada - se mostraron mas fuentes de lo normal*")

    lines.append("---\n*Quieres que profundice en algo especifico?*")
    return "\n".join(lines)


def format_reasoned_answer(answer, question, modelo="flask"):
    if answer is None:
        return None
    if "<div class=\"math-box\">" in answer or "<pre>" in answer:
        return answer
    if modelo == "flask":
        return f"**Analisis Flask:**<br><br>{answer}<br><br><em style='color:#98a8c3;'>Quieres que profundice en algo?</em>"
    if modelo == "gapi":
        return answer
    if modelo == "modify":
        return f"**Modify Code:**<br><br>{answer}"
    return answer


def _get_last_user_topic(history):
    if not history:
        return ""
    followups = {"si", "sí", "yes", "ok", "dale", "adelante", "no", "nop", "busca",
                 "paso a paso", "ejemplo", "ejemplos", "codigo", "código"}
    for h in reversed(history):
        if h.get("rol") == "user":
            msg = normalize_text(h.get("texto", ""))
            if msg not in followups:
                return h.get("texto", "")
    return ""


def _last_ai_asked_sources(history):
    if not history:
        return False
    for h in reversed(history):
        if h.get("rol") == "ai":
            msg = h.get("texto", "")
            if "Quieres que busque fuentes" in msg:
                return True
            return False
    return False


def _apply_detail(resp, is_detail):
    if is_detail or not resp:
        return resp
    lines = resp.split("\n")
    short = [l for l in lines if l.strip() and (
        not l.strip().startswith("---") and
        not l.strip().startswith("*") and
        not l.strip().startswith("✏️") and
        "profundice" not in l.lower() and
        "quieres que" not in l.lower() and
        "dime" not in l.lower()
    )]
    return "\n".join(short[:5] + (["", "*Modo conciso activado*"] if len(short) > 5 else []))


def detect_intent(text, memory):
    lower = normalize_text(text)
    now = datetime.now()

    if re.search(r"(?:chiste|joke|reirme|divertirme)", lower):
        return random.choice(TECH_JOKE)

    draw_match = re.search(r"(?:dibuja|draw|pinta|dibujame)\s+(.+?)[\?\s]*$", lower)
    if draw_match:
        thing = draw_match.group(1).strip()
        return f"**Voy a dibujar:** {thing}\n\n_Usa el boton de dibujo en el chat para verlo_"

    fuentes_match = re.search(r"(?:fuentes?|sources?|buscar fuentes)\s*[:\-]?\s*(.+)", lower)
    if fuentes_match:
        query = fuentes_match.group(1).strip()
        if query:
            sources = search_all_sources(query)
            if sources:
                lines = [f"**Fuentes para \"{query}\":**\n"]
                for i, s in enumerate(sources, 1):
                    label = s.get("source", "Desconocida")
                    lines.append(f"**{i}. {label}:** {s.get('text', '')[:300]}...")
                return "\n".join(lines)
            return f"No encontre fuentes para \"{query}\""
        return "Especifica que buscar: `fuentes: python`"

    if lower.startswith("aprende:"):
        return learn_fact(text, memory)

    if lower.startswith("calcula:"):
        expr = text[len("calcula:"):].strip()
        for solver in [solve_basic_equation, solve_basic_math, solve_advanced_math, solve_algebra, solve_logarithms]:
            result = solver(expr)
            if result:
                return result
        try:
            safe = re.sub(r"(\d+)x\^?2", r"\1**2", expr.lower())
            safe = re.sub(r"(\d+)x", r"\1*", safe)
            safe_num = re.sub(r"[^\d\s\+\-\*/\(\)\.\%]", "", safe)
            if safe_num.strip():
                from math import log, log10, sqrt
                val = eval(safe_num, {"__builtins__": {}}, {"log": log, "log10": log10, "sqrt": sqrt})
                return f"Resultado: {_format_num(val)}"
        except Exception:
            pass
        return f"Procesando: {expr}"

    algebra = solve_algebra(text)
    if algebra:
        return algebra

    log_result = solve_logarithms(text)
    if log_result:
        return log_result

    if lower.startswith("traduce:"):
        match = re.search(r"traduce:\s*(.+?)(?:\s*a\s+(ingles|ingles|english|espanol|español|es|en|fr|pt|it|de|ja|zh|ko|ru))?\s*$", lower, re.IGNORECASE)
        if match:
            txt = match.group(1).strip()
            tgt = match.group(2).strip().lower() if match.group(2) else "en"
            lang_map = {
                "espanol": "es", "español": "es", "es": "es",
                "ingles": "en", "english": "en", "en": "en",
                "frances": "fr", "french": "fr", "fr": "fr",
                "portugues": "pt", "portuguese": "pt", "pt": "pt",
                "italiano": "it", "italian": "it", "it": "it",
                "aleman": "de", "german": "de", "de": "de",
                "japones": "ja", "japanese": "ja", "ja": "ja",
                "chino": "zh", "chinese": "zh", "zh": "zh",
                "coreano": "ko", "korean": "ko", "ko": "ko",
                "ruso": "ru", "russian": "ru", "ru": "ru",
            }
            target = lang_map.get(tgt, tgt)
            if len(target) > 5:
                return f"Idioma no reconocido: {tgt}. Usa: `traduce: texto a ingles`"
            result = translate_text(txt, target)
            if result:
                flag_map = {"es": "🇪🇸", "en": "🇬🇧", "fr": "🇫🇷", "pt": "🇵🇹", "it": "🇮🇹", "de": "🇩🇪", "ja": "🇯🇵", "zh": "🇨🇳", "ko": "🇰🇷", "ru": "🇷🇺"}
                flag = flag_map.get(target, "🌐")
                return f"**{flag} Traduccion al {tgt}:**\n\n> {html_lib.escape(result)}"
            return "No pude traducir eso. Intenta de nuevo."
        return "Usa: `traduce: texto a ingles` o `traduce: hello a espanol`"

    equation = solve_basic_equation(text)
    if equation:
        return equation

    adv_math = solve_advanced_math(text)
    if adv_math:
        return adv_math

    math_result = solve_basic_math(text)
    if math_result:
        return math_result

    time_resp = get_time_response(text)
    if time_resp:
        return time_resp

    text_analysis = analyze_text(text)
    if text_analysis:
        return text_analysis

    for greeting, responses in CONVERSATION_CONTEXT.items():
        if lower == greeting or re.search(rf"^{re.escape(greeting)}\s*[!.]?\s*$", lower):
            return random.choice(responses)

    for trigger, response in GREETING_RESPONSES.items():
        if trigger in lower:
            return response

    for trigger, response in PERSONALITY_RESPONSES.items():
        if trigger in lower:
            return response

    return None


def respond_with_flask_model(message, history, memory, user):
    text = message.strip()
    lower = normalize_text(text)
    raw_name = (user.get("name") or "").strip()
    user_name = raw_name.split("@")[0].split()[0] if raw_name else ""
    auto_sources = session.get("auto_sources", False)
    auto_images = session.get("auto_images", True)
    deep_search = session.get("deep_search", False)
    detallado = session.get("detallado", True)
    asked_sources = _last_ai_asked_sources(history)

    if not text:
        greeting = f"{user_name}! " if user_name else ""
        return f"{greeting}Escribe una pregunta y te dare una explicacion detallada paso a paso."

    if asked_sources and lower in ["si", "sí", "yes", "ok", "dale", "adelante", "busca"]:
        topic = _get_last_user_topic(history)
        if topic:
            web_result = web_search_and_respond(topic, memory, auto_images, deep_search)
            if web_result:
                return (
                    f"**Fuentes web para \"{topic}\":**\n\n{web_result}\n\n"
                    f"---\n*Quieres que profundice? Dime 'paso a paso', 'ejemplo', 'codigo'.*"
                )
            return f"No encontre fuentes web para **\"{topic}\"**. Prueba con otro tema."
        return "Sobre que tema quieres que busque fuentes?"

    if asked_sources and lower in ["no", "nop", "no gracias", "no quiero", "no busques", "no hace falta"]:
        topic = _get_last_user_topic(history)
        if topic:
            concept_key = reasoning_search(topic)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**{topic.title()}**\n\n"
                resp += f"**Que es?** {data.get('what', '')}\n\n"
                if data.get("how"):
                    resp += f"**Como funciona?** {data['how']}\n\n"
                if data.get("purpose"):
                    resp += f"**Para que sirve?** {data['purpose']}\n\n"
                if data.get("examples"):
                    resp += "**Ejemplos:**\n" + "\n".join(f"- `{e}`" for e in data["examples"][:3])
                return resp
            known = extract_known_answer(topic, memory)
            if known:
                return f"**{topic.title()}:**\n\n{known}"
        return "De acuerdo. Preguntame sobre otro tema o dime 'paso a paso', 'ejemplo', 'codigo'."

    if lower in ["paso a paso", "ejemplo", "ejemplos", "codigo", "código", "caso uso", "casos de uso"]:
        last_topic = _get_last_user_topic(history)
        if last_topic:
            concept_key = reasoning_search(last_topic)
            if "ejemplo" in lower:
                if concept_key and CONCEPT_DB[concept_key].get("examples"):
                    exs = CONCEPT_DB[concept_key]["examples"]
                    return f"**Ejemplos practicos de {concept_key}:**\n\n" + "\n".join(f"- `{e}`" for e in exs)
                web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
                if web_result:
                    return f"**Ejemplos desde la web para {last_topic}:**\n\n{web_result}"
            elif "codigo" in lower:
                if concept_key and CONCEPT_DB[concept_key].get("examples"):
                    exs = CONCEPT_DB[concept_key]["examples"]
                    return f"**Codigo de {concept_key}:**\n\n" + "\n".join(f"- `{e}`" for e in exs)
                web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
                if web_result:
                    return f"**Referencias de codigo para {last_topic}:**\n\n{web_result}"
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"**Guia paso a paso: {concept_key.title()}**\n\n"
                resp += f"**1. Que es?** {data.get('what', 'Concepto fundamental.')}\n\n"
                if data.get("how"):
                    resp += f"**2. Como funciona?** {data['how']}\n\n"
                if data.get("purpose"):
                    resp += f"**3. Para que sirve?** {data['purpose']}\n\n"
                if data.get("examples"):
                    resp += "**4. Ejemplos practicos:**\n"
                    for ex in data["examples"][:3]:
                        resp += f"   - `{ex}`\n"
                    resp += "\n"
                if data.get("difficulty"):
                    resp += f"**5. Nivel:** {data['difficulty']}\n\n"
                resp += "---\n*Quieres ver codigo real, casos de uso, o comparar con algo similar?*"
                return resp
            web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
            if web_result:
                return f"**Estructurando informacion para {last_topic}:**\n\n{web_result}"
            return f"No tengo informacion estructurada para **\"{last_topic}\"**."
        return "Sobre que tema quieres la explicacion?"

    if lower in ["si", "sí", "yes", "dale", "adelante", "continua", "continúa", "mas", "más", "profundiza"]:
        last_topic = _get_last_user_topic(history)
        if last_topic:
            reasoning = reason_about(last_topic, memory)
            if reasoning:
                return f"**Profundizando en: {last_topic}**\n\n" + reasoning
            web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
            if web_result:
                return f"**Mas informacion sobre \"{last_topic}\":**\n\n{web_result}"
            return f"No tengo mas informacion sobre **\"{last_topic}\"**."

    intent = detect_intent(text, memory)
    if intent:
        if "<div class=" in intent:
            return intent
        if user_name and any(w in lower for w in ["hola", "buenos", "buenas", "gracias"]):
            intent = intent.replace("Hola!", f"Hola {user_name}!").replace("Bienvenido", f"Bienvenido {user_name}")
        return f"{intent}\n\n*Si quieres profundizar mas, solo pidemelo.*"

    if "quien eres" in lower:
        name_part = f", {user_name}" if user_name else ""
        return f"Soy **ANS Flask{name_part}**, el modo de razonamiento profundo de ANS AI. Creado por **Aldrin Nicolas Salazar Avilas**."

    if "creador" in lower:
        return "Mi creador es **Aldrin Nicolas Salazar Avilas**."

    search_term = extract_search_term(text)
    if not search_term:
        search_term = text[:50]

    if auto_sources:
        web_result = web_search_and_respond(text, memory, auto_images, deep_search)
        concept_key = reasoning_search(text)
        if concept_key:
            data = CONCEPT_DB[concept_key]
            local_info = f"**{concept_key.title()}:**\n{data.get('what', '')}\n"
            if data.get("purpose"):
                local_info += f"\n**Para que sirve:** {data['purpose']}\n"
            if web_result:
                return (
                    f"**Informacion sobre \"{text}\":**\n\n"
                    f"{local_info}\n"
                    f"---\n"
                    f"**Fuentes web automaticas:**\n\n{web_result}\n\n"
                    f"---\n*Quieres que profundice mas?*"
                )
            return local_info + "\n\n---\n*Quieres que busque mas fuentes web?*"
        if web_result:
            return (
                f"**Informacion web sobre \"{text}\":**\n\n{web_result}\n\n"
                f"---\n*Te gustaria que lo explique paso a paso?*"
            )
        reasoning = reason_about(text, memory)
        if reasoning:
            return f"**Analisis:**\n\n{reasoning}"
        known = extract_known_answer(text, memory)
        if known:
            return f"**Conocimiento previo:**\n\n{known}"
        return f"No encontre informacion sobre **\"{text}\"** en ninguna fuente."

    concept_key = reasoning_search(text)
    known = extract_known_answer(text, memory)
    reasoning = reason_about(text, memory)

    if concept_key or known or reasoning:
        return (
            f"Tengo informacion sobre **\"{text}\"** en mi base local.\n\n"
            f"**Quieres que busque fuentes web (Wikipedia, DuckDuckGo, +100 curiosidades) para complementar?**\n\n"
            f"Responde **\"si\"** para buscar fuentes, o **\"no\"** para que responda con mi conocimiento local."
        )
    else:
        return (
            f"No tengo **\"{text}\"** en mi base local.\n\n"
            f"**Quieres que busque fuentes web (Wikipedia, DuckDuckGo, +100 datos) sobre esto?**\n\n"
            f"Responde **\"si\"** para buscar fuentes, o **\"no\"** para que intente responder con mi base de conocimiento."
        )


def respond_with_gapi_model(message, history, memory, user):
    text = message.strip()
    lower = normalize_text(text)
    raw_name = (user.get("name") or "").strip()
    user_name = raw_name.split("@")[0].split()[0] if raw_name else ""

    if not text:
        return "Escribe algo."

    intent = detect_intent(text, memory)
    if intent:
        if "hola" in lower or "buenos" in lower:
            return f"Que hay {user_name}!" if user_name else "Que hay."
        return intent

    if "quien eres" in lower:
        return "Gapi. Modo tecnico rapido. Creado por Aldrin Nicolas Salazar Avilas."

    if "hola" == lower:
        return f"Que hay {user_name}." if user_name else "Que hay."

    reasoning = reason_about(text, memory)
    if reasoning:
        lines = reasoning.split('\n')
        concise = [l for l in lines if l.strip() and not l.startswith('*')]
        return '\n'.join(concise[:5])

    known = extract_known_answer(text, memory)
    if known:
        return known

    web_result = web_search_and_respond(text, memory)
    if web_result:
        return web_result

    return f"No info sobre \"{text}\". Usa: `aprende: {text} = definicion`"


def respond_with_modify_model(message, history, memory, user):
    text = message.strip()
    lower = normalize_text(text)
    user_name = user.get("name", "Alguien")

    if not text:
        return "Hola! Soy Modify Code. Puedo conversar contigo y si quieres ensenarme algo nuevo, solo dime: `aprende: tema = definicion`"

    if lower.startswith("aprende:"):
        result = learn_fact(text, memory)
        return f"{result}\n\n*Gracias {user_name}, lo recordare!*"

    if random.random() < 0.08 and len(memory.get("learned", {})) > 0:
        sample = random.choice(list(memory["learned"].items()))
        return f"Sabes? Alguien me enseno que **{sample[0]}** es: {sample[1][:100]}\n\n" + random.choice([
            "Que opinas de eso?", "Te parece correcto?", "Quieres agregar algo mas?"
        ])

    intent = detect_intent(text, memory)
    if intent:
        return intent

    if "quien eres" in lower:
        return "Soy **Modify Code**, un asistente conversacional que aprende solo cuando me ensenas. Uso el comando `aprende: concepto = definicion` para guardar conocimiento nuevo."

    if "hola" == lower or "buenos" in lower or "buenas" in lower:
        return random.choice([
            f"Hola {user_name}! Como estas hoy?",
            f"Que tal {user_name}! En que puedo ayudarte?",
            f"Saludos {user_name}! Dime en que andas trabajando.",
        ])

    if "gracias" in lower:
        return random.choice(["De nada! Para eso estoy.", "Un placer ayudarte.", "Cuando quieras!"])

    if "como estas" in lower:
        return f"Excelente! Listo para conversar. Tu como estas {user_name}?"

    reasoning = reason_about(text, memory)
    if reasoning:
        return reasoning

    known = extract_known_answer(text, memory)
    if known:
        return known

    web_result = web_search_and_respond(text, memory)
    if web_result:
        return web_result

    return (
        f"Interesante! No tengo informacion sobre **\"{text}\"** aun.\n\n"
        f"Si quieres que lo aprenda, dime:\n"
        f"`aprende: {text} = lo que quieras que sepa`\n\n"
        f"O preguntame sobre otro tema!"
    )
