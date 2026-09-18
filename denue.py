"""Descarga DENUE desde el catálogo público que utiliza la web de INEGI."""
from __future__ import annotations

import base64
import json
import re
import shutil
import uuid
from contextlib import contextmanager
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
STATES = {'Colima': '06', 'Jalisco': '14', 'Michoacán': '16', 'Nayarit': '18'}
SITE = 'https://www.inegi.org.mx'
CATALOG = SITE + '/app/api/descarga/descarga/descargamasiva/lista/'
FIELDS = ['id', 'nom_estab', 'raz_social', 'codigo_act', 'nombre_act', 'per_ocu',
          'tipo_vial', 'nom_vial', 'numero_ext', 'nomb_asent', 'cod_postal',
          'entidad', 'municipio', 'localidad', 'telefono', 'correoelec', 'www',
          'latitud', 'longitud', 'fecha_alta']


@contextmanager
def staging_directory():
    # Hereda los permisos del proyecto, también cuando se ejecuta en Windows.
    path = DATA / ('download_' + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).lower())
                   if unicodedata.category(c) != 'Mn')


def session():
    s = requests.Session()
    s.headers['User-Agent'] = 'DENUE-Occidente/1.0 (consulta de datos publicos)'
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504], allowed_methods=['GET', 'POST'])))
    return s


def latest_release(state, client):
    # La página carga el listado con estas consultas JSON; no requiere token.
    page = client.get(SITE + '/app/descarga/', timeout=(15, 90))
    page.raise_for_status()
    match = re.search(r'data-id="denue"[^>]*data-tinfo="(\d+)"', page.text)
    if not match:
        raise ValueError('Cambió el catálogo de INEGI: no se encontró la sección DENUE.')
    payload = dict(tinfo=match[1], ag=STATES[state], prog='0', cc='0', subtema='0',
                   anio='0', formato='0', datosAbiertos='3', textoBuscar='', ingles='0',
                   tipoInfo='OTROS', titulo=base64.b64encode(b'Otros|DENUE|').decode())
    response = client.post(CATALOG + 'obtenerarchivos', json=payload, timeout=(15, 90))
    response.raise_for_status()
    candidates = []
    for row in response.json():
        period = row['titulo'].split('|')[-1]
        date = re.fullmatch(r'(\d{4})(?:/(\d{2}))?', period)
        if not date:
            continue
        for fmt, ext in zip(row['formatos'].split('|'), row['extensiones'].split('|')):
            if fmt == 'csv':
                url = SITE + '/contenidos' + row['pathLogico'] + ext.split('&')[0]
                if urlparse(url).hostname != 'www.inegi.org.mx' or not url.endswith('.zip'):
                    raise ValueError('Enlace de descarga inesperado.')
                candidates.append(((int(date[1]), int(date[2] or 1)),
                                   {'state': state, 'period': period, 'url': url}))
    if not candidates:
        raise ValueError(f'No se encontraron archivos CSV para {state}.')
    return max(candidates, key=lambda item: item[0])[1]


def read_csv(stream):
    for encoding in ['utf-8-sig', 'cp1252', 'latin1']:
        stream.seek(0)
        try:
            frame = pd.read_csv(stream, encoding=encoding, dtype=str, keep_default_na=False)
            frame.columns = [c.strip().lower().lstrip('\ufeff') for c in frame.columns]
            if not {'id', 'nom_estab', 'codigo_act'}.issubset(frame.columns):
                raise ValueError('El CSV no tiene el esquema de establecimientos del DENUE.')
            return frame
        except UnicodeDecodeError:
            continue
    raise ValueError('No se pudo interpretar la codificación del CSV.')


def download_state(state, refresh=False, report=lambda message: None):
    DATA.mkdir(exist_ok=True)
    destination = DATA / f'denue_{STATES[state]}.parquet'
    metadata = destination.with_suffix('.json')
    if destination.exists() and metadata.exists() and not refresh:
        return json.loads(metadata.read_text(encoding='utf-8'))
    with session() as client:
        report(f'{state}: consultando catálogo oficial…')
        info = latest_release(state, client)
        report(f'{state}: descargando edición {info["period"]}…')
        with staging_directory() as temp:
            archive = Path(temp) / 'denue.zip'
            with client.get(info['url'], stream=True, timeout=(15, 180)) as response:
                response.raise_for_status()
                with archive.open('wb') as output:
                    for chunk in response.iter_content(1024 * 1024):
                        output.write(chunk)
            report(f'{state}: validando y preparando datos…')
            frames = []
            with zipfile.ZipFile(archive) as package:
                for entry in package.infolist():
                    if entry.filename.lower().endswith('.csv') and 'diccionario' not in entry.filename.lower():
                        with package.open(entry) as stream:
                            frames.append(read_csv(stream))
            if not frames:
                raise ValueError(f'El archivo de {state} no contiene datos CSV.')
            frame = pd.concat(frames, ignore_index=True).drop_duplicates('id')
            if frame.empty:
                raise ValueError(f'El archivo de {state} está vacío.')
            if 'cve_ent' in frame and not frame['cve_ent'].str.zfill(2).eq(STATES[state]).all():
                raise ValueError('El archivo contiene registros de otra entidad.')
            frame['estado'] = state
            info.update(rows=len(frame), downloaded_at=datetime.now(timezone.utc).isoformat())
            staging = Path(temp) / 'data.parquet'
            frame.to_parquet(staging, index=False)
            staging.replace(destination)
            staging_meta = Path(temp) / 'meta.json'
            staging_meta.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
            staging_meta.replace(metadata)
            return info


def inventory():
    result = []
    for state, code in STATES.items():
        path = DATA / f'denue_{code}.json'
        if path.exists() and path.with_suffix('.parquet').exists():
            result.append(json.loads(path.read_text(encoding='utf-8')))
    return result


def load_data(states):
    frames = []
    for state in states:
        path = DATA / f'denue_{STATES[state]}.parquet'
        if path.exists():
            frame = pd.read_parquet(path)
            frames.append(frame.reindex(columns=FIELDS + ['estado'], fill_value=''))
    if not frames:
        return pd.DataFrame(columns=FIELDS + ['estado', '_search'])
    frame = pd.concat(frames, ignore_index=True).fillna('')
    for col in ['latitud', 'longitud']:
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    frame['_search'] = (frame.nom_estab + ' ' + frame.nombre_act + ' ' + frame.raz_social).map(normalized)
    return frame


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    for state in STATES:
        result = download_state(state, refresh=args.refresh, report=lambda text: print(text, flush=True))
        print(f'{state}: {result["rows"]:,} establecimientos ({result["period"]})', flush=True)
