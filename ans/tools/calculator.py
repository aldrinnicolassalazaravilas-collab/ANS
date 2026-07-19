import re


def safe_calc(expr):
    safe = re.sub(r"(\d+)x\^?2", r"\1**2", expr.lower())
    safe = re.sub(r"(\d+)x", r"\1*", safe)
    from math import log, log10, sqrt
    safe_num = re.sub(r"[^\d\s\+\-\*/\(\)\.\%]", "", safe)
    if safe_num.strip():
        val = eval(safe_num, {"__builtins__": {}}, {"log": log, "log10": log10, "sqrt": sqrt})
        return val
    return None
