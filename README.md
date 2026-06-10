# 🔶 Connect Assistance México — Análisis Operativo del Portafolio de Clientes

> Dashboard estratégico que transforma los reportes mensuales de Sage Intacct en análisis operativo profundo del portafolio de carteras de Connect.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

## 🎯 ¿Qué analiza?

| # | Módulo | Pregunta que responde |
|---|--------|-----------------------|
| 0 | Concentración de revenue | ¿Alguna cartera tiene demasiado peso? |
| 1 | Clientes activos | ¿Crecen o se pierden clientes por cartera? |
| 2 | Servicios y temporalidad | ¿En qué meses se dispara la demanda? |
| 3 | Frecuencia de uso | ¿Qué carteras tienen alta usabilidad? ¿Coinciden los picos? |
| 4 | Costo promedio por servicio | ¿Hay inflación operativa sistemática? |
| 5 | Loss Ratio histórico | ¿Qué carteras están por encima del objetivo? |
| 6 | Revenue y GP por cliente | ¿Cuánto genera y cuesta cada certificado? |
| 7 | Optimización Markowitz | ¿Cuál es la distribución óptima del portafolio? |
| 8 | Señales de acción | CRÍTICA / REVISAR / MONITOREAR / SANA por cartera |
| 9 | Síntesis ejecutiva | Narrativa automática con hallazgos y próximos pasos |

---

## 📂 ¿Qué archivos subir?

El reporte mensual de Sage Intacct:

```
KPIs - Actuals vs Budget by Segment.xlsx
KPIs - Actuals vs Forecast by Segment.xlsx   ← también funciona
```

- Sube **todos los meses disponibles juntos** — la app los procesa en un clic
- Cuantos más meses, más preciso el análisis (mínimo 3, óptimo 24)
- La app siempre lee la columna **Actual** — ignora Budget y Forecast

---

## 🔄 Actualización mensual

Cada mes después del cierre contable (~día 10):
1. Exporta el reporte KPIs de Sage Intacct
2. Abre la app, arrastra el archivo nuevo junto con los anteriores
3. El análisis se recalcula automáticamente

---

## ⚙️ Instalación local

```bash
git clone https://github.com/FernandoLealC/connect-portafolio-clientes.git
cd connect-portafolio-clientes
pip install -r requirements.txt
streamlit run app.py
```

---

## 🚀 Despliegue en Streamlit Cloud

1. [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Selecciona este repositorio → archivo principal: `app.py`
3. Clic en **Deploy** — listo en ~2 minutos

### Restringir acceso al equipo Connect:
Streamlit Cloud → Settings → Sharing → *"Only specific people"* → agregar correos `@connect.pr`

---

## 🛠️ Stack

Python · Streamlit · Pandas · NumPy · Plotly · Matplotlib · OpenPyXL

---

*Connect Assistance México · Universidad Panamericana · IA para el Análisis Financiero*
