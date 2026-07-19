import json
import urllib.parse
import urllib.request


def translate_text(text, target="es"):
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
