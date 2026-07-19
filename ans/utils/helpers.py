import re
import unicodedata
from datetime import datetime


def normalize_text(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


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
