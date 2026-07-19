import re
import math
import html as html_lib
from ans.utils.helpers import normalize_text


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


def solve_basic_equation(text):
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
            f"<strong>Ecuacion detectada</strong><br><br>"
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
            f"<strong>Ecuacion simple detectada</strong><br><br>"
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
        f"<strong>Operacion:</strong> <code>{a} {op} {b}</code><br>"
        f"<strong>Resultado:</strong> <strong>{_format_num(result)}</strong>"
        "</div>"
    )


def solve_logarithms(text):
    lower = normalize_text(text)
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
                if "ln" in pattern:
                    formula = f"ln({match.group(1)})"
                elif "log10" in pattern:
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
                    f"<strong>Logaritmo</strong><br><br>"
                    f"<code>{formula} = {_format_num(result)}</code><br><br>"
                    f"<small>Base: {'e' if 'ln' in pattern or 'natural' in lower else '10' if 'log10' in pattern else '2' if 'log2' in pattern else '10'}</small>"
                    "</div>"
                )
            except (ValueError, ZeroDivisionError):
                return "No se puede calcular el logaritmo de ese numero (debe ser > 0)."
    return None


def solve_algebra(text):
    lower = normalize_text(text)

    vmatch = re.search(r"(?:^|\s|\d)([a-z])\s*(?:[+\-*/^]|$)", lower)
    _var = vmatch.group(1) if vmatch else "x"
    _evar = re.escape(_var)

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
                f"<strong>Ecuacion cuadratica</strong><br><br>"
                f"<code>{a}{_var} + {b}{_var} + {c} = 0</code><br><br>"
                f"Discriminante = {b} - 4({a})({c}) = {disc} < 0<br>"
                f"<strong>No tiene solucion real</strong> (raices complejas)"
                "</div>"
            )
        x1 = (-b + math.sqrt(disc)) / (2*a)
        x2 = (-b - math.sqrt(disc)) / (2*a)
        return (
            "<div class=\"math-box\">"
            f"<strong>Ecuacion cuadratica</strong><br><br>"
            f"<code>{a}{_var} + {b}{_var} + {c} = 0</code><br><br>"
            f"<strong>Formula general:</strong><br>"
            f"{_var} = [ -({b}) / sqrt({b} - 4*{a}*{c}) ] / (2*{a})<br><br>"
            f"Discriminante: {disc}<br><br>"
            f"<strong>{_var}1 = {_format_num(x1)}</strong><br>"
            f"<strong>{_var}2 = {_format_num(x2)}</strong>"
            "</div>"
        )

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
            f"<strong>Ecuacion con {_var} en ambos lados</strong><br><br>"
            f"<code>{a}{_var} {'+' if b >= 0 else '-'} {abs(int(b))} = {c}{_var} {'+' if d >= 0 else '-'} {abs(int(d))}</code><br><br>"
            f"<strong>Paso 1:</strong> Agrupar terminos con {_var}<br>"
            f"<code>{a}{_var} - {c}{_var} = {d} - ({b})</code><br>"
            f"<code>({a-c}){_var} = {d-b}</code><br><br>"
            f"<strong>Paso 2:</strong> Despejar {_var}<br>"
            f"<code>{_var} = {d-b} / {a-c}</code><br><br>"
            f"<strong>Resultado: {_var} = {_format_num(result)}</strong>"
            "</div>"
        )

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
                f"<strong>Combinacion de terminos</strong><br><br>"
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
            f"<strong>Combinacion de terminos semejantes</strong><br><br>"
            f"<code>{a}{_var} {'+' if b >= 0 else '-'} {abs(int(b))}{_var} = {c}</code><br><br>"
            f"<strong>Paso 1:</strong> Sumar coeficientes<br>"
            f"<code>({a} {'+' if b >= 0 else '-'} {abs(int(b))}){_var} = {c}</code><br>"
            f"<code>{combined}{_var} = {c}</code><br><br>"
            f"<strong>Paso 2:</strong> Despejar {_var}<br>"
            f"<code>{_var} = {c} / {combined}</code><br><br>"
            f"<strong>Resultado: {_var} = {_format_num(result)}</strong>"
            "</div>"
        )

    if "=" not in lower and len(text) < 30:
        num_var = r"\d+\s*" + _evar + r"\s*[+\-*/^]"
        var_op = r"(?:^|\s|\d)" + _evar + r"\s*[+\-*/^=]|[+\-*/^]\s*" + _evar
        if re.search(num_var, lower) or re.search(var_op, lower):
            esc = html_lib.escape(text.strip())
            return (
                "<div class=\"math-box\">"
                "<strong>Expresion algebraica detectada</strong><br><br>"
                f"Escribiste: <code>{esc}</code><br><br>"
                "Es una <strong>expresion algebraica</strong>, pero falta el <strong>=</strong> para resolverla.<br><br>"
                "<strong>Ejemplos completos:</strong><br>"
                f"<code>{esc} = 0</code><br>"
                f"<code>{esc} = 10</code><br><br>"
                "*Escribe la ecuacion completa (con =) para que la resuelva.*"
                "</div>"
            )

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
