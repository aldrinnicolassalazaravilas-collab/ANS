def generate_svg(query):
    query = query.lower().strip()
    if not query:
        return ""

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
    if any(w in query for w in ["circulo", "circle", "pelota", "bola", "esfera"]):
        svg = f'<svg width="200" height="200"><circle cx="100" cy="100" r="60" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Circulo</text></svg>'
    elif any(w in query for w in ["cuadrado", "square", "caja", "rectangulo"]):
        svg = f'<svg width="200" height="200"><rect x="30" y="30" width="140" height="140" rx="8" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Cuadrado</text></svg>'
    elif any(w in query for w in ["triangulo", "triángulo", "triangle"]):
        svg = f'<svg width="200" height="200"><polygon points="100,20 180,160 20,160" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="115" text-anchor="middle" fill="white" font-size="14">Triangulo</text></svg>'
    elif any(w in query for w in ["estrella", "star"]):
        svg = f'<svg width="200" height="200"><polygon points="100,20 120,80 180,80 130,120 150,180 100,150 50,180 70,120 20,80 80,80" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Estrella</text></svg>'
    elif any(w in query for w in ["casa", "house", "hogar"]):
        svg = f'<svg width="220" height="200"><rect x="60" y="80" width="100" height="100" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><polygon points="30,80 110,20 190,80" fill="{stroke_color}" stroke="#f59e0b" stroke-width="2"/><rect x="90" y="120" width="40" height="60" fill="#131c2f" stroke="#f59e0b" stroke-width="2"/></svg>'
    elif any(w in query for w in ["corazon", "corazón", "heart", "amor"]):
        svg = f'<svg width="200" height="200"><path d="M100,170 C40,120 10,70 50,30 C70,10 100,30 100,50 C100,30 130,10 150,30 C190,70 160,120 100,170Z" fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="12">Corazon</text></svg>'
    elif any(w in query for w in ["hexagono", "hexágono", "hexagon"]):
        svg = f'<svg width="200" height="200"><polygon points="100,15 175,55 175,145 100,185 25,145 25,55" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Hexagono</text></svg>'
    elif any(w in query for w in ["pentagono", "pentágono", "pentagon"]):
        svg = f'<svg width="200" height="200"><polygon points="100,15 170,70 140,175 60,175 30,70" fill="{fill_color}" stroke="{stroke_color}" stroke-width="3"/><text x="100" y="105" text-anchor="middle" fill="white" font-size="14">Pentagono</text></svg>'
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

    return svg
