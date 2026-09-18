"""
Script de limpieza y preparación de datos
Censos Económicos 2024 – Región Occidente
Para exportación a Power BI

Archivos de entrada:
    tr_ce_col_2024.csv  → Colima
    tr_ce_jal_2024.csv  → Jalisco
    tr_ce_mich_2024.csv → Michoacán
    tr_ce_nay_2024.csv  → Nayarit

Archivos de salida:
    salida_powerbi/censo_occidente_2024.parquet
"""

import os
import warnings
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

ARCHIVOS = {
    "tr_ce_col_2024.csv":  "Colima",
    "tr_ce_jal_2024.csv":  "Jalisco",
    "tr_ce_mich_2024.csv": "Michoacán",
    "tr_ce_nay_2024.csv":  "Nayarit",
}

CARPETA_SALIDA = "salida_powerbi"

# ---------------------------------------------------------------------------
# MAPEO DE COLUMNAS REALES → NOMBRE LEGIBLE PARA POWER BI
# ---------------------------------------------------------------------------

COLUMNAS_INTERES = {
    # columna_real : nombre_powerbi
    "E03":    "clave_entidad",
    "E04":    "clave_municipio",
    "SECTOR": "sector",
    "SUBSECTOR": "subsector",
    "RAMA":   "rama",
    "SUBRAMA": "subrama",
    "CLASE":  "clase_actividad",
    "CODIGO": "codigo_actividad",
    "UE":     "unidades_economicas",
    "H001A":  "personal_ocupado_total",
    "H010A":  "personal_remunerado",
    "M000A":  "ingresos_totales",
    "K000A":  "gastos_totales",
    "J000A":  "remuneraciones_totales",
    "A111A":  "produccion_bruta_total",
    "A121A":  "consumo_intermedio",
    "A131A":  "valor_agregado_censal_bruto",
    "A211A":  "inversion_total",
    "Q000A":  "activos_fijos_netos",
}

# Textos que identifican filas de totales agregados (no granulares)
PATRONES_TOTAL = [
    "TOTAL",
    "TOTAL DE SECTOR",
    "TOTAL DE SUBSECTOR",
    "TOTAL DE RAMA",
    "TOTAL DE SUBRAMA",
    "TOTAL DE CLASE",
]


# ---------------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

def limpiar_nombre_columna(nombre: str) -> str:
    """Quita BOM, espacios, pasa a minúsculas y reemplaza espacios por '_'."""
    nombre = nombre.strip()
    nombre = nombre.replace("\ufeff", "")   # BOM
    nombre = nombre.replace("\xa0", " ")    # espacio duro
    nombre = nombre.lower()
    nombre = nombre.replace(" ", "_")
    return nombre


def leer_archivo(ruta: str, nombre_entidad: str) -> pd.DataFrame | None:
    """Lee un CSV de Censos Económicos y agrega la columna 'entidad'."""
    if not os.path.exists(ruta):
        warnings.warn(f"[AVISO] Archivo no encontrado, se omite: {ruta}")
        return None

    df = pd.read_csv(
        ruta,
        encoding="utf-8-sig",
        dtype=str,
        low_memory=False,
    )

    df.columns = [limpiar_nombre_columna(c) for c in df.columns]
    df.insert(0, "entidad", nombre_entidad)
    return df


