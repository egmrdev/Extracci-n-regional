"""Genera los dos entregables de Power BI usando limpiar.py y limpiar2.py."""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

import limpiar
import limpiar2
from denue import DATA, STATES, download_state, inventory, session

OUTPUT = DATA / 'entregables'
PROJECTIONS = Path(__file__).resolve().parent / 'proyecciones_region.parquet'
if not PROJECTIONS.exists():
    PROJECTIONS = Path(__file__).resolve().parent / 'proyecciones_region_original.parquet'
CENSO_CODES = {'Colima': 'col', 'Jalisco': 'jal', 'Michoacán': 'mich', 'Nayarit': 'nay'}
CENSO_BASE = 'https://www.inegi.org.mx/contenidos/programas/ce/2024/datosabiertos/'
DENUE_DERIVED = ['nom_loc', 'nom_mun', 'nom_ent', 'tamano_negocio', 'personal_num',
                 'año_alta', 'antiguedad_anios', 'rango_antiguedad', 'mun_estado_geo',
                 'Giro Comercial', 'categoria', 'palabras_clave', 'direccion',
                 'buscador_inteligente']
PROJECTION_COLUMNS = ['CLAVE', 'CLAVE_ENT', 'NOM_ENT', 'NOM_MUN', 'SEXO', 'ANO',
                      'POB_TOTAL', 'POB_00_04', 'POB_05_09', 'POB_010_014',
                      'POB_015_019', 'POB_20_24', 'POB_25_29', 'POB_30_34',
                      'POB_35_39', 'POB_40_44', 'POB_45_49', 'POB_50_54',
                      'POB_55_59', 'POB_60_64', 'POB_65_69', 'POB_70_74',
                      'POB_75_79', 'POB_80_84', 'POB_85_mm', 'fecha',
                      'etiqueta_estado']


def censo_url(code):
    return CENSO_BASE + f'conjunto_de_datos_ce_{code}_2024_csv.zip'


