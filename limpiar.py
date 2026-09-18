import re
import unicodedata
import pandas as pd
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────
DIR = Path(__file__).parent
ARCHIVOS_DENUE = ["colima.csv", "jalisco.csv", "michoacan.csv", "nayarit.csv"]
REFERENCIA = "csv-de-power.csv"
SALIDA = "denue_consolidado.parquet"
ANIO_ACTUAL = 2026

ENCODINGS = ["utf-8", "latin1", "utf-8-sig"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def leer_csv(ruta: Path) -> pd.DataFrame:
    for enc in ENCODINGS:
        try:
            df = pd.read_csv(ruta, encoding=enc, low_memory=False)
            print(f"  [{ruta.name}] leído con '{enc}' — {len(df):,} filas")
            return df
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"No se pudo leer '{ruta.name}' con ninguno de: {ENCODINGS}")


def quitar_acentos(texto: str) -> str:
    """Normaliza NFD y elimina marcas diacríticas (tildes, diéresis, etc.)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


# Patrones ordenados de más específico a más general.
# Se evalúan contra nombre_act con re.search() ignorando mayúsculas y acentos.
# NOTA: No usar \b al final de palabras que tienen plural en español (hotel→hoteles).
_PATRONES_GIRO = [
    # ── Alimentos preparados ──────────────────────────────────────────────────
    (r"taquería|tacos?",                                    "🌮 Taquería"),
    (r"antojito|cenaduría|cenadur",                         "🌭 Antojitos / Cenaduría"),
    (r"tortillería|tortilla",                               "🌯 Tortillería"),
    (r"panadería|pastelería|repostería|pan dulce",          "🥖 Panadería"),
    (r"helados?|paletería|nievería|paleta de hielo",        "🍦 Heladería / Paletería"),
    (r"dulcería|confitería|botana|frituras",                "🍬 Dulcería / Botanas"),
    (r"pizza|hamburguesa|hot.?dog|alitas",                  "🍕 Pizza / Hamburguesas"),
    (r"marisquería|mariscos?|pescado",                      "🐟 Mariscos"),
    (r"carnicería|carne roja|carne de ave|carne de cerdo",  "🥩 Carnicería"),
    (r"cafetería|café |nevería",                            "☕ Cafetería / Nevería"),
    (r"restaurante|fonda |comedor",                         "🍽️ Restaurante"),
    (r"preparación de alimentos|alimentos para consumo inmediato|comida para llevar", "🍽️ Comida rápida / Fonda"),
    (r"abarrote|ultramarino|miscelánea|tienda de barri",    "🛍️ Abarrotes / Minisuper"),
    (r"frutas?|verduras?",                                  "🥬 Frutas y verduras"),
    (r"lácteos?|leche |embutido|queso",                     "🥛 Lácteos / Embutidos"),
    (r"semilla|grano alimenticio|especias?|chile seco",     "🌾 Semillas / Especias"),
    (r"otros alimentos|alimentos varios",                   "🛒 Tienda de alimentos"),
    (r"purificad|embotellado de agua",                      "💧 Purificadora de agua"),
    (r"vinos?|licores?|bebidas? alcohólica",                "🍷 Vinos y licores"),
    (r"bebidas? no alcohólica|refresco|agua embotellada",   "🥤 Bebidas"),
    (r"cabañas?|villas?|similares|alojamiento temporal",    "🏡 Cabañas / Villas"),
    (r"hoteles?|motel|hostal",                              "🏨 Hotel / Hospedaje"),
    # ── Ropa / calzado / accesorios ──────────────────────────────────────────
    (r"calzado|zapatos?|zapatería",                         "👟 Zapatería"),
    (r"bisutería|accesorios de vestir|sombreros?",          "💍 Bisutería / Accesorios"),
    (r"joyería|relojes?|platería",                          "💎 Joyería / Relojería"),
    (r"óptica|lentes?",                                     "👓 Óptica"),
    (r"lencería|blancos|ropa de cama",                      "🛏️ Lencería / Blancos"),
    (r"mercería|bonetería|costura|telas?",                  "🧵 Mercería / Telas"),
    (r"disfraces?|vestido de novia|vestimenta regional",    "👗 Disfraces / Novias"),
    (r"ropa |prendas?|boutique",                            "👕 Tienda de ropa"),
    # ── Salud ─────────────────────────────────────────────────────────────────
    (r"farmacia|medicamentos?|droguería",                   "💊 Farmacia"),
    (r"dentista|odontolog",                                 "🦷 Dentista"),
    (r"laboratorio.*médico|diagnóstico clínico",            "🔬 Laboratorio clínico"),
    (r"psicolog",                                           "🧠 Psicología"),
    (r"nutriólog|dietista",                                 "🥗 Nutriólogo"),
    (r"audiolog|terapia ocupacional|terapia física|terapia del lenguaje", "🦻 Terapia / Rehabilitación"),
    (r"naturista|homeopát|complemento alimenticio",         "🌿 Naturista / Homeopático"),
    (r"médico|hospitales?|clínicas?|consultorio",           "🩺 Médico / Clínica"),
    # ── Educación ─────────────────────────────────────────────────────────────
    (r"guardería|maternal |estancia infantil",              "👶 Guardería"),
    (r"kinder|preescolar",                                  "👶 Guardería / Kinder"),
    (r"idiomas?|inglés|francés",                            "🌐 Idiomas"),
    (r"biblioteca|archivo.*público",                        "📚 Biblioteca"),
    (r"escuela|colegio|academia|instituto.*educac|universidad", "🏫 Escuela"),
    # ── Belleza ───────────────────────────────────────────────────────────────
    (r"estética|barbería|peluquería|salón de belleza|manicura|spa",     "✂️ Estética / Barbería"),
    (r"perfumería|cosméticos?",                             "💄 Perfumería / Cosméticos"),
    (r"lavandería|tintorería",                              "🧺 Lavandería"),
    # ── Construcción / ferretería ─────────────────────────────────────────────
    (r"ferretería|tlapaler",                                "🔨 Ferretería"),
    (r"cemento|tabique|grava|ladrillos?|block |materiales? de construc|materiales? para construc", "🧱 Materiales de construcción"),
    (r"pisos?|recubrimiento cerámico|azulejo",              "🏠 Pisos / Recubrimientos"),
    (r"vidrios?|espejos?|vidrierí",                         "🪟 Vidrios y espejos"),
    (r"hojalatería|pintura.*autom|enderezado|carrocería|tapicería.*auto|cristales.*auto", "🔧 Taller carrocería"),
    (r"instalación.*eléctric|eléctric.*instalación|instalaciones eléctricas", "🔌 Instalaciones eléctricas"),
    (r"pinturería|pintura",                                 "🎨 Pinturería"),
    (r"herrería|estructura metálica|soldadura|metalistería", "⚒️ Herrería"),
    (r"carpintería|aserrado|tablones?",                     "🪚 Carpintería / Madera"),
    (r"muebles?|mueblería",                                 "🛋️ Mueblería"),
    (r"plomería|plomero",                                   "🔧 Plomería"),
    (r"edificación|construcción.*vivienda|vivienda.*unifamiliar|obra.*urbanización|urbanización", "🏗️ Construcción"),
    # ── Autos / transporte ───────────────────────────────────────────────────
    (r"refaccion|autopart",                                 "🚗 Refacciones autom."),
    (r"llantas?|cámara.*auto|vulcanizad",                   "🔧 Vulcanizadora / Llantas"),
    (r"aceites?.*lubricante|grasas? lubricante|aditivo.*vehículo", "🔧 Lubricantes / Aceites"),
    (r"alineación|balanceo",                                "🔧 Alineación / Balanceo"),
    (r"eléctrico.*auto|eléctrico.*camion",                  "🔌 Eléctrico automotriz"),
    (r"taller.*mecáni|mecánica.*auto|reparación.*auto|reparación.*camion", "🔧 Taller mecánico"),
    (r"automóviles?.*usados?|camionetas?.*usadas?",         "🚗 Venta de autos"),
    (r"gasolina|diesel|gas l[. ]*p|combustibles?",           "⛽ Gasolinera / Gas"),
    (r"motocicletas?|moto ",                                "🏍️ Motocicletas"),
    (r"bicicletas?|cicl",                                   "🚲 Bicicletas"),
    (r"lavado.*auto|carwash",                               "🚿 Lavado de autos"),
    # ── Comercio general ─────────────────────────────────────────────────────
    (r"regalos?|recuerdos?|souvenir",                       "🎁 Regalos / Recuerdos"),
    (r"artículos? religiosos?",                             "⛪ Artículos religiosos"),
    (r"artesanías?",                                        "🧶 Artesanías"),
    (r"papelería|librerías?",                               "📔 Papelería"),
    (r"revistas?|periódicos?",                              "📰 Revistas / Periódicos"),
    (r"imprenta|tipografía|serigrafía|fotocopiado|impres",  "🖨️ Imprenta / Copiado"),
    (r"artículos? deportivos?|deportivos?|deportes?",       "⚽ Artículos deportivos"),
    (r"juguetes?|juguetería",                               "🎮 Juguetería"),
    (r"bazar |usados?|segunda mano",                        "♻️ Bazar / Usado"),
    (r"electrodoméstico|línea blanca|aparato.*eléctrico.*hogar", "🏠 Electrodomésticos"),
    (r"cómputo|equipo.*cómputo|mobiliario.*cómputo|computadora",  "💻 Cómputo / Equipos"),
    (r"equipo.*eléctrico|material eléctrico",               "🔌 Material eléctrico"),
    (r"maquinaria|equipo.*industrial|maquinado",            "⚙️ Maquinaria / Equipo"),
    (r"teléfonos?|celulares?|telecom.*menor",               "📱 Telefonía"),
    (r"cristalería|loza |utensilios de cocina",             "🏺 Cristalería / Cocina"),
    (r"decoración.*interior|artículos? de decorac",         "🖼️ Decoración"),
    (r"floristería|florería|flores?",                       "🌸 Florería"),
    (r"desechables?|artículos? de limpieza|productos? de limpieza", "🧽 Desechables / Limpieza"),
    (r"mascotas?|acuario",                                  "🐾 Mascotas"),
    (r"servicios? veterinarios?|veterinario|veterinaria",   "🐾 Veterinaria"),
    (r"artículos? de uso personal|otros artículos? de uso", "🛒 Artículos personales"),
    (r"albercas?|artículos? para alberca",                  "🏊 Albercas"),
    # ── Servicios profesionales ──────────────────────────────────────────────
    (r"contabilidad|auditoría|contador",                    "📊 Contabilidad"),
    (r"jurídico|abogados?|notaría|bufete|trámites? legales", "⚖️ Bufete jurídico"),
    (r"diseño gráfico",                                     "🎨 Diseño gráfico"),
    (r"arquitectura|diseño.*interior|urbanismo",            "🏗️ Arquitectura / Diseño"),
    (r"fotografía|videograbación|estudio.*fotog",           "📸 Fotografía / Video"),
    (r"consultoría|asesoría",                               "📋 Consultoría"),
    (r"telecomunicacion|internet.*servicio|datos.*servicio|alámbric|inalámbric", "📡 Telecomunicaciones"),
    (r"ciber |café.*internet|acceso.*computadora",          "💻 Ciber / Internet"),
    (r"agencia.*viaje|turismo |tour ",                      "✈️ Agencia de viajes"),
    (r"estacionamiento|pensión.*vehículo",                  "🅿️ Estacionamiento"),
    (r"cerrajería",                                         "🔑 Cerrajería"),
    (r"funeraria|servicios? funerar",                       "⚰️ Funeraria"),
    (r"sanitarios? públicos?|bolerías?",                    "💈 Bolería / Sanitarios"),
    (r"billares?",                                          "🎱 Billar"),
    (r"salón.*fiestas|banquetes?|eventos? ",                "🎉 Salón de fiestas"),
    (r"gimnasio|fitness|yoga|pilates",                      "🏋️ Gimnasio"),
    (r"juegos? electrónicos?|videojuego|arcade",            "🎮 Videojuegos"),
    (r"renta.*mesa|renta.*silla|alquiler.*vajilla|alquiler.*evento", "🎊 Renta de eventos"),
    (r"alquiler|arrendamiento",                             "🔑 Arrendamiento"),
    (r"servicios? personales",                              "💈 Servicios personales"),
    # ── Comercio especializado adicional ─────────────────────────────────────
    (r"supermercados?|autoservicio",                        "🛒 Supermercado"),
    (r"tienda departamental",                               "🏪 Tienda departamental"),
    (r"instrumento.*musical|música.*instrumento",           "🎵 Instrumentos musicales"),
    (r"discos?|casetes?|dvd|música.*menor",                 "🎵 Música / Discos"),
    (r"libros?.*menor|librería",                            "📚 Librería"),
    (r"cigarros?|puros?|tabaco",                            "🚬 Tabaco / Cigarros"),
    (r"artículos? ortopédicos?|ortopedia",                  "🦽 Ortopedia"),
    (r"automóviles?.*nuevos?|camionetas?.*nuevas?",         "🚗 Venta de autos"),
    # ── Servicios especializados adicionales ──────────────────────────────────
    (r"profesores? particulares?|clases particulares?",     "👩‍🏫 Clases particulares"),
    (r"publicidad|rotulación|agencia.*publicidad",          "📢 Publicidad"),
    (r"ingeniería",                                         "⚙️ Ingeniería"),
    (r"servicios? postales?|correos?",                      "📮 Correo / Postal"),
    (r"grúas?|servicio.*grúa",                              "🚛 Grúa"),
    (r"aduanal|aduana",                                     "📦 Agencia aduanal"),
    (r"centro.*cambiario|cambio.*divisa|cambio.*moneda",    "💱 Centro cambiario"),
    (r"seguridad.*privada|protección.*custodia|monitoreo.*seguridad", "🔒 Seguridad privada"),
    (r"pensión.*huésped|casa.*huésped",                     "🏨 Pensión / Huéspedes"),
    (r"recreativos?|esparcimiento",                         "🎭 Entretenimiento"),
    (r"parque acuático|balneario",                          "🏊 Parque acuático"),
    (r"billar",                                             "🎱 Billar"),
    (r"administración.*negocio|servicios? de administración","📋 Administración"),
    (r"rectificación.*motor|rectificadora",                 "🔧 Rectificadora de motor"),
    (r"tapicería.*auto|tapicería.*camion",                  "🔧 Tapicería automotriz"),
    (r"orientación.*social|trabajo social|servicio.*niñez|servicio.*juventud", "🤝 Trabajo social"),
    (r"residencia.*adicción|trastorno mental|adicción",     "🏥 Clínica de adicciones"),
    (r"asilo|residencia.*ancianos?|adultos? mayores?",      "🏥 Asilo / Adultos mayores"),
    (r"alimentación comunitaria|comedor.*público",          "🍽️ Comedor comunitario"),
    (r"medio ambiente|preservación.*ambiente",              "🌿 Medio ambiente"),
    (r"alimentos? para animales",                           "🐾 Alimentos para animales"),
    (r"elaboración.*hielo",                                 "🧊 Fábrica de hielo"),
    (r"tequila|mezcal|destilad",                            "🥃 Destilería / Tequilera"),
    (r"radio|estación.*transmisión|radiodifusión",          "📻 Radio"),
    # ── Finanzas ─────────────────────────────────────────────────────────────
    (r"bancas?|bancos?|institución.*bancaria",              "🏦 Banco"),
    (r"caja.*ahorro|cooperativa.*ahorro|unión.*crédito",    "💰 Caja de ahorro"),
    (r"casa.*empeño|empeño",                                "💍 Casa de empeño"),
    (r"seguros?|aseguradora",                               "📋 Seguros"),
    (r"inmobiliaria|bienes raíces|corredor.*inmob",         "🏠 Inmobiliaria"),
    # ── Reparaciones ─────────────────────────────────────────────────────────
    (r"reparación.*electrónica|mantenimiento.*electrónico", "📺 Reparación electrónica"),
    (r"reparación.*electrodoméstico|aparato.*eléctrico.*repar", "🔌 Reparación electrodomésticos"),
    (r"reparación.*hogar|mantenimiento.*hogar",             "🏠 Reparación del hogar"),
    (r"reparación.*industri|mantenimiento.*máquin",         "⚙️ Mantenimiento industrial"),
    (r"reparación.*moto|taller.*moto",                      "🏍️ Taller de motos"),
    # ── Entretenimiento ──────────────────────────────────────────────────────
    (r"música|academia.*danza|teatro |cultura |arte ",      "🎭 Arte / Cultura"),
    # ── Gobierno / social ────────────────────────────────────────────────────
    (r"seguridad.*orden|cuerpo.*policía|policía",           "👮 Seguridad pública"),
    (r"impartición.*justicia|regulación.*desarrollo|fomento.*desarrollo", "🏛️ Gobierno"),
    (r"gobierno|administración.*públic|municipal|federal",  "🏛️ Gobierno"),
    (r"iglesia|templo |asociación.*religiosa|culto ",       "⛪ Iglesia / Asociación"),
    (r"autoayuda|adiccion|alcohólico|grupo.*apoyo",         "🤝 Grupo de autoayuda"),
    (r"bienestar.*social|asistencia.*social",               "🏛️ Bienestar social"),
    # ── Agropecuario ─────────────────────────────────────────────────────────
    (r"pesca |acuacultura|acuícola|camarones?",             "🐟 Pesca / Acuacultura"),
    (r"avicultura|pollos?|gallina|huevos?",                 "🐔 Avicultura"),
    (r"apicultura|abejas?|mieles?",                         "🍯 Apicultura"),
    (r"forestal|madera.*bosque",                            "🌲 Forestal"),
    (r"ganadería|ganados?|bovino|porcino|ovino",            "🐄 Ganadería"),
    (r"fertili|plaguicida|semilla.*siembra",                "🌱 Insumos agrícolas"),
    (r"agricultur|cultivos?|siembra|cosecha",               "🌾 Agricultura"),
    # ── Agua / energía ───────────────────────────────────────────────────────
    (r"captación.*agua|suministro.*agua|tratamiento.*agua", "💧 Agua potable"),
    (r"refinería|petróleo|petroquímica",                    "🛢️ Petróleo / Refinería"),
    (r"electricidad|generación.*eléctric|energía eléctrica","⚡ Energía eléctrica"),
    (r"minería|extracción.*mineral",                        "⛏️ Minería"),
    (r"desecho|residuos?|reciclaj|remediación",             "♻️ Reciclaje / Residuos"),
    # ── Industria / manufactura ──────────────────────────────────────────────
    (r"alfarería|cerámica|porcelana",                       "🏺 Alfarería / Cerámica"),
    (r"textil|confección|bordado",                          "🧵 Textil / Confección"),
    (r"otras industrias|industrias manufactureras",         "🏭 Manufactura"),
    (r"fabricación|manufactura|industria",                  "🏭 Manufactura"),
    # ── Transporte ───────────────────────────────────────────────────────────
    (r"transportes?|fletes?|mensajería|paquetería|mudanza", "🚚 Transporte / Mensajería"),
    (r"ductos?|gasoducto|oleoducto",                        "🛢️ Transporte por ductos"),
]

# Compila los patrones una sola vez para eficiencia
_RE_GIRO = [(re.compile(p, re.IGNORECASE), etiq) for p, etiq in _PATRONES_GIRO]


def giro_por_keywords(nombre_act: str) -> str:
    """Clasifica un negocio usando palabras clave de su actividad económica."""
    if not nombre_act or pd.isna(nombre_act):
        return "📌 Otros"
    texto = unicodedata.normalize("NFC", str(nombre_act))
    for patron, etiqueta in _RE_GIRO:
        if patron.search(texto):
            return etiqueta
    return "📌 Otros"


def cat_scian(codigo) -> str:
    """Fallback: categoría según los 2 primeros dígitos del código SCIAN."""
    codigo_limpio = str(codigo).strip() if pd.notna(codigo) else ""
    sector = codigo_limpio[:2] if codigo_limpio.isdigit() else "00"
    mapa = {
        "11": "Agropecuario",   "21": "Minería",           "22": "Energía",
        "23": "Construcción",   "31": "Manufactura",        "32": "Manufactura",
        "33": "Manufactura",    "43": "Comercio mayorista", "46": "Comercio minorista",
        "48": "Transporte",     "49": "Transporte",         "51": "Información/Media",
        "52": "Finanzas",       "53": "Inmobiliario",       "54": "Serv. profesionales",
        "55": "Corporativos",   "56": "Serv. apoyo negocio","61": "Educación",
        "62": "Salud",          "71": "Entretenimiento",    "72": "Alimentos y hospedaje",
        "81": "Otros servicios","93": "Gobierno",
    }
    return mapa.get(sector, "Otros servicios")


# ── Derivación de columnas ────────────────────────────────────────────────────

PER_OCU_TAMANO = {
    "0 a 5 personas":    "Micro",
    "6 a 10 personas":   "Micro",
    "11 a 30 personas":  "Pequeño",
    "31 a 50 personas":  "Pequeño",
    "51 a 100 personas": "Mediano",
    "101 a 250 personas":"Mediano",
    "251 y más personas":"Grande",
}
PER_OCU_NUM = {
    "0 a 5 personas":    3,
    "6 a 10 personas":   8,
    "11 a 30 personas":  20,
    "31 a 50 personas":  40,
    "51 a 100 personas": 75,
    "101 a 250 personas":175,
    "251 y más personas":300,
}


def derivar_columnas(df: pd.DataFrame, mapa_giro: dict, mapa_cat: dict) -> pd.DataFrame:
    """
    Calcula las 14 columnas que existen en la referencia pero no en los CSV del DENUE.
    Se ejecuta ANTES de descartar las columnas originales del DENUE, porque varias
    derivaciones las necesitan (localidad, municipio, entidad, per_ocu, etc.).
    """

    # ── 1. Geografía: renombrar columnas DENUE → nombres de la referencia ────
    # Los CSV del DENUE usan 'localidad', 'municipio', 'entidad';
    # la referencia los llama 'nom_loc', 'nom_mun', 'nom_ent'.
    df["nom_loc"] = df["localidad"].fillna("").astype(str).str.strip()
    df["nom_mun"] = df["municipio"].fillna("").astype(str).str.strip()
    df["nom_ent"] = df["entidad"].fillna("").astype(str).str.strip()

    # ── 2. Tamaño de negocio y número de personal ─────────────────────────────
    # 'per_ocu' es texto ("0 a 5 personas", etc.); se mapea a etiqueta y número.
    df["tamano_negocio"] = df["per_ocu"].map(PER_OCU_TAMANO).fillna("Sin dato")
    df["personal_num"]   = df["per_ocu"].map(PER_OCU_NUM).astype("Int64")

    # ── 3. Año de alta y antigüedad ───────────────────────────────────────────
    # 'fecha_alta' viene en formato 'AAAA-MM'; se extrae solo el año.
    df["año_alta"] = (
        pd.to_datetime(df["fecha_alta"], format="%Y-%m", errors="coerce").dt.year
        .astype("Int64")
    )
    df["antiguedad_anios"] = (ANIO_ACTUAL - df["año_alta"]).astype("Int64")

    # Rango de antigüedad en tres tramos, igual que la referencia.
    def _rango(n):
        if pd.isna(n):  return None
        if n <= 3:      return "0-3 años"
        if n <= 10:     return "4-10 años"
        return "Más de 10 años"

    df["rango_antiguedad"] = df["antiguedad_anios"].apply(_rango)

    # ── 4. Combinación municipio + estado + país ───────────────────────────────
    df["mun_estado_geo"] = df["nom_mun"] + ", " + df["nom_ent"] + ", Mexico"

    # ── 5. Giro comercial (con emoji) y categoría ─────────────────────────────
    # Prioridad:
    #   1. Lookup directo por codigo_act (944 códigos extraídos de la referencia).
    #   2. Clasificador por palabras clave sobre nombre_act (cubre ~804 códigos restantes).
    #   3. Fallback genérico "📌 Otros".
    giro_lookup = df["codigo_act"].map(mapa_giro).astype(object)
    # Aplica keywords cuando: (a) el código no está en la referencia, o
    # (b) la referencia lo clasifica genéricamente como "Otros".
    mascara_mejorar = giro_lookup.isna() | (giro_lookup == "📌 Otros (ver lista completa)")
    giro_lookup[mascara_mejorar] = df.loc[mascara_mejorar, "nombre_act"].apply(giro_por_keywords)
    df["Giro Comercial"] = giro_lookup

    df["categoria"] = (
        df["codigo_act"].map(mapa_cat)
        .fillna(df["codigo_act"].apply(cat_scian))
    )

    # ── 6. Palabras clave ─────────────────────────────────────────────────────
    # Concatena nombre del establecimiento + actividad económica,
    # todo en minúsculas y sin tildes, para búsquedas en Power BI.
    nom_l  = df["nom_estab"].fillna("").astype(str).str.lower().apply(quitar_acentos)
    act_l  = df["nombre_act"].fillna("").astype(str).str.lower().apply(quitar_acentos)
    df["palabras_clave"] = nom_l + " " + act_l

    # ── 7. Dirección formateada ───────────────────────────────────────────────
    # Formato: "TIPO_VIAL NOM_VIAL NUMERO_EXT, COLONIA, CP CODIGO_POSTAL"
    num_ext = df["numero_ext"].fillna("").astype(str).str.strip()
    cp      = df["cod_postal"].fillna("").astype(str).str.strip()
    df["direccion"] = (
        df["tipo_vial"].fillna("").astype(str) + " " +
        df["nom_vial"].fillna("").astype(str)  + " " +
        num_ext + ", " +
        df["nomb_asent"].fillna("").astype(str) + ", CP " + cp
    )

    # ── 8. Buscador inteligente ───────────────────────────────────────────────
    # Combina: palabras_clave (sin comas) + nombre_act original (sin comas) +
    # nombre del establecimiento en minúsculas.
    # Al incluir la versión con y sin tildes, el buscador de PBI encuentra
    # resultados independientemente de si el usuario escribe con acento o no.
    pc_limpio  = df["palabras_clave"].str.replace(",", "", regex=False)
    act_orig   = df["nombre_act"].fillna("").astype(str).str.replace(",", "", regex=False)
    nom_lower  = df["nom_estab"].fillna("").astype(str).str.lower()
    df["buscador_inteligente"] = " " + pc_limpio + " " + act_orig + " " + nom_lower + " "

    return df


def alinear_esquema(df: pd.DataFrame, referencia: pd.DataFrame, nombre: str) -> pd.DataFrame:
    """Elimina columnas extra, crea las faltantes (ya deben estar derivadas) y reordena."""
    columnas_ref = list(referencia.columns)

    extra = [c for c in df.columns if c not in columnas_ref]
    if extra:
        print(f"  [{nombre}] Descartando {len(extra)} col(s) extra")
    df = df.drop(columns=extra)

    faltantes = [c for c in columnas_ref if c not in df.columns]
    if faltantes:
        print(f"  [{nombre}] Columnas sin derivar (se dejan vacías): {faltantes}")
    for col in faltantes:
        df[col] = pd.Series(index=df.index, dtype=referencia[col].dtype)

    return df[columnas_ref]


def preparar_denue(archivos: dict[str, pd.DataFrame], referencia: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aplica las derivaciones originales a los cuatro estados.

    Sin referencia se conservan las columnas DENUE y las derivadas por este script.
    Con referencia se usa exactamente su orden y nombres de columnas.
    """
    requeridas = {"id", "codigo_act", "nombre_act", "nom_estab", "localidad",
                  "municipio", "entidad", "per_ocu", "fecha_alta", "tipo_vial",
                  "nom_vial", "numero_ext", "nomb_asent", "cod_postal"}
    mapa_giro, mapa_cat = {}, {}
    if referencia is not None:
        if referencia.columns.duplicated().any():
            raise ValueError("La referencia contiene columnas duplicadas.")
        for col in ["codigo_act", "Giro Comercial", "categoria"]:
            if col not in referencia:
                raise ValueError(f"Falta la columna {col} en la referencia.")
        mapa_giro = (referencia.dropna(subset=["codigo_act", "Giro Comercial"])
                     .drop_duplicates("codigo_act").set_index("codigo_act")["Giro Comercial"].to_dict())
        mapa_cat = (referencia.dropna(subset=["codigo_act", "categoria"])
                    .drop_duplicates("codigo_act").set_index("codigo_act")["categoria"].to_dict())
    resultado = []
    for estado, original in archivos.items():
        faltantes = sorted(requeridas - set(original.columns))
        if faltantes:
            raise ValueError(f"{estado}: faltan columnas DENUE: {', '.join(faltantes)}")
        df = original.drop(columns=["estado"], errors="ignore").copy()
        if df["id"].duplicated().any():
            df = df.drop_duplicates("id")
        df["codigo_act"] = df["codigo_act"].astype(str).str.strip()
        df = derivar_columnas(df, mapa_giro, mapa_cat)
        if referencia is not None:
            df = alinear_esquema(df, referencia, estado)
        resultado.append(df)
    if not resultado:
        raise ValueError("No hay archivos DENUE para procesar.")
    return pd.concat(resultado, ignore_index=True)


def main():
    referencia = DIR / REFERENCIA
    if not referencia.exists():
        raise FileNotFoundError(f"Falta {REFERENCIA}; la aplicación puede procesar sin referencia.")
    archivos = {nombre: leer_csv(DIR / nombre) for nombre in ARCHIVOS_DENUE if (DIR / nombre).exists()}
    salida = preparar_denue(archivos, leer_csv(referencia))
    salida.to_parquet(DIR / SALIDA, index=False, engine="pyarrow")
    print(f"Guardado: {DIR / SALIDA} ({len(salida):,} filas)")


if __name__ == "__main__":
    main()
