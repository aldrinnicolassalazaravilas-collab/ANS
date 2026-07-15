from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json
import os
import re
import unicodedata
import math
import random
import urllib.request
import urllib.parse
from datetime import datetime
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
MEMORY_FILE = BASE_DIR / "ans_memory.json"
USER_FILE = BASE_DIR / "ans_users.json"
HISTORY_DIR = BASE_DIR / "ans_history"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback")

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
    USER_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


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
    HISTORY_DIR.mkdir(exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
    path = HISTORY_DIR / f"{safe_id}_{modelo}.json"
    path.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


MODEL_INFO = {
    "flask": {
        "name": "ANS Flask",
        "description": "Razonamiento local, memoria, ecuaciones y respuestas paso a paso.",
    },
    "gapi": {
        "name": "ANS Gapi",
        "description": "Modo mas directo, ideal para consultas rapidas y base general.",
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
    for key in CONCEPT_DB:
        key_norm = normalize_text(key)
        if key_norm == term_lower:
            return key
        if term_lower in key_norm or key_norm in term_lower:
            score = len(key_norm) / max(len(term_lower), 1)
            if score > best_score:
                best_score = score
                best_key = key
        key_words = key_norm.split()
        term_words = term_lower.split()
        common = sum(1 for kw in key_words if kw in " ".join(term_words))
        if common >= 1 and len(key_words) > 0:
            ratio = common / len(key_words)
            if ratio > best_score:
                best_score = ratio
                best_key = key
    if best_key and best_score > 0.25:
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


@app.route("/api/history", methods=["GET"])
@login_required
def get_history():
    user = session.get("user", {})
    modelo = request.args.get("modelo", "flask")
    user_id = user.get("id", "anonymous")
    history = load_user_history(user_id, modelo)
    return jsonify({"history": history})


@app.route("/api/history", methods=["POST"])
@login_required
def save_history():
    user = session.get("user", {})
    data = request.get_json(silent=True) or {}
    modelo = data.get("modelo", "flask")
    historial = data.get("historial", [])
    user_id = user.get("id", "anonymous")
    save_user_history(user_id, modelo, historial)
    return jsonify({"ok": True})


@app.route("/api/history/clear", methods=["POST"])
@login_required
def clear_history():
    user = session.get("user", {})
    data = request.get_json(silent=True) or {}
    modelo = data.get("modelo", "flask")
    user_id = user.get("id", "anonymous")
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

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(url)


@app.route("/auth/google/callback")
def google_callback():
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


def exchange_code_for_token(code):
    try:
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
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
    return render_template("hm.html", user=user)


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
    MEMORY_FILE.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def solve_basic_equation(text):
    patterns = [
        r"^\s*(-?\d*)x\s*([+-])\s*(\d+)\s*=\s*(-?\d+)\s*$",
        r"^\s*(-?\d*)x\s*=\s*(-?\d+)\s*$",
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
        x = step1 / a

        return (
            "<div class=\"math-box\">"
            "<strong>📐 Ecuacion detectada</strong><br><br>"
            f"Ecuacion original: <code>{a}x {sign} {abs(int(raw_b))} = {c}</code><br><br>"
            f"<strong>Paso 1:</strong> Agrupar terminos independientes<br>"
            f"<code>{a}x = {c} - ({b})</code><br>"
            f"<code>{a}x = {step1}</code><br><br>"
            f"<strong>Paso 2:</strong> Despejar x<br>"
            f"<code>x = {step1} / {a}</code><br><br>"
            f"<strong>Resultado: x = {x}</strong>"
            "</div>"
        )

    match2 = re.search(patterns[1], text, re.IGNORECASE)
    if match2:
        raw_a = match2.group(1)
        raw_b = match2.group(2)
        a = 1 if raw_a in ("", "+") else -1 if raw_a == "-" else int(raw_a)
        b = int(raw_b)
        x = b / a

        return (
            "<div class=\"math-box\">"
            "<strong>📐 Ecuacion simple detectada</strong><br><br>"
            f"<code>{a}x = {b}</code><br>"
            f"<code>x = {b} / {a}</code><br><br>"
            f"<strong>Resultado: x = {x}</strong>"
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


def detect_intent(text, memory):
    lower = normalize_text(text)
    now = datetime.now()

    if re.search(r"(?:chiste|joke|reirme|divertirme)", lower):
        return random.choice(TECH_JOKE)

    if lower.startswith("aprende:"):
        return learn_fact(text, memory)

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

    best_match = None
    best_score = 0

    for source in (learned, KNOWLEDGE_BASE):
        for key, value in source.items():
            key_norm = normalize_text(key)
            if not key_norm:
                continue
            if key_norm in q:
                score = len(key_norm) / len(q) if len(q) > 0 else 0
                if score > best_score:
                    best_score = score
                    best_match = value
            elif q in key_norm:
                score = len(q) / len(key_norm) if len(key_norm) > 0 else 0
                if score > best_score:
                    best_score = score
                    best_match = value

    if best_match and best_score > 0.15:
        return best_match

    query_words = q.split()
    for source in (learned, KNOWLEDGE_BASE):
        for key, value in source.items():
            key_norm = normalize_text(key)
            if not key_norm:
                continue
            key_words = key_norm.split()
            matches = sum(1 for kw in key_words if any(w.startswith(kw[:4]) for w in query_words if len(kw) >= 4))
            if matches >= 1 and len(key_words) > 0:
                ratio = matches / len(key_words)
                if ratio > best_score:
                    best_score = ratio
                    best_match = value

    return best_match


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
    ]
    cleaned = re.sub(r"[?¿!¡.,;:]", "", lower)
    words = cleaned.split()
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
    return " ".join(filtered) if filtered else cleaned.strip()


def web_search_and_respond(text, memory):
    search_term = extract_search_term(text)
    if not search_term or len(search_term) < 2:
        return None

    wiki_data = search_wikipedia(search_term)
    if wiki_data and wiki_data.get("extract"):
        memory.setdefault("learned", {})[normalize_text(search_term)] = wiki_data["extract"][:500]
        save_memory(memory)
        return format_wiki_result(wiki_data)

    search_results = search_wikipedia_search(search_term)
    if search_results:
        lines = [f"**Resultados para \"{search_term}\":**\n"]
        for r in search_results[:3]:
            lines.append(f"- **{r['title']}**: {r['snippet'][:120]}...")
        lines.append(f"\nPuedo buscar mas detalles si me dices el tema exacto.")
        return "\n".join(lines)

    return None


def generate_smart_response(text, history, memory):
    lower = normalize_text(text)

    known = extract_known_answer(text, memory)
    if known:
        return f"{known}"

    web_result = web_search_and_respond(text, memory)
    if web_result:
        return web_result

    if history:
        recent = [h for h in history[-5:] if h.get("rol") == "ai" and len(h.get("texto", "")) > 20]
        if recent:
            return (
                f"No encontre una respuesta exacta en mi base de conocimiento para **\"{text}\"**. "
                f"Tambien busque en la red pero no encontre algo relevante. "
                f"Puedo aprenderla con el comando: `aprende: {text} = tu definicion`."
            )

    return (
        f"No tengo una respuesta exacta para **\"{text}\"** aun, "
        f"pero intente buscar en la red. Puedes ensenarmelo con: "
        f"`aprende: {text} = definicion`\n\n"
        f"O prueba preguntarme sobre tecnologia, programacion, hacer una suma, o decirme **ayuda**."
    )


def format_reasoned_answer(answer, question):
    if answer is None:
        return None
    if "<div class=\"math-box\">" in answer or "<pre>" in answer:
        return answer

    q = normalize_text(question)
    if "?" in question or q.startswith(("por que", "como", "explica", "analiza")):
        return f"<strong>Analisis:</strong><br><br>{answer}"
    return answer


def respond_with_flask_model(message, history, memory):
    text = message.strip()
    lower = normalize_text(text)

    if not text:
        return "Escribe una pregunta o un comando para comenzar. Di **ayuda** para ver lo que puedo hacer."

    intent = detect_intent(text, memory)
    if intent:
        return intent

    if "quien eres" in lower or "quien eres?" in lower or "ans ai" in lower:
        return (
            "Soy **ANS AI**, tu asistente virtual local creado por **Aldrin Nicolas Salazar Avilas**. "
            "Mi motor de razonamiento esta activo y funciono completamente sin internet para las consultas basicas. "
            "Puedo resolver matematicas, explicar conceptos, aprender cosas nuevas y mantener memoria persistente. "
            "Di **ayuda** para ver todo lo que puedo hacer."
        )

    if "creador" in lower or "quien te hizo" in lower or "quien te programo" in lower:
        return "Fui creado por **Aldrin Nicolas Salazar Avilas**, un desarrollador apasionado por la tecnologia y la inteligencia artificial."

    reasoning = reason_about(text, memory)
    if reasoning:
        return reasoning

    return generate_smart_response(text, history, memory)


def respond_with_gapi_model(message, history, memory):
    text = message.strip()
    lower = normalize_text(text)

    if not text:
        return "Escribe una pregunta para el modo rapido."

    intent = detect_intent(text, memory)
    if intent:
        return intent

    if "quien eres" in lower or "ans ai" in lower:
        return "Soy **ANS AI** en modo **Gapi**: respuestas directas y rapidas."

    if "hola" == lower or "saludos" == lower:
        return "Hola! Modo rapido activo. Preguntame lo que necesites."

    reasoning = reason_about(text, memory)
    if reasoning:
        return reasoning

    known = extract_known_answer(text, memory)
    if known:
        return f"{known}"

    web_result = web_search_and_respond(text, memory)
    if web_result:
        return web_result

    return (
        f"No encontre info sobre **\"{text}\"** en mi base ni en la red. "
        f"Puedes ensenarmelo con: `aprende: {text} = definicion`"
    )


@app.route("/api/chat", methods=["POST"])
def ai_chat():
    try:
        data = request.get_json(silent=True) or {}
        historial = data.get("historial", [])
        mensaje_nuevo = data.get("mensaje", "")
        modelo = normalize_text(data.get("modelo", "flask"))
        memory = load_memory()

        if modelo == "gapi":
            respuesta = respond_with_gapi_model(mensaje_nuevo, historial, memory)
            modelo_nombre = MODEL_INFO["gapi"]["name"]
        else:
            respuesta = respond_with_flask_model(mensaje_nuevo, historial, memory)
            modelo_nombre = MODEL_INFO["flask"]["name"]

        respuesta = format_reasoned_answer(respuesta, mensaje_nuevo)
        return jsonify({"respuesta": respuesta, "modelo": modelo_nombre})

    except Exception as e:
        print(f"Error critico en el nucleo: {e}")
        return jsonify({"respuesta": "Fallo en el nucleo neuronal. Revisa la terminal."}), 500


if __name__ == "__main__":
    print("--- Servidor ANS AI iniciado con motor local ---")
    app.run(debug=True)
