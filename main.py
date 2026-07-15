from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json
import os
import re
import unicodedata
import math
import random
import urllib.request
import urllib.parse
import uuid
import html as html_lib
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps


def load_dotenv(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app.secret_key = os.environ.get("SECRET_KEY", "ans-ai-secret-key-change-in-production-2024")
IS_PROD = "VERCEL_URL" in os.environ or "RENDER_EXTERNAL_URL" in os.environ or os.environ.get("GOOGLE_REDIRECT_URI", "").startswith("https://")
app.config.update(
    SESSION_COOKIE_SECURE=IS_PROD,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None" if IS_PROD else "Lax",
    SESSION_COOKIE_NAME="ans_session",
)
MEMORY_FILE = BASE_DIR / "ans_memory.json"
USER_FILE = BASE_DIR / "ans_users.json"
HISTORY_DIR = BASE_DIR / "ans_history"
CHATS_FILE = BASE_DIR / "ans_chats.json"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback")

OWNER_EMAIL = "aldrinnicolassalazaravilas@gmail.com"

KV_REST_API_URL = os.environ.get("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")

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

def auto_delete_old_chats():
    """Delete chats older than 10 days"""
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
                    # Delete history file too
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

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user", {})
        if user.get("email") != OWNER_EMAIL:
            return redirect(url_for("hm"))
        return f(*args, **kwargs)
    return decorated


def is_owner():
    return session.get("user", {}).get("email") == OWNER_EMAIL


MODEL_INFO = {
    "flask": {
        "name": "ANS Flask",
        "description": "Razonamiento profundo con respuestas educativas detalladas paso a paso.",
        "features": ["Explicaciones detalladas", "Pasos educativos", "Analogias y contexto", "Preguntas de seguimiento"],
    },
    "gapi": {
        "name": "ANS Gapi",
        "description": "Respuestas tecnicas directas con ejemplos de codigo y al grano.",
        "features": ["Solo codigo y tecnicismos", "Sin rodeos", "Ejemplos practicos", "Respuestas cortas"],
    },
    "modify": {
        "name": "Modify Code",
        "description": "Modo aprendizaje: absorbe conocimiento de cada conversacion y evoluciona.",
        "features": ["Aprende de cada mensaje", "Memoria colectiva", "Evoluciona con uso", "Recuerda todo"],
    },
}

KNOWLEDGE_BASE = {
    "html": "HTML (HyperText Markup Language) es el esqueleto de una pagina web. Define la estructura del contenido usando etiquetas como <div>, <p>, <h1>, etc.",
    "css": "CSS (Cascading Style Sheets) controla la presentacion visual: colores, espacios, tipografia, layout, animaciones y diseño responsivo.",
    "javascript": "JavaScript es un lenguaje de programacion que agrega interactividad, logica y dinamismo al navegador. Permite manipular el DOM, hacer peticiones HTTP y mucho mas.",
    "python": "Python es un lenguaje de programacion de alto nivel, interpretado y multiparadigma. Es popular por su sintaxis clara y se usa en IA, web, datos y ciencia.",
    "java": "Java es un lenguaje orientado a objetos, compilado y multiplataforma. Usa el JDK para compilar y es muy usado en empresariales y Android.",
    "flask": "Flask es un microframework de Python para crear aplicaciones web y APIs. Es ligero, flexible y ideal para prototipos y proyectos medianos.",
    "django": "Django es un framework web completo para Python. Incluye ORM, admin, autenticacion y seguridad integrada.",
    "react": "React es una libreria de JavaScript para construir interfaces de usuario componentizadas. Desarrollada por Meta (Facebook).",
    "nodejs": "Node.js es un entorno de ejecucion de JavaScript fuera del navegador. Permite crear servidores y APIs en JS.",
    "git": "Git es un sistema de control de versiones distribuido. Permite rastrear cambios en el codigo y colaborar en equipo.",
    "github": "GitHub es una plataforma de hosting de repositorios Git con herramientas de colaboracion, issues, pull requests y CI/CD.",
    "sql": "SQL (Structured Query Language) es el lenguaje para gestionar y consultar bases de datos relacionales como MySQL, PostgreSQL y SQLite.",
    "mysql": "MySQL es un sistema de gestion de bases de datos relacional, uno de los mas populares del mundo. Es open source y muy rapido.",
    "postgresql": "PostgreSQL es una base de datos relacional avanzada, open source, conocida por su fiabilidad, escalabilidad y soporte de tipos de datos avanzados.",
    "api": "API (Application Programming Interface) es un conjunto de reglas que permiten que dos aplicaciones se comuniquen entre si.",
    "rest": "REST es un estilo de arquitectura para APIs web. Usa verbos HTTP (GET, POST, PUT, DELETE) y recursos identificados por URLs.",
    "json": "JSON (JavaScript Object Notation) es un formato ligero de intercambio de datos, facil de leer y escribir para humanos y maquinas.",
    "machine learning": "Machine Learning es una rama de la IA donde los sistemas aprenden automaticamente de datos sin ser programados explicitamente para cada tarea.",
    "inteligencia artificial": "La Inteligencia Artificial es la disciplina que crea sistemas capaces de realizar tareas que normalmente requieren inteligencia humana: razonar, aprender, entender lenguaje.",
    "deep learning": "Deep Learning es un subconjunto del Machine Learning que usa redes neuronales artificiales con muchas capas para aprender representaciones jerarquicas de los datos.",
    "redes neuronales": "Las redes neuronales son modelos computacionales inspirados en el cerebro humano. Constan de neuronas artificiales organizadas en capas que procesan informacion.",
    "css grid": "CSS Grid es un sistema de layout bidimensional que permite crear diseños complejos con filas y columnas de forma sencilla.",
    "flexbox": "Flexbox es un metodo de layout en CSS para distribuir y alinear elementos dentro de un contenedor, incluso cuando su tamaño es desconocido.",
    "sistema operativo": "Un sistema operativo es el software que gestiona el hardware y los recursos de una computadora. Ejemplos: Windows, macOS, Linux.",
    "linux": "Linux es un sistema operativo open source basado en Unix. Es la base de servidores, supercomputadoras, Android y muchos dispositivos.",
    "windows": "Windows es el sistema operativo de escritorio mas popular del mundo, desarrollado por Microsoft.",
    "algoritmo": "Un algoritmo es un conjunto finito de instrucciones o reglas paso a paso para resolver un problema o realizar una tarea.",
    "estructura de datos": "Las estructuras de datos son formas de organizar y almacenar datos en una computadora para que puedan ser accedidos y modificados eficientemente.",
    "ans ai": "ANS AI es un asistente virtual local creado por Aldrin Nicolas Salazar Avilas. Funciona con un motor de razonamiento local en Python/Flask, tiene memoria persistente y dos modos: Flask (razonamiento profundo) y Gapi (consultas rapidas).",
    "aldrin": "Aldrin Nicolas Salazar Avilas es el creador y desarrollador de ANS AI y del Proyecto ANS.",
    "proyecto ans": "El Proyecto ANS es una plataforma web educativa con asistente de IA integrado, juegos interactivos para aprender informatica y herramientas de aprendizaje.",
    "sass": "SASS es un preprocesador de CSS que agrega variables, anidamiento, mixins y funciones para escribir CSS mas organizado y mantenible.",
    "webpack": "Webpack es un bundler de JavaScript que empaleta todos los assets (JS, CSS, imagenes) en archivos optimizados para produccion.",
    "npm": "npm es el gestor de paquetes oficial de Node.js con el repositorio mas grande del mundo. Se usa para instalar y gestionar dependencias.",
    "vue": "Vue.js es un framework JavaScript progresivo para interfaces de usuario, conocido por su facilidad de aprendizaje y flexibilidad.",
    "angular": "Angular es un framework web completo de Google con TypeScript, ideal para proyectos grandes y empresariales.",
    "nextjs": "Next.js es un framework de React con SSR, SSG, y optimizaciones automaticas para sitios web rapidos y SEO-friendly.",
    "mongodb": "MongoDB es una base de datos NoSQL basada en documentos que guarda datos en formato BSON, ideal para datos flexibles.",
    "redis": "Redis es una base de datos en memoria ultra-rapida usada como cache, cola de mensajes y almacenamiento de sesiones.",
    "aws": "Amazon Web Services es la plataforma de cloud computing mas grande del mundo con mas de 200 servicios.",
    "flutter": "Flutter es un SDK de Google para crear apps moviles nativas para Android e iOS con un solo codigo fuente usando Dart.",
    "kotlin": "Kotlin es el lenguaje oficial para desarrollo Android, moderno y 100% interoperable con Java.",
    "swift": "Swift es el lenguaje de Apple para crear apps de iOS, macOS, watchOS y tvOS.",
    "rust": "Rust es un lenguaje de sistemas enfocado en seguridad, velocidad y concurrencia. Usado en Firefox, Docker y mas.",
    "go": "Go (Golang) es un lenguaje de Google disenado para simplicidad, eficiencia y concurrencia. Docker y Kubernetes estan hechos en Go.",
    "docker": "Docker es una plataforma de contenedorizacion que empaleta aplicaciones con todas sus dependencias en containers portables.",
    "kubernetes": "Kubernetes es una plataforma de orquestacion de containers que automatiza despliegue, escalado y gestion de apps.",
    "terraform": "Terraform es una herramienta de HashiCorp para infraestructura como codigo que permite crear y gestionar infraestructura en la nube.",
    "laravel": "Laravel es el framework PHP mas popular, elegante y con la mejor comunidad. Usa Eloquent ORM y Blade templates.",
    "django": "Django es un framework web completo para Python con ORM, admin, autenticacion y seguridad integrada.",
    "ruby": "Ruby es un lenguaje elegante y orientado a objetos, conocido por Ruby on Rails para desarrollo web rapido.",
    "php": "PHP es un lenguaje del lado del servidor que powers el 77% de la web, incluyendo WordPress.",
    "babel": "Babel es un compilador de JavaScript que transforma codigo moderno en versiones compatibles con navegadores antiguos.",
    "vue": "Vue.js es un framework JavaScript progresivo para interfaces de usuario, conocido por su facilidad de aprendizaje.",
    "angular": "Angular es un framework web completo de Google con TypeScript, ideal para proyectos grandes y empresariales.",
    "nextjs": "Next.js es un framework de React con SSR, SSG, y optimizaciones automaticas para sitios web rapidos.",
    "mongodb": "MongoDB es una base de datos NoSQL basada en documentos en formato BSON, ideal para datos flexibles.",
    "redis": "Redis es una base de datos en memoria ultra-rapida usada como cache, colas y sesiones.",
    "aws": "Amazon Web Services es la plataforma de cloud computing mas grande del mundo.",
    "flutter": "Flutter es un SDK de Google para crear apps moviles nativas con un solo codigo usando Dart.",
    "kotlin": "Kotlin es el lenguaje oficial para desarrollo Android, moderno y interoperable con Java.",
    "swift": "Swift es el lenguaje de Apple para crear apps de iOS, macOS, watchOS y tvOS.",
    "terraform": "Terraform permite crear y gestionar infraestructura en la nube con archivos de configuracion.",
}

CONVERSATION_CONTEXT = {
    "hola": [
        "Hola! Estoy listo para ayudarte. Puedo responder preguntas, resolver matematicas, explicar conceptos de programacion y mucho mas.",
        "Hola! Bienvenido. Mi motor de razonamiento esta activo. Escribe lo que necesites.",
        "Saludos! ANS AI a tu servicio. En que puedo ayudarte hoy?",
    ],
    "gracias": [
        "De nada! Siempre es un placer ayudarte.",
        "Para eso estamos! Si necesitas algo mas, aqui estoy.",
        "No hay de que! Preguntame lo que quieras.",
    ],
    "adios": [
        "Hasta luego! Fue un placer ayudarte. Vuelve cuando quieras.",
        "Nos vemos! Recuerda que estoy aqui cuando me necesites.",
        "Adios! Que tengas un excelente dia.",
    ],
    "buenos dias": [
        "Buenos dias! Espero que tengas un dia productivo. En que puedo ayudarte?",
        "Buenos dias! El dia esta perfecto para aprender algo nuevo. Preguntame!",
    ],
    "buenas tardes": [
        "Buenas tardes! Como puedo asistirte en esta tarde?",
        "Buenas tardes! Aqui estoy para lo que necesites.",
    ],
    "buenas noches": [
        "Buenas noches! Antes de descansar, hay algo que pueda ayudarte?",
        "Buenas noches! Estoy disponible si necesitas algo.",
    ],
}

GREETING_RESPONSES = {
    "como estas": "Funcionando al 100%! Todos mis modulos estan operativos. Tu como estas?",
    "que tal": "Todo excelente por aqui! Mis circuitos estan frescos y listos para trabajar.",
    "que onda": "Todo bien! Disparando neuronas a toda velocidad. Que necesitas?",
}

PERSONALITY_RESPONSES = {
    "que puedes hacer": (
        "Puedo muchas cosas!\n\n"
        "**Razonamiento:**\n"
        "- Que es [concepto]? -> Te explico que es, como funciona y para que sirve\n"
        "- Por que [fenomeno]? -> Te doy la explicacion con razonamiento\n"
        "- Cuales son las diferencias entre [X] y [Y] -> Comparo ambos\n"
        "- Dame un ejemplo de [tema] -> Ejemplos practicos\n"
        "- Es dificil [aprender X]? -> Te doy mi评估\n"
        "- Que lenguaje es mejor para [proposito]? -> Recomendaciones\n\n"
        "**Funciones:**\n"
        "- Matematicas: escribe operaciones como '25 + 17' o '3x + 5 = 20'\n"
        "- Fecha y hora: dime 'que hora es' o 'que fecha es'\n"
        "- Busqueda web: busco en Wikipedia si no se la respuesta\n"
        "- Aprendizaje: usa 'aprende: concepto = definicion'\n"
        "- Chistes: dime 'dame un chiste'"
    ),
    "ayuda": (
        "**Guia completa de ANS AI:**\n\n"
        "**Preguntas de razonamiento:**\n"
        "- `que es python?` -> Explicacion completa\n"
        "- `como funciona react?` -> Como funciona paso a paso\n"
        "- `por que el cielo es azul?` -> Razonamiento cientifico\n"
        "- `cuales son las diferencias entre Python y Java?` -> Comparacion\n"
        "- `dame un ejemplo de HTML` -> Ejemplos practicos\n"
        "- `es dificil aprender C++?` ->评估 de dificultad\n"
        "- `que lenguaje es mejor para web?` -> Recomendacion\n\n"
        "**Matematicas:**\n"
        "- `25 + 17` -> Operaciones basicas\n"
        "- `3x + 5 = 20` -> Ecuaciones con pasos\n"
        "- `20% de 500` -> Porcentajes\n"
        "- `raiz cuadrada de 144` -> Raices\n"
        "- `5!` -> Factorial\n\n"
        "**Otros:**\n"
        "- `que hora es` / `que fecha es`\n"
        "- `dame un chiste`\n"
        "- `aprende: concepto = definicion`"
    ),
}

TECH_JOKE = [
    "Por que los programadores prefieren el modo oscuro? Porque la luz atrae a los bugs!",
    "Cuanto tarda un programador en cambiar una bombilla? Ninguno, eso es problema de hardware!",
    "Un SQL entra a un bar, ve dos tablas y pregunta: puedo hacer un JOIN?",
    "Hay 10 tipos de personas: las que entienden binario y las que no.",
    "Por que JavaScript siempre se enfada? Porque no entiende las typeof!",
]


REASONING_ENGINE = {
    "que es": {
        "pattern": r"que\s+es\s+(.+?)[\?]?$/",
        "handler": "explain_concept",
    },
    "como funciona": {
        "pattern": r"como\s+funciona\s+(.+?)[\?]?$/",
        "handler": "explain_how",
    },
    "por que": {
        "pattern": r"por\s+que\s+(.+?)[\?]?$/",
        "handler": "explain_why",
    },
    "para que sirve": {
        "pattern": r"para\s+que\s+sirve\s+(.+?)[\?]?$/",
        "handler": "explain_purpose",
    },
    "cuales son las diferencias": {
        "pattern": r"cuales?\s+son?\s+(?:las?\s+)?diferencias?\s+entre\s+(.+?)\s+y\s+(.+?)[\?]?$/",
        "handler": "compare_things",
    },
    "que diferencia hay": {
        "pattern": r"que\s+diferencia\s+hay\s+entre\s+(.+?)\s+y\s+(.+?)[\?]?$/",
        "handler": "compare_things",
    },
    "ventajas": {
        "pattern": r"(?:cuales?\s+son?\s+)?(?:las?\s+)?ventajas?\s+(?:de|del)\s+(.+?)[\?]?$/",
        "handler": "list_pros",
    },
    "desventajas": {
        "pattern": r"(?:cuales?\s+son?\s+)?(?:las?\s+)?desventajas?\s+(?:de|del)\s+(.+?)[\?]?$/",
        "handler": "list_cons",
    },
    "ejemplo": {
        "pattern": r"(?:dame|pon|mustra|ense[nñ]ame)\s+(?:un\s+)?ejemplo\s+(?:de|del)\s+(.+?)[\?]?$/",
        "handler": "give_example",
    },
    "resumen": {
        "pattern": r"(?:dame|pon|haz)\s+(?:un\s+)?resumen\s+(?:de|sobre|del)\s+(.+?)[\?]?$/",
        "handler": "give_summary",
    },
    "es dificil": {
        "pattern": r"es\s+(?:dificil|complicado|complejo)\s+(?:aprender|entender|usar)\s+(.+?)[\?]?$/",
        "handler": "assess_difficulty",
    },
    "que lenguaje": {
        "pattern": r"(?:que|cual)\s+lenguaje\s+(?:de\s+programacion\s+)?(?:es\s+)?(?:mejor|ideal|bueno|recomendado)\s+(?:para|para\s+aprender|para\s+hacer)\s+(.+?)[\?]?$/",
        "handler": "recommend_language",
    },
    "cuanto vale": {
        "pattern": r"(?:cuanto\s+(?:vale|cuesta|precio))\s+(.+?)[\?]?$/",
        "handler": "check_price",
    },
    "pasos": {
        "pattern": r"(?:como\s+)?(?:puedo|hacer|puedo\s+hacer)\s+(.+?)(?:\s+paso\s+a\s+paso)?[\?]?$/",
        "handler": "step_by_step",
    },
}

CONCEPT_DB = {
    "python": {
        "what": "Python es un lenguaje de programacion de alto nivel, interpretado y multiparadigma. Fue creado por Guido van Rossum en 1991.",
        "how": "Python se ejecuta mediante un interpretador que lee el codigo linea por linea y lo convierte en bytecode, que luego se ejecuta en la maquina virtual de Python.",
        "why": "Python se usa porque su sintaxis es clara y facil de leer, tiene una enorma cantidad de librerias, y sirve para casi todo: web, IA, datos, automatizacion.",
        "purpose": "Python sirve para crear aplicaciones web, analizar datos, crear inteligencia artificial, automatizar tareas, y mucho mas.",
        "examples": [
            "print('Hola Mundo') - imprime texto",
            "for i in range(10): print(i) - imprime del 0 al 9",
            "def saludar(nombre): return f'Hola {nombre}' - define una funcion",
        ],
        "difficulty": "Python es uno de los lenguajes mas faciles de aprender. Su sintaxis es similar al ingles y tiene mucha documentacion.",
        "languages_used_for": ["web (Django, Flask)", "ciencia de datos (Pandas, NumPy)", "IA (TensorFlow, PyTorch)", "automatizacion", "juegos (Pygame)"],
    },
    "javascript": {
        "what": "JavaScript es un lenguaje de programacion interpretado, orientado a eventos y multiparadigma. Es el lenguaje de la web.",
        "how": "JavaScript se ejecuta en el navegador (frontend) o en Node.js (backend). Usa un motor de ejecucion (V8 en Chrome) que compila el codigo a bytecode optimizado.",
        "why": "JavaScript es esencial para la web interactiva. Casi todas las paginas web lo usan, y con Node.js tambien sirve para el backend.",
        "purpose": "JavaScript sirve para hacer paginas web interactivas, aplicaciones de escritorio (Electron), servidores (Node.js), y apps moviles (React Native).",
        "examples": [
            "console.log('Hola Mundo') - imprime en consola",
            "document.getElementById('app').innerHTML = 'Hola' - cambia contenido HTML",
            "fetch('https://api.datos.com').then(r => r.json()) - hace peticiones HTTP",
        ],
        "difficulty": "JavaScript es relativamente facil de empezar, pero tiene conceptos complejos como el event loop, closures y async/await que requieren practica.",
        "languages_used_for": ["web frontend (React, Vue, Angular)", "web backend (Node.js, Express)", "apps de escritorio (Electron)", "apps moviles (React Native)"],
    },
    "html": {
        "what": "HTML (HyperText Markup Language) es el lenguaje de marcado que define la estructura y el contenido de las paginas web.",
        "how": "HTML usa etiquetas como <div>, <p>, <h1> para crear una estructura jerarquica. El navegador lee estas etiquetas y renderiza el contenido visualmente.",
        "why": "HTML es la base de toda pagina web. Sin HTML no habria contenido en internet. Es el esqueleto sobre el que se aplica CSS (diseño) y JavaScript (logica).",
        "purpose": "HTML sirve para estructurar contenido web: textos, imagenes, videos, formularios, enlaces y mas.",
        "examples": [
            "<h1>Mi Titulo</h1> - titulo principal",
            "<p>Texto parrafo</p> - parrafo de texto",
            "<a href='https://google.com'>Ir a Google</a> - enlace",
        ],
        "difficulty": "HTML es el lenguaje mas facil de aprender en web. No logica, solo estructura.",
    },
    "css": {
        "what": "CSS (Cascading Style Sheets) es el lenguaje que controla la apariencia visual de las paginas web: colores, fuentes, espaciado, layout y animaciones.",
        "how": "CSS se aplica a elementos HTML usando selectores. El navegador combina todas las reglas CSS y las aplica al DOM para crear el diseño visual final.",
        "why": "Sin CSS, las paginas web serian solo texto negro sobre fondo blanco. CSS permite crear diseños atractivos, responsivos y modernos.",
        "purpose": "CSS sirve para dar estilo a las paginas web: colores, tipografia, layouts con Flexbox/Grid, animaciones, y diseno responsivo para movil.",
        "examples": [
            "body { background: #000; color: white; } - fondo negro, texto blanco",
            ".boton { border-radius: 8px; padding: 10px; } - estilos de boton",
            "@media (max-width: 600px) { .nav { display: none; } } - ocultar nav en movil",
        ],
        "difficulty": "CSS es facil de empezar pero dificil de dominar. Los layouts responsivos y las animaciones avanzadas requieren practica.",
    },
    "flask": {
        "what": "Flask es un microframework web para Python. Permite crear aplicaciones web y APIs de forma ligera y flexible.",
        "how": "Flask recibe peticiones HTTP, las enruta a funciones Python (views), y retorna respuestas (HTML, JSON, etc). Usa Werkzeug para HTTP y Jinja2 para templates.",
        "why": "Flask es ideal para aprender web con Python porque es simple, no impone estructura, y te da libertad total de elegir tus herramientas.",
        "purpose": "Flask sirve para crear APIs REST, paginas web, dashboards, microservicios, y prototipos rapidos.",
        "examples": [
            "@app.route('/') def home(): return 'Hola' - ruta basica",
            "@app.route('/api', methods=['POST']) - endpoint POST",
            "app.run(debug=True) - inicia el servidor",
        ],
        "difficulty": "Flask es facil de aprender si ya sabes Python basico. La curva de aprendizaje es suave.",
    },
    "react": {
        "what": "React es una libreria JavaScript de Meta (Facebook) para construir interfaces de usuario con componentes reutilizables.",
        "how": "React usa un Virtual DOM que compara el estado anterior con el nuevo y solo actualiza lo que cambio en el DOM real, haciendolo muy eficiente.",
        "why": "React facilita crear UIs complejas dividiendolas en componentes independientes. Tiene un ecosistema enorme: Next.js, React Native, etc.",
        "purpose": "React sirve para crear interfaces de usuario interactivas: SPAs, dashboards, apps moviles (React Native), y sitios web (Next.js).",
        "examples": [
            "function App() { return <h1>Hola</h1> } - componente basico",
            "const [count, setCount] = useState(0) - estado local",
            "<App /> - renderizar componente",
        ],
        "difficulty": "React requiere saber JavaScript bien. Los conceptos de JSX, hooks y estado pueden ser confusos al principio.",
    },
    "git": {
        "what": "Git es un sistema de control de versiones distribuido creado por Linus Torvalds en 2005. Registra cambios en archivos a lo largo del tiempo.",
        "how": "Git guarda snapshots del codigo en un repositorio local. Puedes crear ramas, hacer commits, y sincronizar con repositorios remotos como GitHub.",
        "why": "Git es esencial para trabajar en equipo sin pisarse el codigo. Permite revertir cambios, comparar versiones, y colaborar de forma segura.",
        "purpose": "Git sirve para versionar codigo, colaborar en equipo, mantener historial de cambios, y integrar con GitHub/GitLab.",
        "examples": [
            "git init - crea un repositorio nuevo",
            "git add . && git commit -m 'mensaje' - guarda cambios",
            "git push origin main - sube al servidor",
        ],
        "difficulty": "Git basico es facil. Los conflictos de merge y el rebasing son lo mas complicado.",
    },
    "sql": {
        "what": "SQL (Structured Query Language) es el lenguaje estandar para gestionar y consultar bases de datos relacionales.",
        "how": "SQL envia declaraciones a la base de datos: CREATE para tablas, INSERT para datos, SELECT para consultar, UPDATE para modificar, DELETE para borrar.",
        "why": "SQL es la forma estandar de interactuar con bases de datos. Casi toda informacion de internet esta guardada en bases de datos consultadas con SQL.",
        "purpose": "SQL sirve para crear, consultar, modificar y eliminar datos en bases de datos como MySQL, PostgreSQL, SQLite, SQL Server.",
        "examples": [
            "SELECT * FROM usuarios WHERE edad > 18 - buscar mayores de 18",
            "INSERT INTO usuarios (nombre, email) VALUES ('Ana', 'ana@mail.com') - agregar registro",
            "UPDATE usuarios SET nombre = 'Ana M.' WHERE id = 1 - modificar dato",
        ],
        "difficulty": "SQL basico es muy facil. Las consultas complejas con JOINs, subconsultas y optimizacion requieren mas practica.",
    },
    "linux": {
        "what": "Linux es un sistema operativo open source basado en Unix, creado por Linus Torvalds en 1991. Es la base de la mayoria de servidores del mundo.",
        "how": "Linux usa un kernel que gestiona el hardware. Las distribuciones (Ubuntu, Fedora, etc.) empaquetan el kernel con herramientas como el shell, gestor de paquetes, y entorno de escritorio.",
        "why": "Linux es gratuito, seguro, estable, y personalizable. Es el SO preferido para servidores, supercomputadoras, y desarrolladores.",
        "purpose": "Linux sirve para servidores web, desarrollo de software, ciencia de datos, IoT, y como sistema de escritorio alternativo.",
        "examples": [
            "ls - listar archivos",
            "cd /home - cambiar directorio",
            "sudo apt install python3 - instalar paquete",
        ],
        "difficulty": "Linux basico es accesible. La linea de comandos puede intimidar al principio pero es muy poderosa.",
    },
    "inteligencia artificial": {
        "what": "La Inteligencia Artificial es la disciplina de la computacion que crea sistemas capaces de realizar tareas que normalmente requieren inteligencia humana.",
        "how": "La IA usa algoritmos de machine learning que aprenden patrones en datos. Las redes neuronales artificiales simulan el cerebro humano con capas de neuronas que procesan informacion.",
        "why": "La IA existe para automatizar tareas complejas, encontrar patrones en grandes volumes de datos, y crear sistemas que se adapten y mejoren solos.",
        "purpose": "La IA sirve para asistentes virtuales (como yo!), recomendaciones (Netflix, Spotify), coches autonomos, diagnostico medico, traduccion, y mucho mas.",
        "examples": [
            "ChatGPT y asistentes de voz - procesamiento de lenguaje natural",
            "Reconocimiento facial en fotos - vision por computadora",
            "Autocompletar en Google - prediccion de texto",
        ],
        "difficulty": "La IA requiere bases solidas de programacion, matematicas y estadistica. Es un campo amplio pero muy interesante.",
    },
    "machine learning": {
        "what": "Machine Learning es una rama de la IA donde los sistemas aprenden automaticamente de datos sin ser programados explicitamente para cada tarea.",
        "how": "ML usa algoritmos que analizan datos, encuentran patrones, y crean modelos que pueden hacer predicciones o decisiones sobre datos nuevos.",
        "why": "ML permite resolver problemas donde programar reglas explicitas es imposible o muy complejo, como reconocer imagenes o entender texto.",
        "purpose": "ML sirve para clasificacion de datos, prediccion, recomendaciones, deteccion de fraude, procesamiento de lenguaje natural, y mas.",
        "examples": [
            "Spotify te recomienda musica basado en tu historial",
            "Gmail detecta spam analizando patrones de emails",
            "Netflix predice que peliculas te gustarian",
        ],
        "difficulty": "ML requiere saber programacion (Python), matematicas (algebra, estadistica), y conceptos de algoritmos. No es facil pero es muy gratificante.",
    },
    "deep learning": {
        "what": "Deep Learning es un subconjunto del Machine Learning que usa redes neuronales artificiales con muchas capas (profundas) para aprender representaciones jerarquicas de los datos.",
        "how": "Las redes profundas tienen multiples capas ocultas. Cada capa aprende caracteristicas mas abstractas: bordes -> formas -> objetos -> escenas.",
        "why": "Deep Learning ha revolucionado la IA porque puede aprender automaticamente caracteristicas complejas de datos no estructurados como imagenes, audio y texto.",
        "purpose": "Deep Learning sirve para reconocimiento de imagenes, procesamiento de lenguaje natural, coches autonomos, generacion de texto/imagenes, y mas.",
        "examples": [
            "ChatGPT usa transformers (redes profundas) para generar texto",
            "Los filtros de Instagram usan redes neuronales para detectar caras",
            "Tesla usa deep learning para que los coches 'vean' la carretera",
        ],
        "difficulty": "Deep Learning es de los campos mas complejos. Requiere saber programacion, matematicas avanzadas, y tener conocimiento de arquitecturas de redes.",
    },
    "nodejs": {
        "what": "Node.js es un entorno de ejecucion de JavaScript fuera del navegador. Permite crear servidores, APIs y herramientas de linea de comandos en JavaScript.",
        "how": "Node.js usa el motor V8 de Google Chrome para ejecutar JavaScript en el servidor. Usa un event loop no-bloqueante que lo hace muy eficiente para operaciones de E/S.",
        "why": "Node.js permite usar un solo lenguaje (JavaScript) tanto para frontend como backend, reduciendo la complejidad del desarrollo fullstack.",
        "purpose": "Node.js sirve para crear servidores web, APIs REST/GraphQL, herramientas CLI, automatizacion (Gulp, Webpack), y aplicaciones en tiempo real (chats, juegos).",
        "examples": [
            "const http = require('http'); - servidor basico",
            "express.get('/api', (req, res) => res.json({ok: true})) - API con Express",
            "npm install paquete - instalar dependencias",
        ],
        "difficulty": "Node.js es accesible si sabes JavaScript. Los conceptos de async/await y event loop son los mas complicados.",
    },
    "github": {
        "what": "GitHub es la plataforma de hosting de repositorios Git mas grande del mundo. Ofrece herramientas de colaboracion, CI/CD, y gestión de proyectos.",
        "how": "GitHub almacena repositorios Git en la nube. Los desarrolladores suben (push) y descargan (pull) codigo, crean ramas (branches), y fusionan cambios (merge).",
        "why": "GitHub es esencial para colaborar en equipo. Permite revisar codigo (pull requests), reportar errores (issues), y automatizar pruebas (Actions).",
        "purpose": "GitHub sirve para hospedar codigo, colaborar en proyectos, documentar con READMEs, y automatizar flujos de trabajo de desarrollo.",
        "examples": [
            "git push origin main - sube codigo a GitHub",
            "Pull Request - proponer cambios para revision",
            "GitHub Actions - CI/CD automatico",
        ],
        "difficulty": "GitHub basico es facil (push, pull, issues). Los flujos de trabajo avanzados (rebasing, cherry-pick, Actions) requieren mas practica.",
    },
    "docker": {
        "what": "Docker es una plataforma de contenedorizacion que empaleta aplicaciones con todas sus dependencias en containers portables.",
        "how": "Docker crea containers aislados que incluyen la app, librerias, y configuracion. Los containers corren igual en cualquier maquina con Docker instalado.",
        "why": "Docker resuelve el problema de 'en mi maquina funciona'. Asegura que la app se ejecute igual en desarrollo, testing y produccion.",
        "purpose": "Docker sirve para empaquetar aplicaciones, crear ambientes de desarrollo reproducibles, y desplegar en la nube de forma consistente.",
        "examples": [
            "docker build -t mi-app . - crear imagen Docker",
            "docker run -p 5000:5000 mi-app - ejecutar container",
            "docker-compose up - levantar multiples servicios",
        ],
        "difficulty": "Docker basico es entendible. El networking, volumes y orquestacion (Kubernetes) son mas complejos.",
    },
    "kubernetes": {
        "what": "Kubernetes (K8s) es una plataforma open source de orquestacion de containers que automatiza el despliegue, escalado y gestion de aplicaciones.",
        "how": "Kubernetes gestiona clusters de machines (nodos). Organiza containers en Pods, los distribuye, los balancea carga, y los reinicia si fallan.",
        "why": "Kubernetes permite gestionar miles de containers en produccion de forma automatica. Es el estandar de la industria para aplicaciones cloud-native.",
        "purpose": "Kubernetes sirve para desplegar, escalar y gestionar aplicaciones containerizadas en produccion de forma automatica y confiable.",
        "examples": [
            "kubectl apply -f deployment.yaml - desplegar app",
            "kubectl scale --replicas=5 deployment/mi-app - escalar a 5 instancias",
            "kubectl get pods - ver pods corriendo",
        ],
        "difficulty": "Kubernetes es complejo. Requiere saber Docker bien, y conceptos de redes, storage, y sistemas distribuidos.",
    },
    "typescript": {
        "what": "TypeScript es un superconjunto de JavaScript que agrega tipos estaticos. Fue creado por Microsoft para hacer el JS mas robusto.",
        "how": "TypeScript agrega un sistema de tipos sobre JavaScript. El compilador TS verifica tipos en tiempo de desarrollo y genera JavaScript vanilla que ejecuta el navegador.",
        "why": "TypeScript previene errores comunes de JavaScript (como llamar una funcion con el tipo de dato incorrecto) y hace el codigo mas mantenible.",
        "purpose": "TypeScript sirve para escribir JavaScript mas seguro y escalable, especialmente en proyectos grandes y en equipo.",
        "examples": [
            "let nombre: string = 'Ana' - tipo explicito",
            "function sumar(a: number, b: number): number { return a + b } - tipos en funciones",
            "interface Usuario { id: number; nombre: string } - definir estructura",
        ],
        "difficulty": "TypeScript es facil si ya sabes JavaScript. El sistema de tipos es lo mas complejo pero también lo mas util.",
    },
    "machine learning": {
        "what": "Machine Learning es una rama de la IA donde los sistemas aprenden automaticamente de datos sin ser programados explicitamente.",
        "how": "ML usa algoritmos como redes neuronales, arboles de decision, y regresion para encontrar patrones en datos y hacer predicciones.",
        "why": "ML permite resolver problemas complejos donde las reglas son dificiles de definir explicitamente.",
        "purpose": "ML sirve para clasificacion, regresion, clustering, recomendacion, y procesamiento de datos masivos.",
        "examples": [
            "Prediccion de precios de casas con regresion lineal",
            "Clasificacion de emails como spam/no-spam",
            "Recomendaciones de Netflix basadas en historial",
        ],
        "difficulty": "ML requiere saber Python, estadistica, y algebra lineal. Es un campo fascinante pero demandante.",
    },
    "react": {
        "what": "React es una libreria JavaScript para construir interfaces de usuario, desarrollada por Meta.",
        "how": "React usa componentes y un Virtual DOM para actualizar eficientemente la interfaz solo cuando es necesario.",
        "why": "React facilita crear UIs complejas de forma declarativa y componiendo piezas reutilizables.",
        "purpose": "React sirve para crear interfaces web y moviles (React Native).",
        "examples": [
            "function Boton() { return <button>Haz click</button> }",
            "const [contador, setContador] = useState(0)",
        ],
        "difficulty": "Requiere saber JavaScript bien. JSX y hooks pueden confundir al principio.",
    },
    "api": {
        "what": "Una API (Application Programming Interface) es un contrato que define como dos software se comunican entre si.",
        "how": "Una API define endpoints (URLs), metodos HTTP (GET, POST, PUT, DELETE), y formatos de datos (JSON, XML). El cliente envia peticiones y recibe respuestas.",
        "why": "Las APIs permiten que diferentes sistemas se conecten: una app movil habla con un servidor, un sitio web consulta una base de datos externa, etc.",
        "purpose": "Las APIs sirven para conectar servicios, exponer funcionalidades, e integrar sistemas diferentes.",
        "examples": [
            "GET /api/usuarios - obtener lista de usuarios",
            "POST /api/usuarios - crear un usuario nuevo",
            "DELETE /api/usuarios/1 - borrar usuario con id 1",
        ],
        "difficulty": "APIs basicas son faciles. Las APIs complejas con autenticacion, paginacion y versionado requieren mas experiencia.",
    },
    "react": {
        "what": "React es una libreria JavaScript de Meta para construir interfaces de usuario con componentes reutilizables.",
        "how": "React usa un Virtual DOM que compara el estado anterior con el nuevo y solo actualiza lo que cambio en el DOM real, haciendolo muy eficiente.",
        "why": "React facilita crear UIs complejas dividiendolas en componentes independientes. Tiene un ecosistema enorme: Next.js, React Native, etc.",
        "purpose": "React sirve para crear interfaces de usuario interactivas: SPAs, dashboards, apps moviles (React Native), y sitios web (Next.js).",
        "examples": [
            "function App() { return <h1>Hola</h1> } - componente basico",
            "const [count, setCount] = useState(0) - estado local",
            "<App /> - renderizar componente",
        ],
        "difficulty": "React requiere saber JavaScript bien. Los conceptos de JSX, hooks y estado pueden ser confusos al principio.",
    },
    "vue": {
        "what": "Vue.js es un framework JavaScript progresivo para construir interfaces de usuario. Creado por Evan You en 2014.",
        "how": "Vue usa un sistema de reactividad basado en proxies. Los componentes tienen template (HTML), script (JS) y style (CSS) en un solo archivo .vue.",
        "why": "Vue es facil de aprender, muy flexible, y su curva de aprendizaje es suave comparado con React o Angular.",
        "purpose": "Vue sirve para crear interfaces web interactivas, SPAs, y componentes reutilizables.",
        "examples": [
            "<template><h1>{{ mensaje }}</h1></template> - template con datos",
            "const app = Vue.createApp({ data() { return { mensaje: 'Hola' } } })",
            "v-if, v-for, v-model - directivas de Vue",
        ],
        "difficulty": "Vue es de los frameworks mas faciles de aprender. Su documentacion es excelente.",
    },
    "angular": {
        "what": "Angular es un framework web completo de Google para crear aplicaciones de una sola pagina (SPA) con TypeScript.",
        "how": "Angular usa TypeScript, inyeccion de dependencias, RxJS para observables, y un sistema de modulos. Tiene CLI propio para generar codigo.",
        "why": "Angular es ideal para proyectos grandes y empresariales porque opiniona la arquitectura y trae todo incluido.",
        "purpose": "Angular sirve para crear aplicaciones web empresariales, dashboards complejos, y SPAs robustas.",
        "examples": [
            "@Component({ selector: 'app-hola', template: '<h1>Hola</h1>' }) - componente",
            "@Injectable() - servicio inyectable",
            "ng generate component nombre - generar componente con CLI",
        ],
        "difficulty": "Angular es el mas dificil de los 3 grandes (React, Vue, Angular). Requiere saber TypeScript y tener experiencia.",
    },
    "nextjs": {
        "what": "Next.js es un framework de React creado por Vercel que agrega renderizado del lado del servidor (SSR), generacion estatica (SSG), y mas.",
        "how": "Next.js puede renderizar paginas en el servidor (SSR) o generarlas estaticamente (SSG). Soporta rutas dinamicas, API routes, y optimizaciones automaticas.",
        "why": "Next.js resuelve las limitaciones de React puro: SEO, velocidad de carga inicial, y routing basado en archivos.",
        "purpose": "Next.js sirve para crear sitios web rapidos, optimizados para SEO, y aplicaciones web completas con backend incluido.",
        "examples": [
            "pages/index.js - pagina principal",
            "pages/about.js - ruta /about",
            "getServerSideProps() - SSR",
        ],
        "difficulty": "Next.js es accesible si ya sabes React. SSR y SSG pueden confundir al principio.",
    },
    "mongo": {
        "what": "MongoDB es una base de datos NoSQL basada en documentos. Guarda datos en formato BSON (JSON binario) en lugar de tablas.",
        "how": "MongoDB organiza datos en colecciones (como tablas) y documentos (como filas). Usa un lenguaje de consultas flexible y escalabilidad horizontal.",
        "why": "MongoDB es ideal para datos que cambian frecuentemente, estructuras flexibles, y aplicaciones que necesitan escalar horizontalmente.",
        "purpose": "MongoDB sirve para almacenar datos de aplicaciones web, analiticos, contenido, y datos en tiempo real.",
        "examples": [
            "db.usuarios.insertOne({nombre: 'Ana', edad: 25}) - insertar documento",
            "db.usuarios.find({edad: {$gt: 18}}) - buscar mayores de 18",
            "db.usuarios.updateOne({nombre: 'Ana'}, {$set: {edad: 26}}) - actualizar",
        ],
        "difficulty": "MongoDB es facil de empezar si vienes de JSON. Las consultas complejas y la modelizacion de datos requieren practica.",
    },
    "redis": {
        "what": "Redis es una base de datos en memoria ultra-rapida. Se usa como cache, cola de mensajes, y almacenamiento de sesiones.",
        "how": "Redis guarda todo en la memoria RAM, lo que lo hace extremadamente rapido. Soporta estructuras como strings, hashes, listas, sets y sorted sets.",
        "why": "Redis es ideal para cacheo, sesiones, colas de tareas, y cualquier cosa que necesite velocidad extrema.",
        "purpose": "Redis sirve para cache de consultas, sesiones de usuario, colas de mensajes, contadores, y rate limiting.",
        "examples": [
            "SET nombre 'Ana' - guardar string",
            "GET nombre - obtener valor",
            "EXPIRE nombre 3600 - expirar en 1 hora",
        ],
        "difficulty": "Redis basico es muy facil. Las estructuras de datos y los patrones de uso avanzados requieren mas estudio.",
    },
    "aws": {
        "what": "Amazon Web Services (AWS) es la plataforma de cloud computing mas grande del mundo. Ofrece mas de 200 servicios de servidores, almacenamiento, bases de datos, IA y mas.",
        "how": "AWS funciona bajo modelos IaaS, PaaS y SaaS. Puedes alquilar servidores virtuales (EC2), almacenar archivos (S3), usar bases de datos (RDS), y mucho mas.",
        "why": "AWS permite escalar aplicaciones sin comprar hardware, pagar solo por lo que usas, y desplegar globalmente.",
        "purpose": "AWS sirve para hospedar aplicaciones web, almacenar datos, crear APIs, entrenar modelos de IA, y construir infraestructura completa en la nube.",
        "examples": [
            "EC2 - servidores virtuales",
            "S3 - almacenamiento de archivos",
            "Lambda - funcion serverless",
        ],
        "difficulty": "AWS basico es entendible. La cantidad de servicios y configuraciones puede ser abrumadora.",
    },
    "terraform": {
        "what": "Terraform es una herramienta de HashiCorp para infraestructura como codigo (IaC). Permite crear y gestionar infraestructura en la nube con archivos de configuracion.",
        "how": "Terraform usa archivos .hcl para describir la infraestructura deseada. Compara el estado actual con el deseado y hace cambios automaticamente.",
        "why": "Terraform permite versionar la infraestructura, reproducir ambientes, y automatizar despliegues complejos.",
        "purpose": "Terraform sirve para crear y gestionar servidores, redes, bases de datos, y cualquier recurso de nube de forma declarativa.",
        "examples": [
            "resource 'aws_instance' 'web' { ami = '...' } - crear instancia EC2",
            "terraform plan - ver cambios que se harian",
            "terraform apply - aplicar cambios",
        ],
        "difficulty": "Terraform requiere saber云计算 basico y un proveedor (AWS, Azure, GCP). La sintaxis HCL es sencilla.",
    },
    "flutter": {
        "what": "Flutter es un SDK de Google para crear aplicaciones moviles nativas para Android e iOS con un solo codigo fuente. Usa el lenguaje Dart.",
        "how": "Flutter compila a codigo nativo ARM. Usa widgets personalizables que se renderizan directamente en el canvas, sin depender de widgets nativos del SO.",
        "why": "Flutter permite crear apps nativas rapidas y bonitas con un solo equipo de desarrollo, reduciendo costos y tiempo.",
        "purpose": "Flutter sirve para crear apps moviles, apps de escritorio (Flutter Desktop), y hasta apps web.",
        "examples": [
            "MaterialApp(home: Scaffold(body: Text('Hola'))) - app basica",
            "ElevatedButton(onPressed: () {}, child: Text('Click')) - boton",
            "flutter run - ejecutar en emulador",
        ],
        "difficulty": "Flutter es accesible si sabes un lenguaje orientado a objetos. Dart es facil de aprender.",
    },
    "kotlin": {
        "what": "Kotlin es un lenguaje de programacion moderno que corre en la JVM. Es el lenguaje oficial para desarrollo Android.",
        "how": "Kotlin compila a bytecode de JVM o a JavaScript. Es 100% interoperable con Java y tiene features modernas como null safety, coroutines y extension functions.",
        "why": "Kotlin es mas conciso y seguro que Java, y es el lenguaje recomendado por Google para Android.",
        "purpose": "Kotlin sirve para desarrollo Android, backend con Ktor/Spring, y multiplataforma con Kotlin Multiplatform.",
        "examples": [
            "val nombre: String = 'Ana' - variable inmutable",
            "fun saludar(nombre: String) = 'Hola $nombre' - funcion",
            "data class Usuario(val id: Int, val nombre: String) - data class",
        ],
        "difficulty": "Kotlin es facil si vienes de Java o un lenguaje moderno. Null safety puede confundir al principio.",
    },
    "swift": {
        "what": "Swift es un lenguaje de programacion de Apple para crear apps de iOS, macOS, watchOS y tvOS.",
        "how": "Swift compila a codigo nativo optimizado. Tiene un sistema de tipos robusto, optionals para null safety, y es mucho mas rapido que Objective-C.",
        "why": "Swift es el lenguaje oficial de Apple para desarrollo de apps. Es mas seguro, rapido y moderno que Objective-C.",
        "purpose": "Swift sirve para crear apps de iPhone, iPad, Mac, Apple Watch, y Apple TV.",
        "examples": [
            "let nombre = 'Ana' - constante",
            "func saludar(nombre: String) -> String { return 'Hola \\(nombre)' }",
            "struct Usuario { let id: Int; let nombre: String }",
        ],
        "difficulty": "Swift es accesible. Si sabes un lenguaje moderno,Swift es facil de aprender.",
    },
    "rust": {
        "what": "Rust es un lenguaje de programacion de sistemas enfocado en seguridad, velocidad y concurrencia. Creado por Mozilla.",
        "how": "Rust usa un sistema de ownership y borrowing que garantiza seguridad de memoria sin garbage collector. Compila a codigo nativo ultra-rapido.",
        "why": "Rust elimina clases enteras de bugs (data races, null pointers) en tiempo de compilacion sin sacrificar rendimiento.",
        "purpose": "Rust sirve para sistemas operativos, navegadores (Firefox), herramientas CLI, WebAssembly, y software de alto rendimiento.",
        "examples": [
            "let mut x = 5; x += 1; - variable mutable",
            "fn sumar(a: i32, b: i32) -> i32 { a + b } - funcion",
            "match opcion { Some(v) => v, None => 0 } - pattern matching",
        ],
        "difficulty": "Rust es dificil. El sistema de ownership es unico y confunde al principio, pero es muy poderoso.",
    },
    "go": {
        "what": "Go (Golang) es un lenguaje de programacion de Google disenado para simplicidad, eficiencia y concurrencia.",
        "how": "Go compila rapidamente a codigo nativo. Tiene goroutines para concurrencia facil, un garbage collector, y un ecosistema de herramientas excellent.",
        "why": "Go es simple, rapido, y ideal para servicios de red, microservicios, y herramientas de DevOps.",
        "purpose": "Go sirve para APIs, microservicios, herramientas CLI (Docker, Kubernetes estan hechos en Go), y sistemas distribuidos.",
        "examples": [
            "func main() { fmt.Println('Hola') } - programa basico",
            "go func() { fmt.Println('async') }() - goroutine",
            "http.HandleFunc('/', handler) - servidor web",
        ],
        "difficulty": "Go es intencionalmente simple. Es uno de los lenguajes mas faciles de aprender.",
    },
    "c++": {
        "what": "C++ es un lenguaje de programacion de proposito general, compilado, orientado a objetos y de alto rendimiento. Extiende C con clases, templates y STL.",
        "how": "C++ compila directamente a codigo de maquina. Ofrece control manual de memoria (new/delete, smart pointers), plantillas para genericos, y la STL (contenedores, algoritmos, iteradores).",
        "why": "C++ combina abstracciones de alto nivel con control de bajo nivel. Es el estandar en juegos, sistemas embebidos, trading de alta frecuencia, y software critico de rendimiento.",
        "purpose": "C++ sirve para motores de juegos (Unreal Engine), sistemas operativos, navegadores, bases de datos, simulaciones, y cualquier software donde el rendimiento es critico.",
        "examples": [
            "std::vector<int> v = {1,2,3}; - vector dinamico",
            "std::unique_ptr<int> p = std::make_unique<int>(42); - smart pointer",
            "template <typename T> T max(T a, T b) { return a > b ? a : b; } - template",
        ],
        "difficulty": "C++ es dificil. Requiere entender punteros, memoria, templates, y la STL. Curva de aprendizaje empinada pero muy gratificante.",
    },
    "sass": {
        "what": "SASS (Syntactically Awesome Stylesheets) es un preprocesador de CSS que agrega features como variables, nesting, mixins y funciones.",
        "how": "SASS compila a CSS vanilla. Agrega variables ($color), anidamiento (.nav { .item {} }), mixins (@mixin), y archivos parciales.",
        "why": "SASS hace el CSS mas mantenible, reutilizable y organizado, especialmente en proyectos grandes.",
        "purpose": "SASS sirve para escribir CSS mas organizado y potente en proyectos web grandes.",
        "examples": [
            "$primary: #57a6ff; - variable",
            ".nav { .item { color: $primary; } } - nesting",
            "@mixin flex-center { display: flex; align-items: center; justify-content: center; } - mixin",
        ],
        "difficulty": "SASS es facil si ya sabes CSS. Las variables y mixins son intuitivos.",
    },
    "webpack": {
        "what": "Webpack es un bundler de JavaScript que empaleta todos los assets de una aplicacion (JS, CSS, imagenes) en archivos optimizados.",
        "how": "Webpack construye un grafo de dependencias a partir de un archivo de entrada y lo compila en bundles optimizados con loaders y plugins.",
        "why": "Webpack permite usar modulos ES6, TypeScript, SASS, y otros lenguajes que el navegador no entiende directamente.",
        "purpose": "Webpack sirve para compilar, optimizar y empaquetar codigo frontend para produccion.",
        "examples": [
            "entry: './src/index.js' - archivo de entrada",
            "output: { filename: 'bundle.js' } - archivo de salida",
            "loaders: [babel-loader, css-loader] - transformar archivos",
        ],
        "difficulty": "Webpack basico es entendible. La configuracion avanzada (loaders, plugins, code splitting) es compleja.",
    },
    "babel": {
        "what": "Babel es un compilador de JavaScript que transforma codigo moderno (ES6+) en versiones compatibles con navegadores antiguos.",
        "how": "Babel usa un sistema de plugins y presets para transformar el codigo. Puede convertir JSX, optional chaining, y otras features nuevas.",
        "why": "Babel permite usar las ultimas features de JavaScript sin preocuparte por la compatibilidad con navegadores viejos.",
        "purpose": "Babel sirve para transpilar JavaScript moderno, JSX de React, y TypeScript a JS compatible.",
        "examples": [
            "npx babel src --out-dir lib - compilar carpeta",
            "babel.config.json: { presets: ['@babel/preset-env'] } - configuracion",
            "JSX -> React.createElement() - transformacion",
        ],
        "difficulty": "Babel basico es facil. Configurar plugins y presets para proyectos complejos requiere mas experiencia.",
    },
    "npm": {
        "what": "npm (Node Package Manager) es el gestor de paquetes oficial de Node.js. Tiene el repositorio de paquetes open source mas grande del mundo.",
        "how": "npm descarga paquetes de registry.npmjs.com, los instala en node_modules/, y gestiona dependencias en package.json.",
        "why": "npm permite reutilizar codigo de otros desarrolladores, gestionar versiones, y automatizar tareas de desarrollo.",
        "purpose": "npm sirve para instalar, actualizar y gestionar paquetes de JavaScript y herramientas de desarrollo.",
        "examples": [
            "npm init - crear package.json",
            "npm install express - instalar paquete",
            "npm run dev - ejecutar script",
        ],
        "difficulty": "npm basico es muy facil. El manejo de dependencias, versiones y conflictos puede ser complejo.",
    },
    "typescript": {
        "what": "TypeScript es un superconjunto de JavaScript que agrega tipos estaticos. Creado por Microsoft.",
        "how": "TypeScript agrega un sistema de tipos sobre JavaScript. El compilador verifica tipos en tiempo de desarrollo y genera JavaScript vanilla.",
        "why": "TypeScript previene errores comunes de JavaScript y hace el codigo mas mantenible, especialmente en proyectos grandes.",
        "purpose": "TypeScript sirve para escribir JavaScript mas seguro y escalable, especialmente en proyectos grandes y en equipo.",
        "examples": [
            "let nombre: string = 'Ana' - tipo explicito",
            "function sumar(a: number, b: number): number { return a + b }",
            "interface Usuario { id: number; nombre: string }",
        ],
        "difficulty": "TypeScript es facil si ya sabes JavaScript. El sistema de tipos es lo mas complejo pero tambien lo mas util.",
    },
    "php": {
        "what": "PHP es un lenguaje de script del lado del servidor disenado para el desarrollo web. Es el lenguaje de WordPress, Facebook (HHVM) y millones de sitios.",
        "how": "PHP se ejecuta en el servidor, genera HTML, y lo envia al navegador. Soporta multiples bases de datos y tiene un ecosistema enorme.",
        "why": "PHP es facil de aprender, tiene hosting barato, y powers el 77% de la web con WordPress alone.",
        "purpose": "PHP sirve para crear sitios web dinamicos, CMS (WordPress), APIs, y aplicaciones web completas (Laravel).",
        "examples": [
            "<?php echo 'Hola Mundo'; ?> - imprimir texto",
            "$nombre = 'Ana'; - variable",
            "echo json_encode($datos); - output JSON",
        ],
        "difficulty": "PHP es facil de empezar. La calidad del codigo puede variar mucho dependiendo del framework.",
    },
    "ruby": {
        "what": "Ruby es un lenguaje de programacion orientado a objetos creado por Yukihiro Matsumoto. Es conocido por su elegancia y por Ruby on Rails.",
        "how": "Ruby es interpretado, tiene tipado dinamico, y es todo un objeto. Ruby on Rails es un framework web full-stack que sigue convenciones sobre configuracion.",
        "why": "Ruby prioriza la felicidad del programador. Ruby on Rails acelera enormemente el desarrollo web.",
        "purpose": "Ruby sirve para desarrollo web (Rails), scripting, automatizacion, y prototipos rapidos.",
        "examples": [
            "nombre = 'Ana' - variable",
            "def saludar(nombre); puts \"Hola #{nombre}\"; end - metodo",
            "User.where(age: 18).order(:name) - consulta Rails",
        ],
        "difficulty": "Ruby es facil y agradable de usar. Rails tiene una curva de aprendizaje suave pero mucho que memorizar.",
    },
    "django": {
        "what": "Django es un framework web completo para Python que sigue el patron MVT (Model-View-Template).",
        "how": "Django trae ORM, admin panel, autenticacion, routing, templates, y seguridad integrada. Sigue el principio de 'baterias incluidas'.",
        "why": "Django es ideal para proyectos web complejos porque trae todo lo necesario listo para usar.",
        "purpose": "Django sirve para crear APIs REST, dashboards, CMS, e-commerce, y cualquier tipo de aplicacion web.",
        "examples": [
            "python manage.py startapp miapp - crear app",
            "models.py: class Usuario(models.Model): nombre = models.CharField()",
            "python manage.py runserver - iniciar servidor",
        ],
        "difficulty": "Django es accesible si sabes Python. La cantidad de features puede ser abrumadora al principio.",
    },
    "laravel": {
        "what": "Laravel es un framework web para PHP creado por Taylor Otwell. Es el framework PHP mas popular y elegante.",
        "how": "Laravel usa el patron MVC, tiene Blade para templates, Eloquent ORM, migraciones, y artisan CLI. Sigue la filosofia de convention over configuration.",
        "why": "Laravel hace PHP moderno y productivo. Tiene una comunidad enorme y documentacion excelente.",
        "purpose": "Laravel sirve para crear APIs REST, aplicaciones web completas, e-commerce, y dashboards.",
        "examples": [
            "Route::get('/users', [UserController::class, 'index']) - ruta",
            "User::where('age', '>', 18)->get() - consulta Eloquent",
            "php artisan make:model Usuario - generar modelo",
        ],
        "difficulty": "Laravel es accesible si sabes PHP. Blade y Eloquent son intuitivos.",
    },
}

REASONING_PATTERNS = [
    (r"^que\s+es\s+(.+?)[\?\s]*$", "what_is"),
    (r"^que\s+es\s+un\s+(.+?)[\?\s]*$", "what_is"),
    (r"^que\s+es\s+una\s+(.+?)[\?\s]*$", "what_is"),
    (r"^que\s+es\s+el\s+(.+?)[\?\s]*$", "what_is"),
    (r"^que\s+es\s+la\s+(.+?)[\?\s]*$", "what_is"),
    (r"^que\s+es\s+los\s+(.+?)[\?\s]*$", "what_is"),
    (r"^que\s+es\s+las\s+(.+?)[\?\s]*$", "what_is"),
    (r"^como\s+funciona\s+(.+?)[\?\s]*$", "how_works"),
    (r"^como\s+se\s+usa\s+(.+?)[\?\s]*$", "how_use"),
    (r"^como\s+(?:puedo|puedo)\s+(.+?)[\?\s]*$", "how_to"),
    (r"^por\s+que\s+(.+?)[\?\s]*$", "why"),
    (r"^para\s+que\s+(?:sirve|sirve)\s+(.+?)[\?\s]*$", "purpose"),
    (r"^cuales?\s+son?\s+(?:las?\s+)?ventajas?\s+(?:de|del)\s+(.+?)[\?\s]*$", "pros"),
    (r"^cuales?\s+son?\s+(?:las?\s+)?desventajas?\s+(?:de|del)\s+(.+?)[\?\s]*$", "cons"),
    (r"^(?:dame|pon|mustra)\s+(?:un\s+)?ejemplo\s+(?:de|del)\s+(.+?)[\?\s]*$", "example"),
    (r"^(?:dame|pon|haz)\s+(?:un\s+)?resumen\s+(?:de|sobre|del)\s+(.+?)[\?\s]*$", "summary"),
    (r"^(?:cuales?\s+son?\s+)?(?:las?\s+)?diferencias?\s+entre\s+(.+?)\s+y\s+(.+?)[\?\s]*$", "differences"),
    (r"^que\s+diferencia\s+hay\s+entre\s+(.+?)\s+y\s+(.+?)[\?\s]*$", "differences"),
    (r"^es\s+(.+?)\s+(?:dificil|complicado|complejo|facil|rapido|lento)[\?\s]*$", "difficulty"),
    (r"^(?:que\s+tan\s+)?(?:dificil|complicado|complejo|facil)\s+(?:es\s+)?(?:aprender|entender|usar|hacer)\s+(.+?)[\?\s]*$", "difficulty"),
    (r"^(?:cual|que)\s+lenguaje\s+(?:es\s+)?(?:mejor|ideal|bueno|recomendado)\s+(?:para|para\s+aprender|para\s+hacer)\s+(.+?)[\?\s]*$", "recommend"),
    (r"^(?:como\s+)?(?:puedo|puedo)\s+(.+?)\s+paso\s+a\s+paso[\?\s]*$", "step_by_step"),
]

WHY_RESPONSES = {
    "el cielo es azul": "El cielo es azul por un fenomeno llamado **dispersion de Rayleigh**. La luz del sol viaja en todas las longitudes de onda. Cuando entra en la atmosfera, las moleculas de gas esparcen mas la luz azul (longitud de onda corta) que la luz roja. Por eso vemos el cielo de color azul desde la superficie de la Tierra.",
    "la tierra gira": "La Tierra gira por la conservacion del momento angular del disco protoplanetario original que formo el Sistema Solar hace 4,600 millones de anos. No hay 'freno' significativo en el espacio vacio, asi que sigue girando. Completa una rotacion en 24 horas (un dia) y una orbita alrededor del Sol en 365.25 dias (un ano).",
    "llueve": "La lluvia se forma por el ciclo del agua: el sol calienta el agua de oceanos y rios, que se evapora y sube como vapor. En la atmosfera alta, el vapor se enria y forma nubes de gotas de agua o cristales de hielo. Cuando estas gotas se vuelven pesadas, caen por gravedad como lluvia.",
    "la gravedad existe": "La gravedad es una fuerza fundamental descrita por Newton y mejor explicada por Einstein. Segun la relatividad general, la masa curva el espacio-tiempo a su alrededor, y otros objetos se mueven siguiendo esas curvas. Es la fuerza que nos mantiene en la Tierra y mantiene los planetas en orbita.",
    "el sonido se propaga": "El sonido es una onda mecanica que viaja vibrando las moleculas del medio (aire, agua, solidos). Cuando un objeto vibra, comprime y descomprime el aire a su alrededor, creando ondas de presion que viajan a approx. 343 m/s en el aire a 20 grados C.",
    "las plantas son verdes": "Las plantas son verdes porque contienen clorofila, el pigmento que usan para la fotosintesis. La clorofila absorbe la luz roja y azul del espectro solar, pero refleja la luz verde, que es la que vemos.",
    "internet funciona": "Internet funciona mediante una red global de cables (fibra optica), routers y servidores. Los datos se dividen en paquetes, viajan por la red usando protocolos TCP/IP, y se reensamblan en el destino. Los servidores DNS traducen nombres de dominio a direcciones IP.",
    "los coches funcionan": "Los coches de combustion interna convierten energia quimica (gasolina) en energia mecanica. La mezcla de gasolina y aire se comprime y explode en los cilindros, moviendo los pistones que giran el ciguenal, que transmite la fuerza a las ruedas a traves de la transmision.",
}

DIFFICULTY_MAP = {
    "python": "Python es considerado uno de los lenguajes **mas faciles de aprender**. Su sintaxis es clara y similar al ingles. Con dedicacion, puedes aprender lo basico en 2-4 semanas.",
    "javascript": "JavaScript es **moderadamente facil** de empezar pero tiene conceptos complejos como closures, event loop y async/await. Lo basico se aprende en 2-4 semanas.",
    "java": "Java es **moderadamente dificil** por su verbosidad y conceptos de orientacion a objetos estricta. Requiere mas tiempo que Python para empezar.",
    "c++": "C++ es **dificil**. Tiene punteros, gestion de memoria manual, y una sintaxis compleja. Es poderoso pero requiere mucho estudio.",
    "react": "React es **moderadamente dificil**. Requiere saber JavaScript bien. Los conceptos de JSX, hooks y estado pueden confundir al principio.",
    "flask": "Flask es **facil** de aprender si ya sabes Python. La curva de aprendizaje es suave y la documentacion es excelente.",
    "docker": "Docker basico es **facil**. El networking y orquestacion con Kubernetes son **dificiles**.",
    "kubernetes": "Kubernetes es **dificil**. Requiere saber Docker, redes, y sistemas distribuidos. No es para principiantes.",
    "git": "Git basico es **facil**. Los conflictos de merge y operaciones avanzadas como rebasing son **dificiles**.",
    "sql": "SQL basico es **muy facil**. Las consultas complejas con JOINs y optimizacion son **moderadamente dificiles**.",
    "linux": "Linux basico es **accesible**. La linea de comandos puede intimidar pero es **muy util** una vez que la aprendes.",
    "machine learning": "ML es **dificil**. Requiere programacion, estadistica y algebra lineal. Pero es un campo fascinante.",
    "deep learning": "Deep Learning es **muy dificil**. Especializate despues de dominar ML basico.",
    "html": "HTML es **el mas facil de todos**. Es solo estructura, sin logica. Se aprende en pocos dias.",
    "css": "CSS es **facil de empezar** pero **dificil de dominar**. Los layouts responsivos y animaciones avanzadas requieren practica.",
}


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
                resp += f"*Quieres saber como funciona o para que sirve en especifico?*"
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
                    resp += data.get("how", "No tengo ejemplos especificos de uso.")
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
                return f"**Para que sirve {term.title()}:**\n\n{data.get('purpose', data.get('what', 'No tengo informacion sobre eso.'))}"

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
            result = {
                "title": data.get("title", query),
                "extract": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "thumbnail": data.get("thumbnail", {}).get("source", ""),
                "description": data.get("description", ""),
                "source": "Wikipedia",
            }
            return result
    except Exception:
        return None


def search_wikipedia_search(query, lang="es", limit=3):
    try:
        encoded = urllib.parse.quote(query)
        search_url = (
            f"https://{lang}.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={encoded}"
            f"&srlimit={limit}&format=json"
        )
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


IMAGE_DB = {
    "python": "https://upload.wikimedia.org/wikipedia/commons/c/c3/Python-logo-notext.svg",
    "javascript": "https://upload.wikimedia.org/wikipedia/commons/6/6a/JavaScript-logo.png",
    "html": "https://upload.wikimedia.org/wikipedia/commons/6/61/HTML5_logo_and_wordmark.svg",
    "css": "https://upload.wikimedia.org/wikipedia/commons/d/d5/CSS3_logo_and_wordmark.svg",
    "python": "https://upload.wikimedia.org/wikipedia/commons/c/c3/Python-logo-notext.svg",
    "gato": "https://cdn.pixabay.com/photo/2017/02/20/18/03/cat-2083492_1280.jpg",
    "perro": "https://cdn.pixabay.com/photo/2016/12/13/05/15/puppy-1903313_1280.jpg",
    "tierra": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/The_Earth_seen_from_Apollo_17.jpg/1280px-The_Earth_seen_from_Apollo_17.jpg",
    "luna": "https://upload.wikimedia.org/wikipedia/commons/e/e1/FullMoon2010.jpg",
    "sol": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Solar_prominence_20930215.jpg/1280px-Solar_prominence_20930215.jpg",
    "linux": "https://upload.wikimedia.org/wikipedia/commons/a/af/Tux.png",
    "windows": "https://upload.wikimedia.org/wikipedia/commons/5/5f/Windows_logo_-_2012.svg",
    "apple": "https://upload.wikimedia.org/wikipedia/commons/f/fa/Apple_logo_black.svg",
    "google": "https://upload.wikimedia.org/wikipedia/commons/2/2f/Google_2015_logo.svg",
    "titanic": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fd/RMS_Titanic_3.jpg/1280px-RMS_Titanic_3.jpg",
    "coliseo": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/de/Colosseum_in_Rome_2015.jpg/1280px-Colosseum_in_Rome_2015.jpg",
    "piramides": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e3/Kheops-Pyramid.jpg/1280px-Kheops-Pyramid.jpg",
    "marte": "https://upload.wikimedia.org/wikipedia/commons/0/02/OSIRIS_Mars_true_color.jpg",
    "jupiter": "https://upload.wikimedia.org/wikipedia/commons/2/2b/Jupiter_and_its_shrunken_Great_Red_Spot.jpg",
    "bitcoin": "https://upload.wikimedia.org/wikipedia/commons/4/46/Bitcoin.svg",
    "minecraft": "https://upload.wikimedia.org/wikipedia/commons/3/32/Minecraft_logo.svg",
    "disney": "https://upload.wikimedia.org/wikipedia/commons/d/d4/Disney_wordmark.svg",
    "coca cola": "https://upload.wikimedia.org/wikipedia/commons/3/3a/Coca-Cola_logo.svg",
    "taj mahal": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/67/Taj_Mahal_in_Agro.jpg/1280px-Taj_Mahal_in_Agro.jpg",
    "nintendo": "https://upload.wikimedia.org/wikipedia/commons/0/0d/Nintendo.svg",
    "spotify": "https://upload.wikimedia.org/wikipedia/commons/1/19/Spotify_logo_without_text.svg",
    "netflix": "https://upload.wikimedia.org/wikipedia/commons/0/08/Netflix_2015_logo.svg",
    "tesla": "https://upload.wikimedia.org/wikipedia/commons/b/ba/Tesla_Motors_logo.svg",
    "spacex": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/SpaceX_logo_black.svg/1280px-SpaceX_logo_black.svg.png",
    "robot": "https://upload.wikimedia.org/wikipedia/commons/4/4c/ASIMO_%28roboter%29.jpg",
    "delfin": "https://cdn.pixabay.com/photo/2013/12/21/15/33/dolphin-231869_1280.jpg",
    "elefante": "https://cdn.pixabay.com/photo/2016/11/14/04/45/elephant-1822636_1280.jpg",
    "leon": "https://cdn.pixabay.com/photo/2017/02/28/19/34/lion-2106603_1280.jpg",
    "giraffe": "https://cdn.pixabay.com/photo/2017/02/24/25/giraffe-2094770_1280.jpg",
}

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
        parts.append(f'<img src="{wiki_data["thumbnail"]}" style="width:100%;max-width:350px;border-radius:12px;margin-bottom:12px;">')

    parts.append(f'<strong>{wiki_data["title"]}</strong>')
    if wiki_data.get("description"):
        parts.append(f'<em style="color:#98a8c3;">{wiki_data["description"]}</em>')

    parts.append(wiki_data["extract"])

    if wiki_data.get("url"):
        parts.append(f'\n\n[Fuente: Wikipedia]({wiki_data["url"]})')

    return "\n\n".join(parts)


FACTS_DB = {
    "python": "Python fue creado por Guido van Rossum en 1991. Su nombre viene de los Monty Python.",
    "javascript": "JavaScript fue creado por Brendan Eich en 10 dias en 1995.",
    "html": "HTML fue creado por Tim Berners-Lee en 1991 mientras trabajaba en el CERN.",
    "google": "Google procesa mas de 40,000 busquedas por segundo, mas de 3.5 billones al dia.",
    "internet": "El primer sitio web fue creado por Tim Berners-Lee en 1991 y aun esta online.",
    "linux": "Linux fue creado por Linus Torvalds en 1991 como un proyecto hobby.",
    "windows": "Windows 1.0 fue lanzado en 1985, no fue popular hasta Windows 3.0 en 1990.",
    "amazon": "Amazon empezo vendiendo libros en 1994 desde el garaje de Jeff Bezos.",
    "gato": "Los gatos domesticos comparten el 95.6% de su genoma con los tigres.",
    "perro": "Los perros tienen aproximadamente 300 millones de receptores olfativos, comparado con 5 millones en humanos.",
    "delfin": "Los delfines duermen con un ojo abierto y la mitad de su cerebro activo.",
    "pulpo": "Los pulpos tienen tres corazones, sangre azul y nueve cerebros (uno central y ocho en los brazos).",
    "abeja": "Una abeja produce aproximadamente una cucharadita de miel en toda su vida.",
    "ballena": "La ballena azul es el animal mas grande que ha existido, pesando hasta 200 toneladas.",
    "tierra": "La Tierra viaja alrededor del Sol a 107,000 km/h, pero no lo sentimos por la inercia.",
    "luna": "La Luna se aleja de la Tierra unos 3.8 cm cada año.",
    "sol": "El Sol produce energia equivalente a 100 mil millones de bombas de hidrogeno por segundo.",
    "agua": "El agua cubre el 71% de la superficie de la Tierra, pero solo el 2.5% es agua dulce.",
    "cuerpo humano": "El cuerpo humano tiene aproximadamente 60,000 kilometros de vasos sanguineos.",
    "cerebro": "El cerebro humano tiene alrededor de 86 mil millones de neuronas.",
    "dna": "El ADN humano tiene aproximadamente 3 mil millones de pares de bases.",
    "microondas": "El horno microondas fue inventado por accidente en 1945 por Percy Spencer mientras trabajaba con radar.",
    "internet": "El primer sitio web fue creado por Tim Berners-Lee en 1991 y aun esta online en info.cern.ch.",
    "youtube": "YouTube fue creado por tres ex-empleados de PayPal en 2005 y el primer video se llamo 'Me at the zoo'.",
    "facebook": "Facebook fue lanzado en 2004 por Mark Zuckerberg desde su habitacion en Harvard.",
    "whatsapp": "WhatsApp fue comprado por Facebook en 2014 por $19 mil millones, la mayor compra de una startup en esa epoca.",
    "wikipedia": "Wikipedia tiene mas de 60 millones de articulos en mas de 300 idiomas, todos escritos por voluntarios.",
    "tesla": "Tesla fue fundada en 2003 por Martin Eberhard y Marc Tarpenning. Elon Musk se unio como inversor principal.",
    "spacex": "SpaceX fue fundada por Elon Musk en 2002 con el objetivo de colonizar Marte.",
    "nasa": "La NASA fue creada en 1958 en respuesta al lanzamiento del Sputnik por la Union Sovietica.",
    "apple": "Apple fue fundada por Steve Jobs, Steve Wozniak y Ronald Wayne en 1976 en un garaje.",
    "microsoft": "Microsoft fue fundada por Bill Gates y Paul Allen en 1975. Su primer producto fue un interprete de BASIC.",
    "netflix": "Netflix empezo en 1997 como un servicio de alquiler de DVD por correo. Hoy tiene mas de 270 millones de suscriptores.",
    "spotify": "Spotify fue lanzado en 2008 en Suecia y revoluciono la industria musical con streaming.",
    "chatgpt": "ChatGPT fue lanzado por OpenAI en noviembre de 2022 y alcanzo 100 millones de usuarios en solo 2 meses.",
    "google": "Google maneja mas de 3.5 billones de busquedas al dia desde su fundacion en 1998 por Larry Page y Sergey Brin.",
    "android": "Android fue comprado por Google en 2005 por $50 millones. Hoy es el sistema operativo movil mas usado del mundo.",
    "iphone": "El primer iPhone fue lanzado en 2007 por Steve Jobs y cambio la industria de los smartphones para siempre.",
    "bitcoin": "Bitcoin fue creado en 2009 por una persona o grupo bajo el seudonimo Satoshi Nakamoto.",
    "ia": "El termino 'Inteligencia Artificial' fue acunado por John McCarthy en 1956 en la Conferencia de Dartmouth.",
    "robot": "La palabra 'robot' viene del checo 'robota' que significa 'trabajo forzado'. Fue usada por primera vez en 1920.",
    "programacion": "El primer lenguaje de programacion de alto nivel fue Plankalkul, creado por Konrad Zuse entre 1942 y 1945.",
    "primer ordenador": "La ENIAC, considerada la primera computadora electronica de proposito general, pesaba 27 toneladas.",
    "ibm": "IBM existe desde 1911, originalmente como Computing-Tabulating-Recording Company (CTR).",
    "bug": "El termino 'bug' en programacion viene de un insecto real encontrado en un relay del Harvard Mark II en 1947.",
    "hacker": "El termino 'hacker' originalmente describia a programadores expertos, no a criminales informaticos.",
    "contraseña": "La contraseña mas comun en el mundo es '123456', seguida de 'password'.",
    "velocidad luz": "La luz viaja a 299,792,458 metros por segundo. Puede dar 7.5 vueltas a la Tierra en un segundo.",
    "gravedad": "La gravedad es la fuerza mas debil de las cuatro fuerzas fundamentales, pero la que mas sentimos.",
    "rayo": "Un rayo puede alcanzar temperaturas de 30,000 grados Celsius, cinco veces mas caliente que la superficie del sol.",
    "formula 1": "Un coche de Formula 1 puede perder hasta 10 kg de peso durante una carrera por el desgaste de los neumaticos.",
    "ajedrez": "Hay mas posibles partidas de ajedrez que atomos en el universo observable.",
    "musica": "La cancion mas reproducida en Spotify es 'Blinding Lights' de The Weeknd, con mas de 4 mil millones de reproducciones.",
    "coliseo": "El Coliseo Romano podia albergar hasta 80,000 espectadores y tenia un toldo retractil gigante (velarium).",
    "piramides": "Las piramides de Egipto fueron construidas hace mas de 4,500 anos y son las unicas maravillas del mundo antiguo que aun existen.",
    "marte": "Un dia en Marte dura 24 horas y 37 minutos, casi igual que un dia en la Tierra.",
    "jupiter": "Jupiter es el planeta mas grande del sistema solar y su Gran Mancha Roja es una tormenta que dura siglos.",
    "vuelo": "El primer vuelo comercial de pasajeros fue en 1914, volando de San Petersburgo a Tampa, Florida, y duro 23 minutos.",
    "titanic": "El Titanic tenia 269 metros de eslora y se hundio en 1912 en su viaje inaugural.",
    "the beatles": "Los Beatles vendieron mas de 600 millones de discos en todo el mundo.",
    "star wars": "Star Wars fue estrenada en 1977 y recaudo $775 millones, superando a Tiburon como la pelicula mas taquillera.",
    "minecraft": "Minecraft es el videojuego mas vendido de la historia con mas de 300 millones de copias.",
    "gta": "Grand Theft Auto V es uno de los juegos mas exitosos, generando mas de $6 mil millones desde su lanzamiento en 2013.",
    "pokemon": "Pokemon es la franquicia mediatica mas grande del mundo, superando a Mickey Mouse y Star Wars.",
    "coca cola": "Coca-Cola fue inventada en 1886 por John Pemberton y originalmente contenía cocaína.",
    "kfc": "KFC fue fundado por el Coronel Harland Sanders a los 65 años, despues de recibir su primer cheque de jubilacion.",
    "mcdonalds": "McDonald's fue fundado en 1940 por los hermanos Richard y Maurice McDonald en San Bernardino, California.",
    "lego": "LEGO viene del danes 'leg godt' que significa 'juega bien'. Las piezas actuales son compatibles con las de 1958.",
    "disney": "Walt Disney fundo Disney en 1923. El primer personaje creado fue Oswald el Conejo Afortunado, no Mickey Mouse.",
    "nintendo": "Nintendo fue fundada en 1889 como una empresa de naipes (hanafuda) antes de entrar en los videojuegos.",
    "samsung": "Samsung empezo en 1938 como una empresa de exportacion de pescado y verduras en Corea del Sur.",
    "honda": "Honda empezo fabricando motores para bicicletas despues de la Segunda Guerra Mundial.",
    "toyota": "Toyota empezo como fabricante de telares automaticos antes de producir automoviles.",
    "ferrari": "Ferrari fue fundada por Enzo Ferrari en 1947. Originalmente era el equipo de carreras de Alfa Romeo.",
    "lamborghini": "Lamborghini fue fundada por Ferruccio Lamborghini, un fabricante de tractores, despues de una disputa con Enzo Ferrari.",
    "nikon": "Nikon fue fundada en 1917 como Nippon Kogaku Kogyo, fabricando lentes opticos para camaras.",
    "canon": "Canon fue fundada en 1937 como Precision Optical Industry. Su primera camara fue la Kwanon.",
    "post it": "Las notas Post-it fueron inventadas por accidente en 1968 cuando Spencer Silver creo un adhesivo debil.",
    "velcro": "El velcro fue inventado en 1941 por George de Mestral despues de observar como las semillas de cardo se pegaban a su ropa.",
    "microondas": "El horno microondas fue descubierto por accidente en 1945 por Percy Spencer mientras trabajaba con magnetrones de radar.",
    "rayos x": "Los rayos X fueron descubiertos por Wilhelm Rontgen en 1895. La primera radiografia fue de la mano de su esposa.",
    "penicilina": "La penicilina fue descubierta por Alexander Fleming en 1928 cuando observo moho que mataba bacterias.",
    "vacuna": "La primera vacuna fue creada por Edward Jenner en 1796 contra la viruela, usando virus de la vaccinia (viruela bovina).",
    "relatividad": "Einstein publico su teoria de la relatividad general en 1915, prediciendo agujeros negros y ondas gravitacionales.",
    "big bang": "La teoria del Big Bang fue propuesta por Georges Lemaitre en 1927, un sacerdote y astronomo belga.",
    "agujero negro": "El primer agujero negro fotografiado (M87) fue capturado en 2019 por el telescopio Event Horizon.",
    "fotosintesis": "La fotosintesis convierte la luz solar en energia quimica, produciendo oxigeno como subproducto.",
    "mariposa": "Las mariposas saborean con sus patas y tienen sensores de sabor en sus pies.",
    "camaleon": "Los camaleones cambian de color para comunicarse y regular temperatura, no solo para camuflarse.",
    "colibri": "Los colibris son las unicas aves que pueden volar hacia atras y baten sus alas hasta 80 veces por segundo.",
    "hormiga": "Las hormigas pueden levantar hasta 50 veces su propio peso y existen mas de 12,000 especies.",
    "elefante": "Los elefantes son los unicos animales con cuatro rodillas. Son el animal terrestre mas grande.",
    "jirafa": "Las jirafas tienen el mismo numero de vertebras en el cuello que los humanos: siete.",
    "canguro": "Los canguros no pueden caminar hacia atras y las hembras tienen tres vaginas.",
    "panda": "Los pandas gigantes pasan hasta 14 horas al dia comiendo bambu, hasta 38 kg diarios.",
    "tiburon": "Los tiburones han existido por mas de 400 millones de anos, antes que los dinosaurios.",
    "fuego": "El fuego no tiene sombra porque la luz lo atraviesa. El fuego es plasma, no gas.",
    "hielo": "El hielo flota porque es menos denso que el agua liquida, una propiedad unica del agua.",
    "imanes": "Los imanes tienen dos polos (norte y sur) que nunca se pueden separar, incluso si los partes.",
    "eco": "El eco se produce cuando el sonido rebota en una superficie y tarda mas de 0.1 segundos en regresar.",
    "arcoiris": "Los arcoiris son circulos completos, pero desde el suelo solo vemos un arco porque la tierra bloquea la mitad.",
}

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
    # Add more sources
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
        query = data.get("query", "").strip().lower()
        if not query:
            return jsonify({"svg": "", "error": "Dime que dibujar"})

        # Extract color
        colors = {
            "rojo": "#ef4444", "red": "#ef4444",
            "azul": "#3b82f6", "blue": "#3b82f6",
            "verde": "#22c55e", "green": "#22c55e",
            "amarillo": "#fbbf24", "yellow": "#fbbf24", "dorado": "#fbbf24",
            "naranja": "#f97316", "orange": "#f97316",
            "morado": "#a855f7", "purple": "#a855f7", "violeta": "#a855f7",
            "rosa": "#ec4899", "pink": "#ec4899",
            "cyan": "#06b6d4", "celeste": "#06b6d4",
            "blanco": "#ffffff", "white": "#ffffff",
            "negro": "#1f2937", "black": "#1f2937",
            "gris": "#9ca3af", "gray": "#9ca3af",
        }
        fill_color = "#57a6ff"
        stroke_color = "#34d399"
        for cname, cval in colors.items():
            if cname in query:
                fill_color = cval
                stroke_color = cval
                break

        svg = ""
        # Basic shapes
        if any(w in query for w in ["circulo", "circle", "pelota", "bola", "esfera"]):
            svg = f'<svg width="200" height="200"><circle cx="100" cy="100" r="60" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Círculo</text></svg>'
        elif any(w in query for w in ["cuadrado", "square", "caja", "rectangulo", "rectángulo"]):
            svg = f'<svg width="200" height="200"><rect x="30" y="30" width="140" height="140" rx="8" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Cuadrado</text></svg>'
        elif any(w in query for w in ["triangulo", "triángulo", "triangle"]):
            svg = f'<svg width="200" height="200"><polygon points="100,20 180,160 20,160" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="115" text-anchor="middle" fill="white" font-size="14">Triángulo</text></svg>'
        elif any(w in query for w in ["estrella", "star"]):
            svg = f'<svg width="200" height="200"><polygon points="100,20 120,80 180,80 130,120 150,180 100,150 50,180 70,120 20,80 80,80" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Estrella</text></svg>'
        elif any(w in query for w in ["casa", "house", "hogar"]):
            svg = f'<svg width="220" height="200"><rect x="60" y="80" width="100" height="100" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><polygon points="30,80 110,20 190,80" fill="{stroke_color}" stroke="#f59e0b" stroke-width="2"/><rect x="90" y="120" width="40" height="60" fill="#131c2f" stroke="#f59e0b" stroke-width="2"/></svg>'
        elif any(w in query for w in ["corazon", "corazón", "heart", "amor"]):
            svg = f'<svg width="200" height="200"><path d="M100,170 C40,120 10,70 50,30 C70,10 100,30 100,50 C100,30 130,10 150,30 C190,70 160,120 100,170Z" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="12">Corazón</text></svg>'
        # New shapes
        elif any(w in query for w in ["hexagono", "hexágono", "hexagon"]):
            svg = f'<svg width="200" height="200"><polygon points="100,15 175,55 175,145 100,185 25,145 25,55" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Hexágono</text></svg>'
        elif any(w in query for w in ["pentagono", "pentágono", "pentagon"]):
            svg = f'<svg width="200" height="200"><polygon points="100,15 170,70 140,175 60,175 30,70" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Pentágono</text></svg>'
        elif any(w in query for w in ["rombo", "diamond", "diamante"]):
            svg = f'<svg width="200" height="200"><polygon points="100,20 180,100 100,180 20,100" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Rombo</text></svg>'
        elif any(w in query for w in ["nube", "cloud"]):
            svg = f'<svg width="250" height="150"><ellipse cx="80" cy="80" rx="50" ry="30" fill="{fill_color}"/><ellipse cx="140" cy="70" rx="40" ry="25" fill="{fill_color}"/><ellipse cx="180" cy="90" rx="35" ry="25" fill="{fill_color}"/><ellipse cx="120" cy="95" rx="45" ry="25" fill="{fill_color}"/></svg>'
        elif any(w in query for w in ["sol", "sun"]):
            svg = f'<svg width="200" height="200"><circle cx="100" cy="100" r="40" fill="#fbbf24" stroke="#f59e0b" stroke-width="3"/><g stroke="#fbbf24" stroke-width="3"><line x1="100" y1="15" x2="100" y2="35"/><line x1="100" y1="165" x2="100" y2="185"/><line x1="15" y1="100" x2="35" y2="100"/><line x1="165" y1="100" x2="185" y2="100"/><line x1="35" y1="35" x2="50" y2="50"/><line x1="150" y1="150" x2="165" y2="165"/><line x1="35" y1="165" x2="50" y2="150"/><line x1="150" y1="50" x2="165" y2="35"/></g></svg>'
        elif any(w in query for w in ["luna", "moon"]):
            svg = f'<svg width="200" height="200"><circle cx="100" cy="100" r="60" fill="#fbbf24"/><circle cx="130" cy="80" r="60" fill="#0f1624"/></svg>'
        elif any(w in query for w in ["arbol", "árbol", "tree"]):
            svg = f'<svg width="200" height="250"><rect x="90" y="150" width="20" height="100" fill="#8b4513"/><ellipse cx="100" cy="80" rx="60" ry="70" fill="#22c55e"/><ellipse cx="50" cy="120" rx="40" ry="30" fill="#16a34a"/><ellipse cx="150" cy="120" rx="40" ry="30" fill="#16a34a"/></svg>'
        elif any(w in query for w in ["flor", "flower"]):
            svg = f'<svg width="200" height="250"><line x1="100" y1="150" x2="100" y2="240" stroke="#22c55e" stroke-width="6"/><g fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"><circle cx="100" cy="100" r="30"/><circle cx="100" cy="50" r="25"/><circle cx="140" cy="85" r="25"/><circle cx="60" cy="85" r="25"/><circle cx="80" cy="130" r="25"/><circle cx="120" cy="130" r="25"/></g><circle cx="100" cy="100" r="15" fill="#fbbf24"/></svg>'
        elif any(w in query for w in ["gato", "cat", "gatito"]):
            svg = f'<svg width="200" height="200"><circle cx="100" cy="110" r="50" fill="{fill_color}"/><circle cx="70" cy="65" r="25" fill="{fill_color}"/><circle cx="130" cy="65" r="25" fill="{fill_color}"/><circle cx="80" cy="100" r="8" fill="white"/><circle cx="120" cy="100" r="8" fill="white"/><circle cx="75" cy="100" r="4" fill="black"/><circle cx="115" cy="100" r="4" fill="black"/><ellipse cx="100" cy="125" rx="15" ry="8" fill="pink"/><path d="M85,130 Q100,135 115,130" stroke="black" stroke-width="2" fill="none"/></svg>'
        elif any(w in query for w in ["perro", "dog", "perrito"]):
            svg = f'<svg width="200" height="200"><ellipse cx="100" cy="120" rx="55" ry="45" fill="{fill_color}"/><circle cx="100" cy="70" r="35" fill="{fill_color}"/><ellipse cx="70" cy="50" rx="15" ry="25" fill="{fill_color}"/><ellipse cx="130" cy="50" rx="15" ry="25" fill="{fill_color}"/><circle cx="85" cy="65" r="6" fill="white"/><circle cx="115" cy="65" r="6" fill="white"/><circle cx="82" cy="65" r="3" fill="black"/><circle cx="112" cy="65" r="3" fill="black"/><ellipse cx="100" cy="85" rx="12" ry="8" fill="#8b4513"/><path d="M90,92 Q100,98 110,92" stroke="black" stroke-width="2" fill="none"/></svg>'
        elif any(w in query for w in ["cohete", "rocket", "nave"]):
            svg = f'<svg width="150" height="300"><rect x="50" y="50" width="50" height="180" rx="5" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><polygon points="50,50 75,15 100,50" fill="{stroke_color}"/><rect x="60" y="180" width="30" height="50" fill="#8b4513"/><ellipse cx="75" cy="120" rx="15" ry="15" fill="#06b6d4"/><path d="M50,230 L30,280 M100,230 L120,280" stroke="#f59e0b" stroke-width="8" stroke-linecap="round"/></svg>'
        elif any(w in query for w in ["robot", "bot"]):
            svg = f'<svg width="200" height="250"><rect x="50" y="120" width="100" height="100" rx="10" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><rect x="65" y="140" width="30" height="20" rx="5" fill="#06b6d4"/><rect x="105" y="140" width="30" height="20" rx="5" fill="#06b6d4"/><circle cx="80" cy="90" r="25" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><circle cx="70" cy="85" r="5" fill="white"/><circle cx="90" cy="85" r="5" fill="white"/><line x1="30" y1="140" x2="20" y2="120" stroke="{stroke_color}" stroke-width="5" stroke-linecap="round"/><line x1="170" y1="140" x2="180" y2="120" stroke="{stroke_color}" stroke-width="5" stroke-linecap="round"/></svg>'
        elif any(w in query for w in ["coche", "car", "auto", "carro"]):
            svg = f'<svg width="300" height="150"><rect x="30" y="60" width="240" height="50" rx="10" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><polygon points="60,60 90,30 210,30 240,60" fill="{stroke_color}"/><circle cx="80" cy="110" r="20" fill="#1f2937" stroke="#fff" stroke-width="2"/><circle cx="220" cy="110" r="20" fill="#1f2937" stroke="#fff" stroke-width="2"/><circle cx="80" cy="110" r="8" fill="#fff"/><circle cx="220" cy="110" r="8" fill="#fff"/></svg>'
        elif any(w in query for w in ["avion", "avión", "plane", "aereo", "aéreo"]):
            svg = f'<svg width="300" height="150"><path d="M30,100 Q100,20 150,100 Q100,180 30,100" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><polygon points="150,100 250,70 250,130" fill="{stroke_color}"/><ellipse cx="60" cy="100" rx="80" ry="15" fill="{stroke_color}"/></svg>'
        elif any(w in query for w in ["barco", "ship", "velero"]):
            svg = f'<svg width="300" height="200"><path d="M20,140 Q150,100 280,140 L280,170 L20,170 Z" fill="#8b4513" stroke="#5c4033" stroke-width="3"/><line x1="150" y1="40" x2="150" y2="140" stroke="#5c4033" stroke-width="4"/><polygon points="150,40 250,90 150,120" fill="#fff"/></svg>'
        elif any(w in query for w in ["taza", "cup", "cafe", "café", "mug"]):
            svg = f'<svg width="200" height="200"><path d="M50,180 L60,80 Q100,60 140,80 L150,180" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3" stroke-linejoin="round"/><path d="M150,120 Q180,110 180,90 Q180,70 150,60" fill="none" stroke="{stroke_color}" stroke-width="3" stroke-linecap="round"/><ellipse cx="100" cy="65" rx="45" ry="8" fill="{stroke_color}"/></svg>'
        elif any(w in query for w in ["pizza"]):
            svg = f'<svg width="200" height="200"><circle cx="100" cy="100" r="90" fill="#f59e0b" stroke="#d97706" stroke-width="4"/><g fill="#ef4444"><circle cx="70" cy="70" r="12"/><circle cx="130" cy="80" r="10"/><circle cx="100" cy="130" r="11"/><circle cx="50" cy="110" r="9"/><circle cx="140" cy="120" r="10"/></g></svg>'
        elif any(w in query for w in ["hamburguesa", "burger", "hamburger"]):
            svg = f'<svg width="200" height="250"><ellipse cx="100" cy="40" rx="70" ry="20" fill="#f59e0b"/><ellipse cx="100" cy="80" rx="75" ry="15" fill="#4ade80"/><ellipse cx="100" cy="110" rx="78" ry="18" fill="#ef4444"/><ellipse cx="100" cy="140" rx="75" ry="15" fill="#fbbf24"/><ellipse cx="100" cy="170" rx="70" ry="18" fill="#8b4513"/><ellipse cx="100" cy="195" rx="70" ry="20" fill="#f59e0b"/></svg>'
        elif any(w in query for w in ["donut", "dona", "rosquilla"]):
            svg = f'<svg width="200" height="200"><circle cx="100" cy="100" r="70" fill="#d97706" stroke="#92400e" stroke-width="3"/><circle cx="100" cy="100" r="25" fill="#0f1624"/><g fill="#ec4899"><circle cx="70" cy="50" r="10"/><circle cx="130" cy="60" r="8"/><circle cx="110" cy="140" r="9"/><circle cx="50" cy="120" r="7"/><circle cx="150" cy="110" r="8"/></g></svg>'
        else:
            svg = f'<svg width="250" height="100"><rect x="10" y="10" width="230" height="80" rx="12" fill="#0f1624" stroke="#57a6ff" stroke-width="1"/><text x="125" y="50" text-anchor="middle" fill="#98a8c3" font-size="14">Dibujo: {query[:30]}</text><text x="125" y="70" text-anchor="middle" fill="#98a8c3" font-size="10">formas: circulo, triangulo, estrella, casa, corazon, hexagono, nube, sol, arbol, gato, perro, cohete, robot, coche, avion, barco, pizza, hamburguesa, donut...</text></svg>'

        return jsonify({"svg": svg, "query": query})
    except Exception:
        return jsonify({"svg": "", "error": "Error al dibujar"})


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    try:
        data = request.get_json(silent=True) or {}
        expr = data.get("expr", "").strip()
        if not expr:
            return jsonify({"result": None, "error": "Expresion vacia"})

        # Safe evaluation
        import re
        allowed = re.compile(r'^[\d\s\+\-\*/\(\)\.\%\*\*]+$')
        if not allowed.match(expr):
            return jsonify({"result": None, "error": "Expresion invalida"})

        result = eval(expr, {"__builtins__": {}}, {})
        return jsonify({"result": result, "expr": expr})
    except Exception as e:
        return jsonify({"result": None, "error": str(e)})


MESSAGES_FILE = BASE_DIR / "ans_messages.json"

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
    return render_template("admin.html", users=user_list, concepts=concept_count, memory=memory_count, history_files=history_files, memory_items=list(learned.items())[:100], blocked=blocked, messages=messages, facts_count=len(FACTS_DB))


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
    # Delete history file
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
        # Update chat's updated_at
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
        return redirect(url_for("hm"))
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

    # Use env var redirect_uri if set (what's registered in Google Cloud Console)
    if GOOGLE_REDIRECT_URI:
        redirect_uri = GOOGLE_REDIRECT_URI
    else:
        # Dynamic fallback: normalize 127.0.0.1 → localhost for GCP match
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

        return redirect(url_for("hm"))
    except Exception:
        return redirect(url_for("login"))


def exchange_code_for_token(code):
    try:
        # Use session-stored redirect_uri (dynamic), fall back to env var
        redirect_uri = session.pop("google_redirect_uri", None) or GOOGLE_REDIRECT_URI
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Token exchange error: {e}")
        return None


def get_google_user_info(access_token):
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


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


def normalize_text(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


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


def solve_basic_equation(text):
    """Solve equations with any single-letter variable (x, t, y, z, a, b, etc.)"""
    var_match = re.search(r"(?:^|\s|\d)([a-z])\s*(?:[+\-*/^]|$|=)", text, re.IGNORECASE)
    if not var_match:
        return None
    var = var_match.group(1).lower()

    patterns = [
        rf"^\s*(-?\d*){var}\s*([+-])\s*(\d+)\s*=\s*(-?\d+)\s*$",
        rf"^\s*(-?\d*){var}\s*=\s*(-?\d+)\s*$",
    ]

    match = re.search(patterns[0], text, re.IGNORECASE)
    if match:
        raw_a, sign, raw_b, raw_c = match.groups()
        a = 1 if raw_a in ("", "+") else -1 if raw_a == "-" else int(raw_a)
        b = int(raw_b)
        c = int(raw_c)
        if sign == "-":
            b = -b

        step1 = c - b
        result = step1 / a

        return (
            "<div class=\"math-box\">"
            f"<strong>📐 Ecuacion detectada</strong><br><br>"
            f"Ecuacion original: <code>{a}{var} {sign} {abs(int(raw_b))} = {c}</code><br><br>"
            f"<strong>Paso 1:</strong> Agrupar terminos independientes<br>"
            f"<code>{a}{var} = {c} - ({b})</code><br>"
            f"<code>{a}{var} = {step1}</code><br><br>"
            f"<strong>Paso 2:</strong> Despejar {var}<br>"
            f"<code>{var} = {step1} / {a}</code><br><br>"
            f"<strong>Resultado: {var} = {result}</strong>"
            "</div>"
        )

    match2 = re.search(patterns[1], text, re.IGNORECASE)
    if match2:
        raw_a = match2.group(1)
        raw_b = match2.group(2)
        a = 1 if raw_a in ("", "+") else -1 if raw_a == "-" else int(raw_a)
        b = int(raw_b)
        result = b / a

        return (
            "<div class=\"math-box\">"
            f"<strong>📐 Ecuacion simple detectada</strong><br><br>"
            f"<code>{a}{var} = {b}</code><br>"
            f"<code>{var} = {b} / {a}</code><br><br>"
            f"<strong>Resultado: {var} = {result}</strong>"
            "</div>"
        )

    return None


def solve_basic_math(text):
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([+\-*/xX^])\s*(-?\d+(?:\.\d+)?)", text)
    if not match:
        match = re.search(r"(-?\d+(?:\.\d+)?)\s+(mas|menos|por|entre|multiplicado por|dividido por)\s+(-?\d+(?:\.\d+)?)", text)
        if match:
            op_text = match.group(2).lower()
            op_map = {
                "mas": "+", "menos": "-", "por": "*", "multiplicado por": "*",
                "entre": "/", "dividido por": "/"
            }
            op = op_map.get(op_text, "+")
            a = float(match.group(1))
            b = float(match.group(3))
            result = _calc(a, op, b)
            return f"El resultado de <code>{a} {op_text} {b}</code> es: <strong>{_format_num(result)}</strong>."
        return None

    a = float(match.group(1))
    op = match.group(2).replace("x", "*").replace("X", "*")
    b = float(match.group(3))
    result = _calc(a, op, b)

    if result is None:
        return None

    return (
        "<div class=\"math-box\">"
        f"<strong>🔢 Operacion:</strong> <code>{a} {op} {b}</code><br>"
        f"<strong>Resultado:</strong> <strong>{_format_num(result)}</strong>"
        "</div>"
    )


def _calc(a, op, b):
    if op == "+":
        return a + b
    elif op == "-":
        return a - b
    elif op in ("*", "x", "X"):
        return a * b
    elif op == "/":
        if b == 0:
            return None
        return a / b
    elif op == "^":
        return a ** b
    return None


def _format_num(n):
    if isinstance(n, float) and n == int(n):
        return str(int(n))
    if isinstance(n, float):
        return f"{n:.6g}"
    return str(n)


def solve_logarithms(text):
    lower = normalize_text(text)
    # Examples: log(100), ln(5), log10(100), log2(8), logaritmo base 2 de 8
    patterns = [
        (r"log10?\s*\(\s*(\d+(?:\.\d+)?)\s*\)", lambda m: math.log10(float(m.group(1)))),
        (r"ln\s*\(\s*(\d+(?:\.\d+)?)\s*\)", lambda m: math.log(float(m.group(1)))),
        (r"log2\s*\(\s*(\d+(?:\.\d+)?)\s*\)", lambda m: math.log(float(m.group(1)), 2)),
        (r"log\s*\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)", lambda m: math.log(float(m.group(1)), float(m.group(2)))),
        (r"log\s*\(\s*(\d+(?:\.\d+)?)\s*\)", lambda m: math.log10(float(m.group(1)))),
        (r"logaritmo\s+(?:natural\s+)?(?:de\s+)?(\d+(?:\.\d+)?)", lambda m: math.log(float(m.group(1)))),
        (r"logaritmo\s+base\s+(\d+(?:\.\d+)?)\s+de\s+(\d+(?:\.\d+)?)", lambda m: math.log(float(m.group(2)), float(m.group(1)))),
        (r"log10\s+de\s+(\d+(?:\.\d+)?)", lambda m: math.log10(float(m.group(1)))),
        (r"ln\s+de\s+(\d+(?:\.\d+)?)", lambda m: math.log(float(m.group(1)))),
    ]
    for pattern, calc in patterns:
        match = re.search(pattern, lower)
        if match:
            try:
                result = calc(match)
                # Pretty print the formula back
                if "ln" in pattern:
                    formula = f"ln({match.group(1)})"
                elif "log10" in pattern or "log10" in pattern:
                    formula = f"log10({match.group(1)})"
                elif "log2" in pattern:
                    formula = f"log2({match.group(1)})"
                elif "base" in lower:
                    formula = f"log_{match.group(1)}({match.group(2)})"
                elif "log" in pattern and "," not in pattern:
                    formula = f"log({match.group(1)})"
                else:
                    formula = text.strip()
                return (
                    "<div class=\"math-box\">"
                    f"<strong>📐 Logaritmo</strong><br><br>"
                    f"<code>{formula} = {_format_num(result)}</code><br><br>"
                    f"<small>Base: {'e' if 'ln' in pattern or 'natural' in lower else '10' if 'log10' in pattern else '2' if 'log2' in pattern else '10'}</small>"
                    "</div>"
                )
            except (ValueError, ZeroDivisionError):
                return "No se puede calcular el logaritmo de ese numero (debe ser > 0)."
    return None


def solve_algebra(text):
    """Solve more complex equations: ax + b = cx + d, quadratic, etc."""
    lower = normalize_text(text)

    # Detect any single-letter variable used in the equation
    vmatch = re.search(r"(?:^|\s|\d)([a-z])\s*(?:[+\-*/^]|$)", lower)
    _var = vmatch.group(1) if vmatch else "x"
    _evar = re.escape(_var)

    # Quadratic: av^2 + bv + c = 0
    qpat = r"(\d+(?:\.\d+)?)\s*" + _evar + r"\s*\^?\s*2\s*([+-])\s*(\d+(?:\.\d+)?)\s*" + _evar + r"\s*([+-])\s*(\d+(?:\.\d+)?)\s*=\s*0"
    quad = re.search(qpat, lower)
    if quad:
        a = float(quad.group(1))
        b_sign = 1 if quad.group(2) == "+" else -1
        b = b_sign * float(quad.group(3))
        c_sign = 1 if quad.group(4) == "+" else -1
        c = c_sign * float(quad.group(5))
        disc = b*b - 4*a*c
        if disc < 0:
            return (
                "<div class=\"math-box\">"
                f"<strong>📐 Ecuacion cuadratica</strong><br><br>"
                f"<code>{a}{_var}² + {b}{_var} + {c} = 0</code><br><br>"
                f"Discriminante = {b}² - 4({a})({c}) = {disc} < 0<br>"
                f"<strong>No tiene solucion real</strong> (raices complejas)"
                "</div>"
            )
        x1 = (-b + math.sqrt(disc)) / (2*a)
        x2 = (-b - math.sqrt(disc)) / (2*a)
        return (
            "<div class=\"math-box\">"
            f"<strong>📐 Ecuacion cuadratica</strong><br><br>"
            f"<code>{a}{_var}² + {b}{_var} + {c} = 0</code><br><br>"
            f"<strong>Formula general:</strong><br>"
            f"{_var} = [ -({b}) ± √({b}² - 4·{a}·{c}) ] / (2·{a})<br><br>"
            f"Discriminante: {disc}<br><br>"
            f"<strong>{_var}₁ = {_format_num(x1)}</strong><br>"
            f"<strong>{_var}₂ = {_format_num(x2)}</strong>"
            "</div>"
        )

    # Both sides: av + b = cv + d
    both_pat = r"(\d+)\s*" + _evar + r"\s*([+-])\s*(\d+)\s*=\s*(\d+)\s*" + _evar + r"\s*([+-])\s*(\d+)"
    both = re.search(both_pat, lower)
    if both:
        a = float(both.group(1))
        sign_b = 1 if both.group(2) == "+" else -1
        b = sign_b * float(both.group(3))
        c = float(both.group(4))
        sign_d = 1 if both.group(5) == "+" else -1
        d = sign_d * float(both.group(6))
        result = (d - b) / (a - c)
        return (
            "<div class=\"math-box\">"
            f"<strong>📐 Ecuacion con {_var} en ambos lados</strong><br><br>"
            f"<code>{a}{_var} {'+' if b >= 0 else '-'} {abs(int(b))} = {c}{_var} {'+' if d >= 0 else '-'} {abs(int(d))}</code><br><br>"
            f"<strong>Paso 1:</strong> Agrupar terminos con {_var}<br>"
            f"<code>{a}{_var} - {c}{_var} = {d} - ({b})</code><br>"
            f"<code>({a-c}){_var} = {d-b}</code><br><br>"
            f"<strong>Paso 2:</strong> Despejar {_var}<br>"
            f"<code>{_var} = {d-b} / {a-c}</code><br><br>"
            f"<strong>Resultado: {_var} = {_format_num(result)}</strong>"
            "</div>"
        )

    # Like terms: av + bv = c  (e.g. "2t + 2t = 0" → 4t = 0 → t = 0)
    like_pat = r"(\d+)\s*" + _evar + r"\s*([+-])\s*(\d+)\s*" + _evar + r"\s*=\s*(-?\d+)"
    like_m = re.search(like_pat, lower)
    if like_m:
        a = float(like_m.group(1))
        sign_b = 1 if like_m.group(2) == "+" else -1
        b = sign_b * float(like_m.group(3))
        c = float(like_m.group(4))
        combined = a + b
        if combined == 0:
            return (
                "<div class=\"math-box\">"
                f"<strong>📐 Combinacion de terminos</strong><br><br>"
                f"<code>{a}{_var} {'+' if b >= 0 else '-'} {abs(int(b))}{_var} = {c}</code><br><br>"
                f"({a}{'+' if b >= 0 else '-'}{abs(int(b))}){_var} = {c}<br>"
                f"<code>{combined}{_var} = {c}</code><br><br>"
                f"Los terminos se cancelan: 0{_var} = {c}<br>"
                f"<strong>No tiene solucion</strong> (a menos que {c} = 0)"
                "</div>"
            )
        result = c / combined
        return (
            "<div class=\"math-box\">"
            f"<strong>📐 Combinacion de terminos semejantes</strong><br><br>"
            f"<code>{a}{_var} {'+' if b >= 0 else '-'} {abs(int(b))}{_var} = {c}</code><br><br>"
            f"<strong>Paso 1:</strong> Sumar coeficientes<br>"
            f"<code>({a} {'+' if b >= 0 else '-'} {abs(int(b))}){_var} = {c}</code><br>"
            f"<code>{combined}{_var} = {c}</code><br><br>"
            f"<strong>Paso 2:</strong> Despejar {_var}<br>"
            f"<code>{_var} = {c} / {combined}</code><br><br>"
            f"<strong>Resultado: {_var} = {_format_num(result)}</strong>"
            "</div>"
        )

    # Detect incomplete algebra EXPRESSION: "2t + 3", "x + 5" (has var but no =)
    if "=" not in lower and len(text) < 30:
        num_var = r"\d+\s*" + _evar + r"\s*[+\-*/^]"
        var_op = r"(?:^|\s|\d)" + _evar + r"\s*[+\-*/^=]|[+\-*/^]\s*" + _evar
        if re.search(num_var, lower) or re.search(var_op, lower):
            esc = html_lib.escape(text.strip())
            return (
                "<div class=\"math-box\">"
                "<strong>📐 Expresion algebraica detectada</strong><br><br>"
                f"Escribiste: <code>{esc}</code><br><br>"
                "Es una <strong>expresion algebraica</strong>, pero falta el <strong>=</strong> para resolverla.<br><br>"
                "<strong>Ejemplos completos:</strong><br>"
                f"<code>{esc} = 0</code><br>"
                f"<code>{esc} = 10</code><br><br>"
                "✏️ *Escribe la ecuacion completa (con =) para que la resuelva.*"
                "</div>"
            )

    solve_match = re.search(r"(?:solve|resolver|despejar)\s*(?:x|la\s*ecuacion)?\s*([\dx\s+\-*/^=.]+)", lower)
    if solve_match:
        return None
    return None


def solve_advanced_math(text):
    lower = normalize_text(text)

    porcentaje = re.search(r"(\d+(?:\.\d+)?)\s*(?:por\s*ciento|%)\s*(?:de|de\s+)?\s*(\d+(?:\.\d+)?)", lower)
    if not porcentaje:
        porcentaje = re.search(r"cuanto\s+es\s+el?\s*(\d+(?:\.\d+)?)\s*%\s*(?:de|de\s+)?\s*(\d+(?:\.\d+)?)", lower)
    if porcentaje:
        pct = float(porcentaje.group(1))
        base = float(porcentaje.group(2))
        result = (pct / 100) * base
        return (
            "<div class=\"math-box\">"
            f"<strong>Porcentaje:</strong> {pct}% de {base}<br>"
            f"<code>({pct} / 100) x {base} = {result}</code><br>"
            f"<strong>Resultado: {_format_num(result)}</strong>"
            "</div>"
        )

    potencia = re.search(r"(\d+(?:\.\d+)?)\s*(?:\^|\*\*)\s*(\d+(?:\.\d+)?)", text)
    if potencia:
        base = float(potencia.group(1))
        exp = float(potencia.group(2))
        result = base ** exp
        return (
            "<div class=\"math-box\">"
            f"<strong>Potencia:</strong> {base}^{exp}<br>"
            f"<strong>Resultado: {_format_num(result)}</strong>"
            "</div>"
        )

    raiz = re.search(r"(?:raiz\s+cuadrada|sqrt)\s*(?:de\s+)?(\d+(?:\.\d+)?)", lower)
    if raiz:
        num = float(raiz.group(1))
        result = math.sqrt(num)
        return (
            "<div class=\"math-box\">"
            f"<strong>Raiz cuadrada de {num}:</strong><br>"
            f"<code>sqrt({num}) = {result:.6g}</code>"
            "</div>"
        )

    if re.search(r"(?:factorial)\s*(?:de\s+)?(\d+)", lower):
        n = int(re.search(r"(?:factorial)\s*(?:de\s+)?(\d+)", lower).group(1))
        if n > 20:
            return "El factorial es demasiado grande para calcular. Intenta con un numero menor a 20."
        result = math.factorial(n)
        return (
            "<div class=\"math-box\">"
            f"<strong>Factorial de {n}:</strong><br>"
            f"<code>{n}! = {result}</code>"
            "</div>"
        )

    return None


def get_time_response(text):
    lower = normalize_text(text)
    now = datetime.now()

    if re.search(r"(?:que hora|hora es|que tiempo|hora actual)", lower):
        return f"Son las <strong>{now.strftime('%H:%M')}</strong> del dia {now.strftime('%d/%m/%Y')}."

    if re.search(r"(?:que fecha|fecha es|que dia|dia es|hoy que dia)", lower):
        dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        dia_semana = dias[now.weekday()]
        mes = meses[now.month - 1]
        return f"Hoy es <strong>{dia_semana} {now.day} de {mes} de {now.year}</strong>."

    return None


def analyze_text(text):
    lower = normalize_text(text)

    if re.search(r"(?:cuantas? letras|contar letras|longitud)", lower):
        match = re.search(r"(?:cuantas? letras|contar letras|longitud)\s*(?:tiene|tiene la palabra|de la palabra|de)\s+(\w+)", lower)
        if match:
            word = match.group(1)
            return f"La palabra <strong>\"{word}\"</strong> tiene <strong>{len(word)} letras</strong>."
        return "Escribe algo como 'cuantas letras tiene hola' para que pueda contarlas."

    if re.search(r"(?:cuantas? palabras|contar palabras)", lower):
        words = text.split()
        return f"El texto tiene <strong>{len(words)} palabras</strong>."

    if re.search(r"(?:invertir|al reves|revertir)", lower):
        match = re.search(r"(?:invertir|al reves|revertir)\s*(?:la palabra|el texto|la cadena)?\s*\"?(\w+)\"?", lower)
        if match:
            word = match.group(1)
            reversed_word = word[::-1]
            return f'La palabra "<strong>{word}</strong>" al reves es: <strong>"{reversed_word}"</strong>.'
        return "Escribe algo como 'invertir la palabra hola'."

    if re.search(r"(?:contar vocales|cuantas vocales)", lower):
        match = re.search(r"(?:contar vocales|cuantas vocales)\s*(?:tiene|de la palabra|en)\s+(\w+)", lower)
        if match:
            word = match.group(1)
            vocales = sum(1 for c in word.lower() if c in "aeiou")
            return f'La palabra "<strong>{word}</strong>" tiene <strong>{vocales} vocales</strong>.'
        return "Escribe algo como 'cuantas vocales tiene palabra'."

    if re.search(r"(?:contar consonantes|cuantas consonantes)", lower):
        match = re.search(r"(?:contar consonantes|cuantas consonantes)\s*(?:tiene|de la palabra|en)\s+(\w+)", lower)
        if match:
            word = match.group(1)
            consonantes = sum(1 for c in word.lower() if c.isalpha() and c not in "aeiou")
            return f'La palabra "<strong>{word}</strong>" tiene <strong>{consonantes} consonantes</strong>.'
        return "Escribe algo como 'cuantas consonantes tiene palabra'."

    return None


def translate_text(text, target="es"):
    """Translate text using free Google Translate API"""
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target}&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        parts = []
        for sentence in data[0]:
            if sentence[0]:
                parts.append(sentence[0])
        return "".join(parts) if parts else None
    except Exception as e:
        print(f"Translation error: {e}")
        return None


@app.route("/api/translate", methods=["POST"])
def api_translate():
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


def detect_intent(text, memory):
    lower = normalize_text(text)
    now = datetime.now()

    if re.search(r"(?:chiste|joke|reirme|divertirme)", lower):
        return random.choice(TECH_JOKE)

    draw_match = re.search(r"(?:dibuja|draw|pinta|dibujame)\s+(.+?)[\?\s]*$", lower)
    if draw_match:
        thing = draw_match.group(1).strip()
        return f"🖌️ **Voy a dibujar:** {thing}\n\n_Usa el boton de dibujo en el chat para verlo_"

    # Fuentes: buscar multiples fuentes
    fuentes_match = re.search(r"(?:fuentes?|sources?|buscar fuentes)\s*[:\-]?\s*(.+)", lower)
    if fuentes_match:
        query = fuentes_match.group(1).strip()
        if query:
            sources = search_all_sources(query)
            if sources:
                lines = [f"📚 **Fuentes para \"{query}\":**\n"]
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
        # Try our math solvers
        for solver in [solve_basic_equation, solve_basic_math, solve_advanced_math, solve_algebra, solve_logarithms]:
            result = solver(expr)
            if result:
                return result
        # Fallback: try to evaluate with safe eval
        try:
            safe = re.sub(r"(\d+)x\^?2", r"\1**2", expr.lower())
            safe = re.sub(r"(\d+)x", r"\1*", safe)
            safe = re.sub(r"(\d+)\s*=\s*(\d+)", r"", safe)
            safe_num = re.sub(r"[^\d\s\+\-\*/\(\)\.\%]", "", safe)
            if safe_num.strip():
                from math import log, log10, sqrt
                val = eval(safe_num, {"__builtins__": {}}, {"log": log, "log10": log10, "sqrt": sqrt})
                return f"Resultado: {_format_num(val)}"
        except:
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
                return f"**{flag} Traducción al {tgt}:**\n\n> {html_lib.escape(result)}"
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
    return f'🧠 Datos asimilados correctamente. Ahora se que **"{key}"** significa: "{value}".'


def extract_search_term(text):
    lower = normalize_text(text)
    stopwords = [
        "que", "es", "un", "una", "el", "la", "los", "las", "de", "del",
        "para", "como", "funciona", "significa", "hace", "sobre", "acerca",
        "cuales", "cual", "quien", "quienes", "donde", "cuando", "cuanto",
        "por que", "porque", "explica", "dame", "cuentame", "hablame",
        "dime", "quisiera", "saber", "informacion", "info", "datos",
        "es", "son", "esta", "estan", "hay", "puede", "pueden",
        "yo", "tu", "nosotros", "ellos", "esto", "eso", "eso",
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

    # Save to memory
    memory.setdefault("learned", {})[normalize_text(search_term)] = all_sources[0]["text"][:500]
    save_memory(memory)

    # Combine ALL sources with images
    lines = []
    added_image = False
    for src in all_sources:
        img = src.get("image")
        if img and auto_images and not added_image:
            lines.append(f'<img src="{img}" style="width:100%;max-width:350px;border-radius:12px;margin-bottom:12px;">')
            added_image = True

    lines.append(f"📚 **Fuentes para: {search_term.title()}**\n")

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

    # Add Wikipedia search results if we have none
    if not any(s.get("source") == "Wikipedia" for s in all_sources):
        search_results = search_wikipedia_search(search_term, limit=5 if deep_search else 2)
        if search_results:
            lines.append(f"**Más resultados de Wikipedia:**")
            for r in search_results[:3 if deep_search else 2]:
                lines.append(f"- **{r['title']}**: {r['snippet'][:100]}...")

    if deep_search:
        lines.append(f"\n*Búsqueda profunda activada - se mostraron más fuentes de lo normal*")

    lines.append("---\n📌 *¿Quieres que profundice en algo específico?*")
    return "\n".join(lines)





def format_reasoned_answer(answer, question, modelo="flask"):
    if answer is None:
        return None
    if "<div class=\"math-box\">" in answer or "<pre>" in answer:
        return answer

    if modelo == "flask":
        return f"🧠 **Analisis Flask:**<br><br>{answer}<br><br><em style='color:#98a8c3;'>Quieres que profundice en algo?</em>"
    if modelo == "gapi":
        return answer
    if modelo == "modify":
        return f"🔄 **Modify Code:**<br><br>{answer}"
    return answer


def _get_last_user_topic(history):
    """Get the last user message (non follow-up) from history"""
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
    """Check if last AI message asked about sources"""
    if not history:
        return False
    for h in reversed(history):
        if h.get("rol") == "ai":
            msg = h.get("texto", "")
            if "¿Quieres que busque fuentes" in msg:
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
        not l.strip().startswith("📌") and
        not l.strip().startswith("✏️") and
        "profundice" not in l.lower() and
        "quieres que" not in l.lower() and
        "dime" not in l.lower()
    )]
    return "\n".join(short[:5] + (["", "📌 *Modo conciso activado*"] if len(short) > 5 else []))


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

    # === FOLLOW-UP: "si" after being asked about sources → search all sources ===
    if asked_sources and lower in ["si", "sí", "yes", "ok", "dale", "adelante", "busca"]:
        topic = _get_last_user_topic(history)
        if topic:
            web_result = web_search_and_respond(topic, memory, auto_images, deep_search)
            if web_result:
                return (
                    f"🌐 **Fuentes web para \"{topic}\":**\n\n{web_result}\n\n"
                    f"---\n✏️ *¿Quieres que profundice? Dime 'paso a paso', 'ejemplo', 'código'.*"
                )
            return f"No encontré fuentes web para **\"{topic}\"**. Prueba con otro tema."
        return "¿Sobre qué tema quieres que busque fuentes?"

    # === FOLLOW-UP: "no" after being asked about sources → local only ===
    if asked_sources and lower in ["no", "nop", "no gracias", "no quiero", "no busques", "no hace falta"]:
        topic = _get_last_user_topic(history)
        if topic:
            concept_key = reasoning_search(topic)
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"📚 **{topic.title()}**\n\n"
                resp += f"**¿Qué es?** {data.get('what', '')}\n\n"
                if data.get("how"):
                    resp += f"**¿Cómo funciona?** {data['how']}\n\n"
                if data.get("purpose"):
                    resp += f"**¿Para qué sirve?** {data['purpose']}\n\n"
                if data.get("examples"):
                    resp += "**Ejemplos:**\n" + "\n".join(f"- `{e}`" for e in data["examples"][:3])
                return resp
            known = extract_known_answer(topic, memory)
            if known:
                return f"📚 **{topic.title()}:**\n\n{known}"
        return "De acuerdo. Pregúntame sobre otro tema o dime 'paso a paso', 'ejemplo', 'código'."

    # === FOLLOW-UP: structured (paso a paso, ejemplo, codigo) ===
    if lower in ["paso a paso", "ejemplo", "ejemplos", "codigo", "código", "caso uso", "casos de uso"]:
        last_topic = _get_last_user_topic(history)
        if last_topic:
            concept_key = reasoning_search(last_topic)
            if "ejemplo" in lower:
                if concept_key and CONCEPT_DB[concept_key].get("examples"):
                    exs = CONCEPT_DB[concept_key]["examples"]
                    return f"💡 **Ejemplos prácticos de {concept_key}:**\n\n" + "\n".join(f"- `{e}`" for e in exs)
                web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
                if web_result:
                    return f"💡 **Ejemplos desde la web para {last_topic}:**\n\n{web_result}"
            elif "codigo" in lower:
                if concept_key and CONCEPT_DB[concept_key].get("examples"):
                    exs = CONCEPT_DB[concept_key]["examples"]
                    return f"💻 **Código de {concept_key}:**\n\n" + "\n".join(f"- `{e}`" for e in exs)
                web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
                if web_result:
                    return f"💻 **Referencias de código para {last_topic}:**\n\n{web_result}"
            if concept_key:
                data = CONCEPT_DB[concept_key]
                resp = f"📚 **Guía paso a paso: {concept_key.title()}**\n\n"
                resp += f"**1. ¿Qué es?** {data.get('what', 'Concepto fundamental.')}\n\n"
                if data.get("how"):
                    resp += f"**2. ¿Cómo funciona?** {data['how']}\n\n"
                if data.get("purpose"):
                    resp += f"**3. ¿Para qué sirve?** {data['purpose']}\n\n"
                if data.get("examples"):
                    resp += "**4. Ejemplos prácticos:**\n"
                    for ex in data["examples"][:3]:
                        resp += f"   - `{ex}`\n"
                    resp += "\n"
                if data.get("difficulty"):
                    resp += f"**5. Nivel:** {data['difficulty']}\n\n"
                resp += "---\n✏️ *¿Quieres ver código real, casos de uso, o comparar con algo similar?*"
                return resp
            web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
            if web_result:
                return f"📚 **Estructurando información para {last_topic}:**\n\n{web_result}"
            return f"🤔 No tengo información estructurada para **\"{last_topic}\"**."
        return "¿Sobre qué tema quieres la explicación?"

    # === FOLLOW-UP: si/yes general deepening ===
    if lower in ["si", "sí", "yes", "dale", "adelante", "continua", "continúa", "mas", "más", "profundiza"]:
        last_topic = _get_last_user_topic(history)
        if last_topic:
            reasoning = reason_about(last_topic, memory)
            if reasoning:
                return f"🔍 **Profundizando en: {last_topic}**\n\n" + reasoning
            web_result = web_search_and_respond(last_topic, memory, auto_images, deep_search)
            if web_result:
                return f"🌐 **Más información sobre \"{last_topic}\":**\n\n{web_result}"
            return f"🤔 No tengo más información sobre **\"{last_topic}\"**."

    # === SIMPLE INTENTS (skip source asking) ===
    intent = detect_intent(text, memory)
    if intent:
        if "<div class=" in intent:
            return intent
        if user_name and any(w in lower for w in ["hola", "buenos", "buenas", "gracias"]):
            intent = intent.replace("Hola!", f"Hola {user_name}!").replace("Bienvenido", f"Bienvenido {user_name}")
        return f"{intent}\n\n💡 *Si quieres profundizar mas, solo pidemelo.*"

    if "quien eres" in lower:
        name_part = f", {user_name}" if user_name else ""
        return f"Soy **ANS Flask{name_part}**, el modo de razonamiento profundo de ANS AI. Creado por **Aldrin Nicolas Salazar Avilas**."

    if "creador" in lower:
        return "Mi creador es **Aldrin Nicolas Salazar Avilas**."

    # === MAIN FLOW: Ask about sources for EVERY question ===
    search_term = extract_search_term(text)
    if not search_term:
        search_term = text[:50]

    if auto_sources:
        # Auto mode: combine local + web sources
        web_result = web_search_and_respond(text, memory, auto_images, deep_search)
        concept_key = reasoning_search(text)
        if concept_key:
            data = CONCEPT_DB[concept_key]
            local_info = f"📚 **{concept_key.title()}:**\n{data.get('what', '')}\n"
            if data.get("purpose"):
                local_info += f"\n**Para qué sirve:** {data['purpose']}\n"
            if web_result:
                return (
                    f"🤔 **Información sobre \"{text}\":**\n\n"
                    f"{local_info}\n"
                    f"---\n"
                    f"📚 **Fuentes web automáticas:**\n\n{web_result}\n\n"
                    f"---\n✏️ *¿Quieres que profundice más?*"
                )
            return local_info + "\n\n---\n✏️ *¿Quieres que busque más fuentes web?*"
        if web_result:
            return (
                f"🌐 **Información web sobre \"{text}\":**\n\n{web_result}\n\n"
                f"---\n✏️ *¿Te gustaría que lo explique paso a paso?*"
            )
        reasoning = reason_about(text, memory)
        if reasoning:
            return f"🧠 **Análisis:**\n\n{reasoning}"
        known = extract_known_answer(text, memory)
        if known:
            return f"📚 **Conocimiento previo:**\n\n{known}"
        return f"🤔 No encontré información sobre **\"{text}\"** en ninguna fuente."

    # === AUTO-SOURCES OFF: Ask user if they want sources ===
    concept_key = reasoning_search(text)
    known = extract_known_answer(text, memory)
    reasoning = reason_about(text, memory)

    if concept_key or known or reasoning:
        return (
            f"🤔 Tengo información sobre **\"{text}\"** en mi base local.\n\n"
            f"📚 **¿Quieres que busque fuentes web (Wikipedia, DuckDuckGo, +100 curiosidades) para complementar?**\n\n"
            f"Responde **\"si\"** para buscar fuentes, o **\"no\"** para que responda con mi conocimiento local."
        )
    else:
        return (
            f"🤔 No tengo **\"{text}\"** en mi base local.\n\n"
            f"🌐 **¿Quieres que busque fuentes web (Wikipedia, DuckDuckGo, +100 datos) sobre esto?**\n\n"
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
        # Gapi returns concise version
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
        return f"{result}\n\n📝 *Gracias {user_name}, lo recordare!*"

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
        return random.choice([
            "De nada! Para eso estoy.",
            "Un placer ayudarte.",
            "Cuando quieras!",
        ])

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

    context_tip = ""
    if history:
        last_ai = [h for h in history[-3:] if h.get("rol") == "ai"]
        if last_ai:
            context_tip = "\n\n💬 *Siguiendo nuestra conversacion...*"

    return (
        f"Interesante! No tengo informacion sobre **\"{text}\"** aun.\n\n"
        f"Si quieres que lo aprenda, dime:\n"
        f"`aprende: {text} = lo que quieras que sepa`\n\n"
        f"O preguntame sobre otro tema!{context_tip}"
    )


@app.route("/api/chat", methods=["POST"])
def ai_chat():
    try:
        data = request.get_json(silent=True) or {}
        historial = data.get("historial", [])
        mensaje_nuevo = data.get("mensaje", "")
        modelo = normalize_text(data.get("modelo", "flask"))
        chat_id = data.get("chat_id", "")
        auto_sources = data.get("auto_sources", False)
        auto_images = data.get("auto_images", True)
        deep_search = data.get("deep_search", False)
        detallado = data.get("detallado", True)
        memory = load_memory()
        user = session.get("user", {})
        user_email = user.get("email", "")
        blocked = memory.get("blocked", [])
        if user_email in blocked:
            return jsonify({"respuesta": "Tu cuenta ha sido bloqueada por el administrador.", "modelo": "Bloqueado"}), 403

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

        respuesta = format_reasoned_answer(respuesta, mensaje_nuevo, modelo)
        return jsonify({"respuesta": respuesta, "modelo": modelo_nombre, "source": source})

    except Exception as e:
        print(f"Error critico en el nucleo: {e}")
        return jsonify({"respuesta": "Fallo en el nucleo neuronal. Revisa la terminal."}), 500


if __name__ == "__main__":
    print("--- Servidor ANS AI iniciado con motor local ---")
    app.run(debug=True)