def seleccionar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Conserva únicamente las columnas de interés que existan en el DataFrame."""
    mapeo_limpio = {
        limpiar_nombre_columna(k): v
        for k, v in COLUMNAS_INTERES.items()
    }

    columnas_presentes = {}
    for col_original, col_nuevo in mapeo_limpio.items():
        if col_original in df.columns:
            columnas_presentes[col_original] = col_nuevo

    cols_finales = ["entidad"] + list(columnas_presentes.keys())
    cols_finales = [c for c in cols_finales if c in df.columns]

    df = df[cols_finales].copy()
    renombrar = {k: v for k, v in columnas_presentes.items() if k in df.columns}
    df.rename(columns=renombrar, inplace=True)
    return df


def eliminar_totales(df: pd.DataFrame, col_codigo: str = "codigo_actividad") -> pd.DataFrame:
    """Elimina filas cuyo código de actividad corresponde a un total agregado."""
    if col_codigo not in df.columns:
        return df

    patrones_upper = [p.upper() for p in PATRONES_TOTAL]
    mascara_total = df[col_codigo].astype(str).str.strip().str.upper().isin(patrones_upper)
    n_eliminadas = mascara_total.sum()
    if n_eliminadas > 0:
        print(f"  Eliminadas {n_eliminadas:,} filas de totales agregados.")
    return df[~mascara_total].copy()


def convertir_numericas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte a numérico todas las columnas que no sean
    identificadores de texto (entidad, códigos, claves de texto).
    """
    cols_texto = {
        "entidad", "clave_entidad", "clave_municipio", "mun_estado_geo",
        "sector", "subsector", "rama", "subrama",
        "clase_actividad", "codigo_actividad",
    }
    for col in df.columns:
        if col not in cols_texto:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def preparar_censo(archivos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Conserva el esquema y las reglas de limpiar2.py; exige todas las columnas y formatea las claves."""
    cols_interes_valores = list(COLUMNAS_INTERES.values())
    idx_mun = cols_interes_valores.index("clave_municipio") + 1
    cols_ordenadas = cols_interes_valores[:idx_mun] + ["mun_estado_geo"] + cols_interes_valores[idx_mun:]
    columnas_esperadas = ["entidad"] + cols_ordenadas

    resultado = []
    for entidad, original in archivos.items():
        df = original.copy()
        df.columns = [limpiar_nombre_columna(c) for c in df.columns]

        # Filtrar solo ID_ESTRATO nulo para evitar duplicación por desglose de estrato
        if "id_estrato" in df.columns:
            df = df[df["id_estrato"].isna()].copy()

        faltantes = [c for c in COLUMNAS_INTERES if limpiar_nombre_columna(c) not in df]
        if faltantes:
            raise ValueError(f"{entidad}: faltan columnas del censo: {', '.join(faltantes)}")

        df.insert(0, "entidad", entidad)
        df = seleccionar_columnas(df)

        # Limpiar espacios en columnas de texto
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({"nan": None, "": None, "None": None, "<NA>": None})

        # Formatear claves geográficas con ceros iniciales
        if "clave_entidad" in df.columns:
            df["clave_entidad"] = df["clave_entidad"].apply(
                lambda x: str(int(float(x))).zfill(2) if x and str(x) != "None" else None
            )
        if "clave_municipio" in df.columns:
            df["clave_municipio"] = df["clave_municipio"].apply(
                lambda x: str(int(float(x))).zfill(3) if x and str(x) != "None" else None
            )

        # Crear mun_estado_geo (5 dígitos) para vinculación con DENUE en Power BI
        mask_mun = df["clave_entidad"].notna() & df["clave_municipio"].notna()
        df["mun_estado_geo"] = None
        df.loc[mask_mun, "mun_estado_geo"] = df.loc[mask_mun, "clave_entidad"] + df.loc[mask_mun, "clave_municipio"]

        df = df.dropna(how="all", subset=[c for c in df if c not in ("entidad", "clave_entidad", "clave_municipio", "mun_estado_geo")])
        df = eliminar_totales(df).drop_duplicates()
        df = convertir_numericas(df)

        df = df[columnas_esperadas]
        resultado.append(df)

    if not resultado:
        raise ValueError("No hay archivos censales para procesar.")
    final = pd.concat(resultado, ignore_index=True).drop_duplicates()
    if list(final.columns) != columnas_esperadas:
        raise ValueError("El orden de columnas del censo no coincide con limpiar2.py.")
    return final


def main():
    print("=" * 60)
    print("Censos Económicos 2024 – Limpieza para Power BI")
    print("=" * 60)

    todos_los_df = []
    columnas_detectadas_global = set()

    for nombre_archivo, nombre_entidad in ARCHIVOS.items():
        print(f"\n📂 Procesando: {nombre_archivo} ({nombre_entidad})")

        df = leer_archivo(nombre_archivo, nombre_entidad)
        if df is None:
            continue

        cols_raw = set(df.columns) - {"entidad"}
        columnas_detectadas_global.update(cols_raw)

        df = seleccionar_columnas(df)
        cols_sin_entidad = [c for c in df.columns if c != "entidad"]
        df.dropna(how="all", subset=cols_sin_entidad, inplace=True)
        df = eliminar_totales(df)
        df.drop_duplicates(inplace=True)
        df = convertir_numericas(df)
        todos_los_df.append(df)

    if not todos_los_df:
        print("\n[ERROR] No se pudo leer ningún archivo.")
        return

    df_final = pd.concat(todos_los_df, ignore_index=True).drop_duplicates()
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_parquet = os.path.join(CARPETA_SALIDA, "censo_occidente_2024.parquet")
    df_final.to_parquet(ruta_parquet, index=False)
    print(f"\n📊 Filas finales: {len(df_final):,}, Columnas: {len(df_final.columns)}")
    print(f"💾 Guardado en {os.path.abspath(ruta_parquet)}")


if __name__ == "__main__":
    main()
