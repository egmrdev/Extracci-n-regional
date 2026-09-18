# Extracción Regional INEGI · Streamlit App

Aplicación web interactiva para descargar los datos del **DENUE** y de los **Censos Económicos** preparados y optimizados para **Power BI**.

---

## 📁 Estructura del Repositorio

- `app.py`: Aplicación principal de Streamlit (punto de entrada).
- `preparar_datos.py`: Módulo de descarga y empaquetado automático.
- `limpiar.py`: Reglas de limpieza y columnas derivadas para el **DENUE**.
- `limpiar2.py`: Reglas de limpieza y compactación para los **Censos Económicos**.
- `denue.py`: Conector para la API/Catálogo del INEGI.
- `proyecciones_region.parquet`: Base de proyecciones regionales de población.
- `csv-de-power.csv`: Esquema de 29 columnas para Power BI.
- `requirements.txt`: Dependencias del proyecto.
- `data/entregables/`: Paquetes ZIP preparados con archivos `.parquet` descargables.

---

## 🚀 Pasos para publicar en GitHub y Streamlit Cloud

### 1. Subir la carpeta a GitHub
1. Abre tu terminal en esta carpeta (`github_streamlit`):
   ```bash
   git init
   git add .
   git commit -m "Inicializar app de Streamlit"
   ```
2. Crea un nuevo repositorio en GitHub (público o privado).
3. Conecta y sube el repositorio:
   ```bash
   git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   git branch -M main
   git push -u origin main
   ```

### 2. Desplegar en Streamlit Community Cloud
1. Ve a [share.streamlit.io](https://share.streamlit.io).
2. Inicia sesión con tu cuenta de GitHub.
3. Haz clic en **"New app"**.
4. Selecciona tu repositorio y rama (`main`).
5. En **Main file path**, ingresa: `app.py`.
6. Haz clic en **"Deploy!"**.

¡Tu aplicación estará en línea en pocos segundos!
