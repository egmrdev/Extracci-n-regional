"""Dos extracciones independientes, basadas en los scripts del proyecto."""
import json
import zipfile

import streamlit as st

from preparar_datos import prepare

st.set_page_config(page_title='Extracción regional · INEGI', page_icon='◈', layout='centered')
st.markdown('''<style>
.block-container {padding-top:3rem;max-width:760px}
h1 {letter-spacing:-1.3px}
</style>''', unsafe_allow_html=True)

st.title('Extracción regional')
st.write('Elige el producto y descarga su archivo preparado para Power BI.')

option = st.radio(
    'Producto',
    ['DENUE', 'Censos Económicos'],
)
kind = 'denue' if option == 'DENUE' else 'censo'

@st.cache_data(show_spinner=False)
def load_package(product_kind):
    path = prepare(product_kind)
    bytes_data = path.read_bytes()
    with zipfile.ZipFile(path) as package:
        meta = json.loads(package.read('procedencia.json'))
    return bytes_data, path.name, meta

try:
    with st.spinner('Cargando los datos oficiales…'):
        data_bytes, file_name, meta = load_package(kind)
    st.success(f'Listo: {meta["filas"]:,} filas · {len(meta["columnas"])} columnas')
    st.download_button(
        'Extraer',
        data=data_bytes,
        file_name=file_name,
        mime='application/zip',
        type='primary',
        use_container_width=True,
    )
    st.caption('El ZIP contiene únicamente archivos Parquet y procedencia para la opción elegida.')
    if kind == 'denue':
        st.caption('DENUE limitado a los municipios de la base regional. Las columnas derivadas se calculan con limpiar.py.')
except Exception as exc:
    st.error(f'No se pudo preparar {option}: {exc}')