def ensure_censo_sources(refresh=False, report=lambda message: None):
    DATA.mkdir(exist_ok=True)
    with session() as client:
        for state, code in CENSO_CODES.items():
            path = DATA / f'censo_2024_{code}.zip'
            if path.exists() and not refresh:
                continue
            report(f'Descargando Censos 2024: {state}…')
            staged = path.with_suffix('.download')
            with client.get(censo_url(code), stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                with staged.open('wb') as target:
                    for chunk in response.iter_content(1024 * 1024):
                        target.write(chunk)
            with zipfile.ZipFile(staged) as source:
                expected = f'conjunto_de_datos/tr_ce_{code}_2024.csv'
                if expected not in source.namelist():
                    staged.unlink(missing_ok=True)
                    raise ValueError(f'{state}: el ZIP no contiene {expected}.')
            staged.replace(path)


def read_censo_sources():
    frames = {}
    for state, code in CENSO_CODES.items():
        with zipfile.ZipFile(DATA / f'censo_2024_{code}.zip') as source:
            with source.open(f'conjunto_de_datos/tr_ce_{code}_2024.csv') as stream:
                frame = pd.read_csv(stream, dtype=str, low_memory=False)
        if not frame['E03'].dropna().eq(STATES[state]).all():
            raise ValueError(f'{state}: clave de entidad incorrecta en archivo censal.')
        frames[state] = frame
    return frames


def read_projection_base():
    if not PROJECTIONS.exists():
        raise FileNotFoundError(f'Falta la base regional: {PROJECTIONS.name}')
    frame = pd.read_parquet(PROJECTIONS)
    if list(frame.columns) != PROJECTION_COLUMNS:
        raise ValueError('Cambió el orden o los nombres de las 27 columnas de proyecciones.')
    if frame.empty or frame[PROJECTION_COLUMNS].isna().any().any():
        raise ValueError('La base de proyecciones está vacía o tiene campos nulos.')
    state_codes = set(pd.to_numeric(frame.CLAVE_ENT, errors='raise').astype(int))
    unknown = state_codes - {int(code) for code in STATES.values()}
    if unknown:
        raise ValueError(f'La base de proyecciones contiene estados no configurados: {sorted(unknown)}')
    return frame


def read_denue_sources(states):
    return {state: pd.read_parquet(DATA / f'denue_{code}.parquet')
            for state, code in STATES.items() if state in states}


def limit_denue_to_projection_base(frames, projections):
    """Usa CLAVE municipal de proyecciones para delimitar los establecimientos."""
    allowed = set(pd.to_numeric(projections.CLAVE, errors='raise').astype(int))
    selected = {}
    found = set()
    for state, frame in frames.items():
        for col in ('cve_ent', 'cve_mun'):
            if col not in frame:
                raise ValueError(f'{state}: falta {col} para relacionar con proyecciones.')
        key = pd.to_numeric(frame.cve_ent.str.zfill(2) + frame.cve_mun.str.zfill(3),
                            errors='coerce')
        mask = key.isin(allowed)
        selected[state] = frame.loc[mask].copy()
        found.update(key.loc[mask].astype(int).unique())
    missing = allowed - found
    if missing:
        raise ValueError(f'Faltan {len(missing)} municipios de proyecciones en DENUE.')
    return selected


def validate_denue(frame, source_frames, ref_df=None):
    if ref_df is not None:
        expected = list(ref_df.columns)
    else:
        raw_cols = [c for c in next(iter(source_frames.values())).columns if c != 'estado']
        expected = raw_cols + DENUE_DERIVED
    if list(frame.columns) != expected:
        raise ValueError('El orden de columnas DENUE no coincide con limpiar.py.')
    if frame['id'].duplicated().any():
        raise ValueError('Hay establecimientos DENUE duplicados.')


def validate_censo(frame):
    cols_interes_valores = list(limpiar2.COLUMNAS_INTERES.values())
    idx_mun = cols_interes_valores.index("clave_municipio") + 1
    expected = ["entidad"] + cols_interes_valores[:idx_mun] + ["mun_estado_geo"] + cols_interes_valores[idx_mun:]
    if list(frame.columns) != expected:
        raise ValueError('El orden de columnas censales no coincide con limpiar2.py.')
    if set(frame.entidad.dropna()) != set(CENSO_CODES):
        raise ValueError('Faltan estados en el censo consolidado.')


def write_outputs(kind, frame, sources, projections=None):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = 'DENUE' if kind == 'denue' else 'censo_occidente_2024'
    destination = OUTPUT / f'{base}.zip'
    staged = destination.with_suffix('.download')
    with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as target:
        extra = {}
        if kind == 'denue':
            if projections is None:
                raise ValueError('Falta la base regional para crear la descarga DENUE.')
            extra = {'municipios_base': int(projections.CLAVE.nunique()),
                     'relacion_geografica': 'CLAVE = cve_ent (2 dígitos) + cve_mun (3 dígitos).'}
            # Incluir únicamente el parquet de proyecciones_region
            pob_pq_buf = io.BytesIO()
            projections.to_parquet(pob_pq_buf, index=False)
            target.writestr('proyecciones_region.parquet', pob_pq_buf.getvalue())

            # Incluir únicamente el parquet de DENUE
            denue_pq_buf = io.BytesIO()
            frame.to_parquet(denue_pq_buf, index=False)
            target.writestr('DENUE.parquet', denue_pq_buf.getvalue())
        else:
            censo_pq_buf = io.BytesIO()
            frame.to_parquet(censo_pq_buf, index=False)
            target.writestr(f'{base}.parquet', censo_pq_buf.getvalue())

        target.writestr('procedencia.json', json.dumps({
            'producto': kind, 'fuentes': sources, 'filas': len(frame),
            'columnas': list(frame.columns),
            'generado_utc': datetime.now(timezone.utc).isoformat(),
            **extra,
        }, ensure_ascii=False, indent=2))
    if destination.exists():
        try:
            destination.unlink()
        except Exception:
            pass
    try:
        staged.replace(destination)
    except PermissionError:
        import time
        time.sleep(1)
        if destination.exists():
            try:
                destination.unlink()
            except Exception:
                pass
        staged.replace(destination)
    return destination


def prepare(kind, refresh=False, report=lambda message: None):
    """Devuelve un ZIP con archivos Parquet; conserva el archivo anterior si falla."""
    if kind not in {'denue', 'censo'}:
        raise ValueError('Producto desconocido.')
    DATA.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    base = 'proyecciones_regionales_denue' if kind == 'denue' else 'censo_occidente_2024'
    destination = OUTPUT / f'{base}.zip'
    if destination.exists() and not refresh:
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(destination.stat().st_mtime, timezone.utc)
        current = kind != 'denue'
        if kind == 'denue' and PROJECTIONS.exists() and PROJECTIONS.stat().st_mtime <= destination.stat().st_mtime:
            with zipfile.ZipFile(destination) as package:
                names = set(package.namelist())
            current = f'{base}.csv' in names and f'{base}.parquet' in names
        if age < timedelta(days=30) and current:
            return destination
    if kind == 'denue':
        projections = read_projection_base()
        selected_states = [state for state, code in STATES.items()
                           if int(code) in set(projections.CLAVE_ENT.astype(int))]
        for state in selected_states:
            download_state(state, refresh=refresh, report=report)
        originals = limit_denue_to_projection_base(read_denue_sources(selected_states), projections)
        report('Aplicando las reglas de limpiar.py…')
        ref_path = limpiar.DIR / limpiar.REFERENCIA
        ref_df = limpiar.leer_csv(ref_path) if ref_path.exists() else None
        frame = limpiar.preparar_denue(originals, ref_df)
        validate_denue(frame, originals, ref_df)
        sources = inventory()
    else:
        ensure_censo_sources(refresh=refresh, report=report)
        originals = read_censo_sources()
        report('Aplicando las reglas de limpiar2.py…')
        frame = limpiar2.preparar_censo(originals)
        validate_censo(frame)
        sources = [censo_url(code) for code in CENSO_CODES.values()]
    report(f'Empaquetando {len(frame):,} filas y {len(frame.columns)} columnas…')
    return write_outputs(kind, frame, sources, projections if kind == 'denue' else None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('producto', choices=['denue', 'censo', 'ambos'])
    cli.add_argument('--refresh', action='store_true')
    args = cli.parse_args()
    for product in (['denue', 'censo'] if args.producto == 'ambos' else [args.producto]):
        path = prepare(product, refresh=args.refresh, report=lambda message: print(message, flush=True))
        print(path, flush=True)
