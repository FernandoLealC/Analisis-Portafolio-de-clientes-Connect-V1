import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import re
from datetime import datetime

st.set_page_config(
    page_title="Connect | Análisis de Portafolio",
    page_icon="🔶", layout="wide",
)

st.markdown("""
<style>
html,body,[class*="css"]{font-family:'Segoe UI',Arial,sans-serif;}
.connect-header{background:linear-gradient(135deg,#001d3d 0%,#0a3060 100%);border-radius:12px;padding:18px 26px;margin-bottom:1.2rem;display:flex;align-items:center;gap:16px;}
.connect-logo{background:#f15b2b;width:46px;height:46px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0;}
.connect-title h1{color:white;font-size:1.6rem;font-weight:700;margin:0;}
.connect-title p{color:rgba(255,255,255,0.65);font-size:0.85rem;margin:3px 0 0 0;}
.sec{font-size:1.12rem;font-weight:700;color:#001d3d;border-left:5px solid #f15b2b;padding:4px 0 4px 12px;margin:2rem 0 0.8rem 0;background:linear-gradient(90deg,#f8f9fa 0%,transparent 100%);}
.box-ok{background:#e8f5e9;border-radius:8px;padding:10px 14px;font-size:0.86rem;color:#1b5e20;margin:0.4rem 0;border-left:4px solid #43a047;}
.box-warn{background:#fff8e1;border-radius:8px;padding:10px 14px;font-size:0.86rem;color:#6d4c00;margin:0.4rem 0;border-left:4px solid #f15b2b;}
.box-danger{background:#fdecea;border-radius:8px;padding:10px 14px;font-size:0.86rem;color:#7f1d1d;margin:0.4rem 0;border-left:4px solid #e53935;}
.box-info{background:#eef4fb;border-radius:8px;padding:10px 14px;font-size:0.86rem;color:#1a3a5c;margin:0.4rem 0;border-left:4px solid #0d7377;}
.ai-box{background:linear-gradient(135deg,#001d3d 0%,#0a3060 100%);border-radius:12px;padding:20px 24px;color:white;margin-top:1rem;}
.ai-box h3{color:#f15b2b;margin-bottom:10px;font-size:1.05rem;}
.ai-box p{font-size:0.88rem;line-height:1.6;opacity:0.92;margin:5px 0;}
div[data-testid="metric-container"]{background:#f8f9fa;border-radius:8px;padding:10px 14px;border:1px solid #e0e0e0;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="connect-header">
  <div class="connect-logo">🔶</div>
  <div class="connect-title">
    <h1>Análisis Operativo del Portafolio de Clientes</h1>
    <p>Comportamiento por cartera · Temporalidad · Usabilidad · Costo · Loss Ratio · Markowitz</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# CARTERAS Y PALABRAS DE EXCLUSIÓN
# ─────────────────────────────────────────────────────────
CARTERAS_VALIDAS = [
    'Afirme','Crabi','HDI Seguros - Bajio','HDI Seguros - Financieras',
    'HDI Seguros - Motos','HDI Seguros - MX','HDI Seguros - Occidente',
    'Kavak','Seguros Atlas - Auto','Seguros Atlas - Equipo Pesado',
    'Seguros El Potosi','Seguros El Potosi - ACMX','Tesla - MX','Clupp - Auto',
]
_EXCL = {
    'despachos','moto','motos','siniestro','pesado','acmx',
    'fleet','demand','services','compa','employees','empleados',
    'blu','spee','dee',
}

PAL = px.colors.qualitative.D3 + px.colors.qualitative.Plotly

# ─────────────────────────────────────────────────────────
# PARSER DEFINITIVO — AGNÓSTICO A ESTRUCTURA
# ─────────────────────────────────────────────────────────
def _clasificar_seccion(texto):
    """Clasifica un header de sección sin importar variaciones de nombre."""
    t = texto.lower().strip()
    if re.search(r'number of clients|clientes', t):          return 'clientes'
    if re.search(r'service count external', t):               return 'servicios'
    if re.search(r'service count all', t):                    return 'servicios'
    if re.search(r'^service frequency$', t):                  return 'frecuencia'
    if re.search(r'^revenue\s*-\s*sales', t):                 return 'revenue'
    if re.search(r'^service costs external$', t):             return 'costo_svc'
    if re.search(r'^average service cost', t):                return 'avg_costo'
    if re.search(r'^gross profit at risk', t):                return 'gp_at_risk'
    if re.search(r'^loss ratio\s*%', t):                      return 'loss_ratio'
    return None  # sección no reconocida → ignorar

def _match_cartera(nombre):
    """Empareja un nombre de fila con una cartera conocida."""
    s = nombre.strip(); sl = s.lower()
    if not sl or sl in ('nan','none',''): return None
    # 1. Exacto
    for c in CARTERAS_VALIDAS:
        if c.lower() == sl: return c
    # 2. Containment con protección de sub-carteras
    for c in CARTERAS_VALIDAS:
        cl = c.lower()
        if cl in sl and len(cl) > 4:
            extra = sl.replace(cl,'').strip(' -')
            ew = set(extra.split())
            if ew & _EXCL: continue
            if {w for w in ew if len(w) > 1}: continue
            return c
    # 3. Palabras clave (≥2 palabras significativas en común)
    sw = {w for w in sl.split() if len(w) > 2}
    for c in CARTERAS_VALIDAS:
        cw = {w for w in c.lower().split() if len(w) > 2}
        if len(sw & cw) >= 2 and len(sw & cw) >= len(cw) * 0.75:
            if not (sw - cw) & _EXCL: return c
    return None

def _primer_numero(row, max_cols=6):
    for ci in range(1, max_cols):
        try:
            v = str(row.iloc[ci]).strip().replace(',','')
            if v in ('','nan','None'): continue
            return float(v)
        except: pass
    return None

def _es_header(row):
    """True si la fila parece ser un encabezado de sección (col1 no es número)."""
    c1 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
    try:
        float(c1.replace(',',''))
        return False
    except:
        return True

def _parse_fecha(nombre, df_raw):
    """Extrae la fecha del contenido del archivo o del nombre."""
    # Desde contenido
    for _, row in df_raw.head(15).iterrows():
        for cell in row:
            s = str(cell) if pd.notna(cell) else ''
            if not s or s == 'nan': continue
            m = re.search(r'(\d{2}/\d{2}/\d{4})', s)
            if m:
                try: return datetime.strptime(m.group(1), '%m/%d/%Y')
                except: pass
            m = re.search(
                r'(January|February|March|April|May|June|July|August|'
                r'September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
                s, re.I
            )
            if m:
                for fmt in ('%B %d, %Y','%B %d %Y'):
                    try: return datetime.strptime(m.group(0).replace(',','').strip(), '%B %d %Y')
                    except: pass
            if isinstance(cell, pd.Timestamp):
                return cell.to_pydatetime()
    # Desde nombre del archivo — patrones MMYY, MM-YY, YYYY-MM
    for pat, fmt in [(r'(\d{4})[-_](\d{2})','%Y-%m'), (r'(\d{2})(\d{2})\.', None), (r'(\d{2})[-_](\d{2})\.', None)]:
        m = re.search(pat, nombre)
        if m:
            if fmt:
                try: return datetime.strptime(m.group(0).rstrip('.'), fmt)
                except: pass
            else:
                try:
                    g1, g2 = m.group(1), m.group(2)
                    mes = int(g1); anio = int(g2)
                    if 1 <= mes <= 12 and 20 <= anio <= 35:
                        return datetime(2000+anio, mes, 1)
                except: pass
    return None

def extraer_archivo(df_raw):
    """
    Parser agnóstico: escanea el archivo de arriba a abajo,
    detecta secciones por sus keywords y extrae datos por cartera.
    Funciona independientemente de la estructura, año o versión del reporte.
    """
    resultado = {}
    seccion_actual = None
    seen_costo_svc = False   # costo_svc aparece dos veces; ignorar la segunda

    for i, row in df_raw.iterrows():
        c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
        if not c0: continue

        # ¿Es un total? → ignorar
        if c0.lower().startswith('total'): continue

        # ¿Es un header de sección?
        if _es_header(row) and len(c0) > 3:
            var = _clasificar_seccion(c0)
            if var == '__skip__' or var is None:
                # Si no reconocemos la sección, volvemos al estado neutro
                # EXCEPTO si es una subsección conocida como "Cost of Sales Revenue"
                if re.search(r'cost of (sales|revenue)|gross profit fee|revenue.*services', c0.lower()):
                    seccion_actual = '__skip__'
                # Para secciones como "KPIs - Number of Clients" completas
                continue
            if var == 'costo_svc':
                if seen_costo_svc:
                    # Segunda aparición = subsección de avg_costo → ignorar datos
                    seccion_actual = '__skip__'
                    continue
                seen_costo_svc = True
            seccion_actual = var
            if var not in resultado:
                resultado[var] = {}
            continue

        # ¿Estamos en una sección a ignorar?
        if seccion_actual is None or seccion_actual == '__skip__':
            continue

        # Intentar extraer dato de cartera
        cartera = _match_cartera(c0)
        if not cartera: continue
        val = _primer_numero(row)
        if val is not None:
            # Para secciones donde podría haber duplicado, quedarnos con el primero
            if cartera not in resultado.get(seccion_actual, {}):
                resultado.setdefault(seccion_actual, {})[cartera] = val

    return resultado


@st.cache_data(show_spinner="📂 Procesando reportes Sage Intacct...", ttl=None)
def procesar_todo(bytes_list, nombres_list):
    import io
    records = []
    errores = []

    for fbytes, fname in zip(bytes_list, nombres_list):
        try:
            df_raw = pd.read_excel(io.BytesIO(fbytes), header=None)
            fecha  = _parse_fecha(fname, df_raw)
            if not fecha:
                errores.append(f"⚠️ {fname}: no se pudo detectar la fecha — renombra como MMAA.KPI.xlsx")
                continue

            mes_label   = fecha.strftime('%Y-%m')
            mes_display = fecha.strftime('%b-%Y')
            extraidos   = extraer_archivo(df_raw)

            todas_carteras = set()
            for d in extraidos.values():
                todas_carteras.update(d.keys())

            n = 0
            for cart in todas_carteras:
                rev  = extraidos.get('revenue',   {}).get(cart)
                cost = extraidos.get('costo_svc', {}).get(cart)
                clts = extraidos.get('clientes',  {}).get(cart)
                svcs = extraidos.get('servicios', {}).get(cart)
                freq = extraidos.get('frecuencia',{}).get(cart)
                avg  = extraidos.get('avg_costo', {}).get(cart)
                gp   = extraidos.get('gp_at_risk',{}).get(cart)
                lr   = extraidos.get('loss_ratio',{}).get(cart)

                if not rev or rev <= 0: continue

                records.append({
                    'Mes':            mes_label,
                    'Mes_Display':    mes_display,
                    'Cartera':        cart,
                    'Revenue':        rev,
                    'Costo_Servicio': cost,
                    'Clientes':       clts,
                    'Servicios':      svcs,
                    'Frecuencia':     freq,
                    'Avg_Costo_Svc':  avg,
                    'GP_At_Risk':     gp,
                    'Loss_Ratio':     lr,
                    'Margen_GP':      (rev-cost)/rev if cost and rev > 0 else None,
                    'GP_por_Cliente': gp/clts if gp and clts and clts > 0 else None,
                    'Rev_por_Cliente':rev/clts if clts and clts > 0 else None,
                    'Costo_por_Cliente': cost/clts if cost and clts and clts > 0 else None,
                })
                n += 1

            if n == 0:
                errores.append(f"⚠️ {fname} ({mes_display}): archivo procesado pero sin carteras reconocidas con revenue > 0")
        except Exception as e:
            errores.append(f"❌ {fname}: {type(e).__name__}: {e}")
            continue

    if not records:
        detalle = " | ".join(errores) if errores else "El parser no encontró datos de revenue en ningún archivo."
        return None, errores, f"No se pudieron extraer datos. {detalle}"

    df = pd.DataFrame(records).sort_values(['Cartera','Mes']).reset_index(drop=True)
    return df, errores, None


@st.cache_data(show_spinner="🎲 Simulación Monte Carlo...")
def monte_carlo(mu_t, cov_flat, n_prov, n_sim, carteras_t):
    mu_arr  = np.array(mu_t)
    cov_mat = np.array(cov_flat).reshape(n_prov, n_prov)
    carteras = list(carteras_t)
    np.random.seed(42)
    res = np.zeros((n_sim, 3 + n_prov))
    for i in range(n_sim):
        w = np.random.random(n_prov); w /= w.sum()
        s  = float(np.dot(w, mu_arr))
        r  = float(np.sqrt(w @ cov_mat @ w))
        res[i] = [s, r, s/r if r > 0 else 0] + list(w)
    df_s = pd.DataFrame(res, columns=['Rent','Riesgo','Sharpe']+carteras)
    return df_s, df_s.loc[df_s['Sharpe'].idxmax()], df_s.loc[df_s['Riesgo'].idxmin()]


# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    archivos = st.file_uploader(
        "📂 Reportes KPIs Sage (.xlsx)",
        type=["xlsx"], accept_multiple_files=True,
        help="Sube todos los meses disponibles. Funciona con Budget o Forecast, cualquier año."
    )
    st.markdown("---")
    lr_target   = st.slider("📉 Loss Ratio objetivo (máx)", 40, 85, 65, 5) / 100
    freq_alerta = st.slider("⚡ Alerta frecuencia (‰ sv/cliente)", 5, 25, 12, 1) / 1000
    umbral_conc = st.slider("⚠️ Umbral concentración revenue (%)", 15, 40, 25, 5)
    n_sim       = st.select_slider("🎲 Simulaciones Monte Carlo", [1000,3000,5000,10000,20000], 5000)
    min_meses_mk= st.slider("📅 Meses mínimos para Markowitz", 3, 18, 6, 1,
                             help="Carteras con menos meses quedan fuera del modelo.")
    st.markdown("---")
    carteras_sel = st.multiselect("🔍 Filtrar carteras", CARTERAS_VALIDAS, default=[],
                                  help="Vacío = mostrar todas")
    st.markdown("---")
    if st.button("🔄 Limpiar caché y reprocesar", help="Fuerza el reprocesamiento de todos los archivos"):
        procesar_todo.clear()
        monte_carlo.clear()
        st.rerun()
    st.caption("Connect Assistance México\nAnálisis Operativo del Portafolio\nUniversidad Panamericana")

# ─────────────────────────────────────────────────────────
# PANTALLA INICIAL
# ─────────────────────────────────────────────────────────
if not archivos:
    st.info("👈 Sube los reportes KPIs mensuales de Sage Intacct — todos los meses juntos.")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("""
**¿Qué archivos subir?**
- `KPIs - Actuals vs Budget by Segment.xlsx`
- `KPIs - Actuals vs Forecast by Segment.xlsx`
- Uno por mes — sube todos juntos de una vez
- Nombre sugerido: `MMAA.KPI.xlsx` (ej: `0125.KPI.xlsx`)
        """)
    with c2:
        st.markdown("""
**¿Qué analiza?**
1. Concentración de revenue
2. Crecimiento de clientes
3. Servicios y temporalidad
4. Frecuencia de uso
5. Costo promedio por servicio
6. Loss Ratio histórico
7. Markowitz (1 − Loss Ratio)
8. Señales de acción por cartera
9. Síntesis ejecutiva
        """)
    st.stop()

# ─────────────────────────────────────────────────────────
# PROCESAR
# ─────────────────────────────────────────────────────────
fb = [f.read() for f in archivos]
fn = [f.name for f in archivos]

df_all, errores, error_fatal = procesar_todo(fb, fn)

if errores:
    with st.expander(f"⚠️ {len(errores)} advertencia(s) al procesar", expanded=bool(error_fatal)):
        for e in errores: st.write(e)

if error_fatal:
    st.error(f"❌ {error_fatal}")
    st.stop()

if carteras_sel:
    df_all = df_all[df_all['Cartera'].isin(carteras_sel)]

carteras    = sorted(df_all['Cartera'].unique().tolist())
meses_ord   = sorted(df_all['Mes'].unique().tolist())
n_meses     = len(meses_ord)
mes_disp    = df_all.groupby('Mes')['Mes_Display'].first().to_dict()
xticks      = [mes_disp.get(m,m) for m in meses_ord]

st.success(
    f"✅ **{len(archivos)} archivo(s)** · **{len(carteras)} carteras** · "
    f"**{n_meses} períodos** · de {mes_disp.get(meses_ord[0],'?')} a {mes_disp.get(meses_ord[-1],'?')}"
)

def pivot(col, fillna=None):
    p = df_all.pivot_table(index='Mes', columns='Cartera', values=col, aggfunc='mean')
    p = p.reindex(meses_ord)
    if fillna is not None: p = p.fillna(fillna)
    return p

# Pivots principales
rev_pivot  = pivot('Revenue')
clts_pivot = pivot('Clientes')
svc_pivot  = pivot('Servicios')
freq_pivot = pivot('Frecuencia')
avg_pivot  = pivot('Avg_Costo_Svc')
lr_pivot   = pivot('Loss_Ratio')
rpc_pivot  = pivot('Rev_por_Cliente')
gpc_pivot  = pivot('GP_por_Cliente')

# Revenue y concentración
rev_prom      = rev_pivot.mean()
rev_total_prom= rev_prom.sum()
participacion = (rev_prom / rev_total_prom * 100)
pesos_act     = (rev_prom / rev_total_prom).values
mu_global     = np.array([rev_prom.get(c,0) for c in carteras])

# ─────────────────────────────────────────────────────────
# SECCIÓN 0 — CONCENTRACIÓN
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">0 · Concentración de Revenue por Cartera</div>', unsafe_allow_html=True)

part_sorted = participacion.sort_values(ascending=False)
c1, c2 = st.columns([1.1,1])
with c1:
    df_conc = pd.DataFrame({
        'Cartera':           part_sorted.index,
        'Revenue Prom. ($)': rev_prom[part_sorted.index].round(0),
        'Participación (%)': part_sorted.values.round(1),
    }).reset_index(drop=True)
    def hl(v): return "background-color:#fdecea;font-weight:bold" if isinstance(v,float) and v>umbral_conc else ""
    st.dataframe(
        df_conc.style.map(hl, subset=['Participación (%)'])
            .format({'Revenue Prom. ($)':'${:,.0f}','Participación (%)':'{:.1f}%'}),
        use_container_width=True, hide_index=True
    )
    en_riesgo = participacion[participacion > umbral_conc]
    for c,p in en_riesgo.sort_values(ascending=False).items():
        st.markdown(f'<div class="box-warn">⚠️ <b>{c}</b> concentra <b>{p:.1f}%</b> del revenue — supera el umbral de {umbral_conc}%.</div>', unsafe_allow_html=True)
    if en_riesgo.empty:
        st.markdown(f'<div class="box-ok">✅ Ninguna cartera supera el umbral de {umbral_conc}%.</div>', unsafe_allow_html=True)
with c2:
    colors = ["#e53935" if participacion[c]>umbral_conc else "#001d3d" for c in part_sorted.index]
    fig = go.Figure(go.Pie(labels=part_sorted.index, values=part_sorted.values,
        hole=0.45, textinfo="label+percent", marker=dict(colors=colors)))
    fig.update_layout(title="Concentración actual del revenue", height=320, showlegend=False, margin=dict(t=40,b=5,l=5,r=5))
    st.plotly_chart(fig, use_container_width=True)

# Revenue apilado en el tiempo
fig_rev = go.Figure()
for i,c in enumerate(carteras):
    if c in rev_pivot.columns:
        fig_rev.add_trace(go.Bar(x=xticks, y=rev_pivot[c].values, name=c,
            marker_color=PAL[i%len(PAL)],
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>${{y:,.0f}}<extra></extra>"))
fig_rev.update_layout(barmode='stack', title="Revenue mensual acumulado por cartera",
    xaxis_title="Mes", yaxis_title="Revenue ($)", height=370,
    legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_rev, use_container_width=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 1 — CLIENTES
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">1 · Clientes Activos — Crecimiento por Cartera</div>', unsafe_allow_html=True)

fig_clts = go.Figure()
for i,c in enumerate(carteras):
    if c in clts_pivot.columns and clts_pivot[c].notna().sum() >= 2:
        s = clts_pivot[c].dropna()
        fig_clts.add_trace(go.Scatter(x=[mes_disp.get(m,m) for m in s.index], y=s.values,
            mode='lines+markers', name=c,
            line=dict(width=2, color=PAL[i%len(PAL)]), marker=dict(size=5),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>{{y:,.0f}} clientes<extra></extra>"))
fig_clts.update_layout(title="Evolución de Clientes Activos por Cartera",
    xaxis_title="Mes", yaxis_title="Clientes", height=400,
    xaxis=dict(categoryorder='array', categoryarray=xticks),
    hovermode='x unified', legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_clts, use_container_width=True)

crec = []
for c in carteras:
    if c in clts_pivot.columns:
        s = clts_pivot[c].dropna()
        if len(s) >= 2:
            crec.append({'Cartera':c, 'Inicio':s.iloc[0], 'Fin':s.iloc[-1],
                         'Meses datos':len(s),
                         'Crecimiento (%)': (s.iloc[-1]-s.iloc[0])/s.iloc[0]*100})
if crec:
    df_crec = pd.DataFrame(crec).sort_values('Crecimiento (%)', ascending=False)
    def hl_crec(v):
        if isinstance(v,float):
            if v > 20: return "background-color:#e8f5e9"
            if v < -10: return "background-color:#fdecea"
        return ""
    st.dataframe(df_crec.style.map(hl_crec, subset=['Crecimiento (%)'])
        .format({'Inicio':'{:,.0f}','Fin':'{:,.0f}','Crecimiento (%)':'{:+.1f}%'}),
        use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 2 — SERVICIOS Y TEMPORALIDAD
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">2 · Servicios y Temporalidad — ¿Cuándo se dispara la demanda?</div>', unsafe_allow_html=True)

carts_svc = [c for c in carteras if c in svc_pivot.columns and svc_pivot[c].notna().sum() >= 2]
if carts_svc:
    mat = svc_pivot[carts_svc].T
    fig_h = px.imshow(mat.values, x=xticks, y=carts_svc,
        color_continuous_scale='RdYlGn_r', aspect='auto',
        title="Heatmap de Servicios  (rojo = pico de demanda)")
    fig_h.update_layout(height=max(300, len(carts_svc)*35+80), margin=dict(t=55,b=20))
    st.plotly_chart(fig_h, use_container_width=True)
    st.markdown('<div class="box-info">💡 Los picos rojos indican meses de alta demanda. Columnas con múltiples carteras en rojo = riesgo sistémico de costo ese mes.</div>', unsafe_allow_html=True)

fig_svc = go.Figure()
for i,c in enumerate(carts_svc):
    s=svc_pivot[c].dropna()
    fig_svc.add_trace(go.Scatter(x=[mes_disp.get(m,m) for m in s.index], y=s.values,
        mode='lines+markers', name=c, line=dict(width=2, color=PAL[i%len(PAL)]),
        hovertemplate=f"<b>{c}</b><br>%{{x}}<br>{{y:,.0f}} servicios<extra></extra>"))
fig_svc.update_layout(title="Evolución de Servicios Mensuales",
    xaxis_title="Mes", yaxis_title="Servicios", height=370,
    xaxis=dict(categoryorder='array', categoryarray=xticks),
    hovermode='x unified', legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_svc, use_container_width=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 3 — FRECUENCIA DE USO
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">3 · Frecuencia de Uso — Usabilidad e Impacto en el Costo</div>', unsafe_allow_html=True)

st.markdown(f'<div class="box-info">💡 <b>Frecuencia = servicios / clientes activos.</b> Cuando sube, más clientes usan el servicio — el costo sube aunque el precio no cambie. Línea de alerta: <b>{freq_alerta*1000:.0f}‰</b>.</div>', unsafe_allow_html=True)

fig_freq = go.Figure()
for i,c in enumerate(carteras):
    if c in freq_pivot.columns and freq_pivot[c].notna().sum() >= 2:
        s=freq_pivot[c].dropna()
        fig_freq.add_trace(go.Scatter(x=[mes_disp.get(m,m) for m in s.index], y=s.values*100,
            mode='lines+markers', name=c, line=dict(width=2, color=PAL[i%len(PAL)]),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>%{{y:.3f}}%<extra></extra>"))
fig_freq.add_hline(y=freq_alerta*100, line_dash='dot', line_color='#f15b2b',
    annotation_text=f"Alerta {freq_alerta*1000:.0f}‰", annotation_font=dict(color='#f15b2b',size=10))
fig_freq.update_layout(title="Frecuencia de Uso (% de clientes que usaron el servicio)",
    xaxis_title="Mes", yaxis_title="Frecuencia (%)", height=400,
    xaxis=dict(categoryorder='array', categoryarray=xticks),
    hovermode='x unified', legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_freq, use_container_width=True)

freq_carts = [c for c in carteras if c in freq_pivot.columns and freq_pivot[c].notna().sum() >= 3]
if len(freq_carts) >= 2:
    corr_freq = freq_pivot[freq_carts].corr().round(2)
    fig_corr_f = px.imshow(corr_freq, text_auto=True, color_continuous_scale='RdBu_r',
        zmin=-1, zmax=1, title="Correlación de frecuencia de uso entre carteras", aspect='auto')
    fig_corr_f.update_layout(height=380, margin=dict(t=55,b=10))
    st.plotly_chart(fig_corr_f, use_container_width=True)
    st.markdown('<div class="box-info">💡 Alta correlación = los picos de costo ocurren en los mismos meses para ambas carteras. Baja correlación = se compensan mutuamente.</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 4 — COSTO PROMEDIO
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">4 · Costo Promedio por Servicio — Inflación Operativa</div>', unsafe_allow_html=True)

st.markdown('<div class="box-info">💡 Si el costo promedio sube sistemáticamente sin que el precio contratado haya cambiado, el margen se comprime mes a mes.</div>', unsafe_allow_html=True)

fig_avg = go.Figure()
for i,c in enumerate(carteras):
    if c in avg_pivot.columns and avg_pivot[c].notna().sum() >= 2:
        # Usar solo los meses donde hay datos (sin NaN) — evita desalineación de ejes
        serie = avg_pivot[c].dropna()
        x_ticks_c = [mes_disp.get(m, m) for m in serie.index]
        y_vals = serie.values
        fig_avg.add_trace(go.Scatter(
            x=x_ticks_c, y=y_vals, mode='lines+markers', name=c,
            line=dict(width=2, color=PAL[i%len(PAL)]),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>${{y:.2f}}/servicio<extra></extra>"))
        if len(y_vals) >= 3:
            xn = np.arange(len(y_vals)); z = np.polyfit(xn, y_vals, 1)
            fig_avg.add_trace(go.Scatter(
                x=x_ticks_c, y=np.poly1d(z)(xn),
                mode='lines', line=dict(width=1, dash='dot', color=PAL[i%len(PAL)]),
                showlegend=False, opacity=0.4,
                hovertemplate=f"<b>{c} tendencia</b><br>${{y:.2f}}<extra></extra>"))
fig_avg.update_layout(title="Costo Promedio por Servicio con tendencias",
    xaxis_title="Mes", yaxis_title="$ / servicio", height=420,
    xaxis=dict(categoryorder='array', categoryarray=xticks),
    hovermode='x unified', legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_avg, use_container_width=True)

avg_res = []
for c in carteras:
    if c in avg_pivot.columns:
        s = avg_pivot[c].dropna()
        if len(s) >= 2:
            var = (s.iloc[-1]-s.iloc[0])/s.iloc[0]*100
            avg_res.append({'Cartera':c,'Costo inicial ($)':s.iloc[0],'Costo actual ($)':s.iloc[-1],
                            'Variación (%)':var,'Meses':len(s),
                            'Tendencia':'📈 Subiendo' if var>5 else ('📉 Bajando' if var<-5 else '➡️ Estable')})
if avg_res:
    df_avg_r = pd.DataFrame(avg_res).sort_values('Variación (%)', ascending=False)
    def hl_avg(v):
        if isinstance(v,float):
            if v>20: return "background-color:#fdecea"
            if v>10: return "background-color:#fff8e1"
            if v<-5: return "background-color:#e8f5e9"
        return ""
    st.dataframe(df_avg_r.style.map(hl_avg, subset=['Variación (%)'])
        .format({'Costo inicial ($)':'${:.2f}','Costo actual ($)':'${:.2f}','Variación (%)':'{:+.1f}%'}),
        use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 5 — LOSS RATIO
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">5 · Loss Ratio — Historial, Temporalidad y Alertas</div>', unsafe_allow_html=True)

st.markdown(f'<div class="box-info">💡 <b>Loss Ratio = Costo de Servicio / Revenue.</b> Límite objetivo: {lr_target:.0%}. Valores > 1.0 = pérdida directa en servicios.</div>', unsafe_allow_html=True)

fig_lr = go.Figure()
for i,c in enumerate(carteras):
    if c in lr_pivot.columns and lr_pivot[c].notna().sum() >= 2:
        s=lr_pivot[c].dropna()
        fig_lr.add_trace(go.Scatter(x=[mes_disp.get(m,m) for m in s.index], y=s.values,
            mode='lines+markers', name=c, line=dict(width=2.5, color=PAL[i%len(PAL)]),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>LR: %{{y:.3f}}<extra></extra>"))
fig_lr.add_hline(y=lr_target, line_dash='dot', line_color='#f15b2b', line_width=2,
    annotation_text=f"Objetivo {lr_target:.0%}", annotation_font=dict(color='#f15b2b',size=11))
fig_lr.add_hline(y=1.0, line_dash='solid', line_color='#7f1d1d', line_width=1.5,
    annotation_text="LR=1.0: sin margen", annotation_position='bottom right',
    annotation_font=dict(color='#7f1d1d',size=9))
fig_lr.update_layout(title="Evolución del Loss Ratio por Cartera",
    xaxis_title="Mes", yaxis_title="Loss Ratio", height=450,
    xaxis=dict(categoryorder='array', categoryarray=xticks),
    hovermode='x unified', legend=dict(orientation='h',y=-0.3), margin=dict(t=55,b=10))
st.plotly_chart(fig_lr, use_container_width=True)

lr_carts = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].notna().sum() >= 2]
if lr_carts:
    mat_lr = lr_pivot[lr_carts].T
    fig_lr_h = px.imshow(mat_lr.values, x=xticks, y=lr_carts,
        color_continuous_scale='RdYlGn_r', zmin=0, zmax=1.2, aspect='auto',
        title="Heatmap Loss Ratio  (rojo = cartera en problema ese mes)")
    fig_lr_h.update_layout(height=max(300,len(lr_carts)*35+80), margin=dict(t=55,b=10))
    st.plotly_chart(fig_lr_h, use_container_width=True)

lr_res = []
for c in carteras:
    if c in lr_pivot.columns:
        s = lr_pivot[c].dropna()
        if len(s) >= 1:
            pct_sobre = (s > lr_target).mean()*100
            lr_res.append({'Cartera':c,'Meses con datos':len(s),
                           'LR Promedio':s.mean(),'LR Máximo':s.max(),'LR Mínimo':s.min(),
                           'Meses sobre objetivo (%)':pct_sobre,
                           'Estado':'🔴 CRÍTICO' if s.mean()>0.85 else ('🟡 REVISAR' if s.mean()>lr_target else '🟢 OK')})
if lr_res:
    df_lr_r = pd.DataFrame(lr_res).sort_values('LR Promedio', ascending=False)
    def hl_lr(v):
        if isinstance(v,float):
            if v>0.85: return "background-color:#fdecea;font-weight:bold"
            if v>lr_target: return "background-color:#fff8e1"
        return ""
    st.dataframe(df_lr_r.style.map(hl_lr, subset=['LR Promedio','LR Máximo'])
        .format({'LR Promedio':'{:.3f}','LR Máximo':'{:.3f}','LR Mínimo':'{:.3f}',
                 'Meses sobre objetivo (%)':'{:.0f}%'}),
        use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 6 — REVENUE Y GP POR CLIENTE
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">6 · Ingreso y GP por Cliente — Rentabilidad Real por Certificado</div>', unsafe_allow_html=True)

c1,c2 = st.columns(2)
with c1:
    fig_rpc = go.Figure()
    for i,c in enumerate(carteras):
        if c in rpc_pivot.columns and rpc_pivot[c].notna().sum() >= 2:
            s=rpc_pivot[c].dropna()
            fig_rpc.add_trace(go.Scatter(x=[mes_disp.get(m,m) for m in s.index], y=s.values,
                mode='lines+markers', name=c, line=dict(width=2, color=PAL[i%len(PAL)]),
                hovertemplate=f"<b>{c}</b><br>${{y:.3f}}/cliente<extra></extra>"))
    fig_rpc.update_layout(title="Revenue por cliente ($)", xaxis_title="Mes",
        height=340, xaxis=dict(categoryorder='array', categoryarray=xticks),
        hovermode='x unified', legend=dict(orientation='h',y=-0.4), margin=dict(t=50,b=10))
    st.plotly_chart(fig_rpc, use_container_width=True)
with c2:
    fig_gpc = go.Figure()
    for i,c in enumerate(carteras):
        if c in gpc_pivot.columns and gpc_pivot[c].notna().sum() >= 2:
            s=gpc_pivot[c].dropna()
            fig_gpc.add_trace(go.Scatter(x=[mes_disp.get(m,m) for m in s.index], y=s.values,
                mode='lines+markers', name=c, line=dict(width=2, color=PAL[i%len(PAL)]),
                hovertemplate=f"<b>{c}</b><br>GP ${{'y:.3f}}/cliente<extra></extra>"))
    fig_gpc.update_layout(title="GP At Risk por cliente ($)", xaxis_title="Mes",
        height=340, xaxis=dict(categoryorder='array', categoryarray=xticks),
        hovermode='x unified', legend=dict(orientation='h',y=-0.4), margin=dict(t=50,b=10))
    st.plotly_chart(fig_gpc, use_container_width=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 7 — MARKOWITZ
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">7 · Optimización Markowitz — Portafolio por Rentabilidad Real (1 − Loss Ratio)</div>', unsafe_allow_html=True)

st.markdown("""
<div class="box-info">
💡 <b>Variable del modelo: (1 - Loss Ratio)</b> — cuánto queda de cada peso de revenue después del costo de servicio.
Varía entre 5% y 55% entre carteras y tiene variación real mes a mes.
El Margen GP At Risk del reporte es estrecho (~85-99%) y no diferencia carteras.
</div>
""", unsafe_allow_html=True)

rentab_pivot = 1 - lr_pivot
carteras_mk = [c for c in carteras if c in rentab_pivot.columns
               and rentab_pivot[c].notna().sum() >= min_meses_mk
               and rentab_pivot[c].std() > 0]
excluidas_mk = [c for c in carteras if c in rentab_pivot.columns
                and 0 < rentab_pivot[c].notna().sum() < min_meses_mk]

if excluidas_mk:
    st.markdown(
        f'<div class="box-warn">📅 <b>{len(excluidas_mk)} cartera(s) excluida(s)</b> del modelo '
        f'por tener menos de {min_meses_mk} meses de Loss Ratio: <b>{", ".join(excluidas_mk)}</b>. '
        f'Reduce el mínimo en el sidebar para incluirlas.</div>',
        unsafe_allow_html=True
    )

if len(carteras_mk) >= 2:
    mu_mk    = rentab_pivot[carteras_mk].mean()
    sigma_mk = rentab_pivot[carteras_mk].std()
    cov_mk   = rentab_pivot[carteras_mk].cov().values
    cov_mk   = np.nan_to_num(cov_mk, nan=0.0)
    

    # Mapa riesgo-rentabilidad
    fig_mapa = go.Figure()
    for i,c in enumerate(carteras_mk):
        fig_mapa.add_trace(go.Scatter(
            x=[sigma_mk[c]], y=[mu_mk[c]],
            mode='markers+text', text=[c], textposition='top center',
            marker=dict(size=20, color=PAL[i%len(PAL)], line=dict(color='white',width=1.5)),
            name=c,
            hovertemplate=f"<b>{c}</b><br>Rentabilidad: {mu_mk[c]:.1%}<br>σ: {sigma_mk[c]:.4f}<extra></extra>"
        ))
    fig_mapa.add_hline(y=(1-lr_target), line_dash='dash', line_color='#f15b2b',
        annotation_text=f"Objetivo {1-lr_target:.0%}", annotation_font=dict(color='#f15b2b',size=9))
    fig_mapa.add_vline(x=sigma_mk.median(), line_dash='dot', line_color='#aaa', line_width=1)
    fig_mapa.add_hline(y=mu_mk.median(), line_dash='dot', line_color='#aaa', line_width=1)
    fig_mapa.update_layout(
        title="Mapa Riesgo–Rentabilidad  (esquina superior izquierda = ideal ⭐)",
        xaxis_title="Riesgo — Volatilidad de (1 - LR)",
        yaxis_title="Rentabilidad Promedio (1 - LR)",
        yaxis=dict(tickformat='.0%'), height=420, showlegend=False, margin=dict(t=55,b=30))
    st.plotly_chart(fig_mapa, use_container_width=True)

    # Monte Carlo
    df_sim, opt, minr = monte_carlo(
        tuple(mu_mk.values), tuple(cov_mk.flatten()),
        len(carteras_mk), n_sim, tuple(carteras_mk)
    )

    fig_front = go.Figure()
    fig_front.add_trace(go.Scatter(x=df_sim['Riesgo'], y=df_sim['Rent'], mode='markers',
        marker=dict(color=df_sim['Sharpe'], colorscale='Viridis', size=3, opacity=0.5,
                    colorbar=dict(title='Eficiencia',thickness=12,len=0.7)),
        name='Portafolios simulados',
        hovertemplate='Riesgo: %{x:.4f}<br>Rentabilidad: %{y:.1%}<extra></extra>'))
    fig_front.add_trace(go.Scatter(x=[minr['Riesgo']], y=[minr['Rent']], mode='markers',
        marker=dict(symbol='diamond',size=18,color='#1976d2',line=dict(color='white',width=1.5)),
        name='🔵 Mínimo Riesgo'))
    fig_front.add_trace(go.Scatter(x=[opt['Riesgo']], y=[opt['Rent']], mode='markers',
        marker=dict(symbol='star',size=24,color='#e53935',line=dict(color='white',width=1.5)),
        name='⭐ Portafolio Óptimo'))

    # Distribución actual
    carts_comun = [c for c in carteras_mk if c in rev_pivot.columns]
    if carts_comun:
        w_act  = np.array([rev_prom.get(c,0) for c in carts_comun])
        w_act  = w_act / w_act.sum() if w_act.sum() > 0 else w_act
        mu_act = np.array([mu_mk[c] for c in carts_comun])
        cv_act = rentab_pivot[carts_comun].cov().values
        r_a = float(np.dot(w_act, mu_act))
        v_a = float(np.sqrt(w_act @ cv_act @ w_act))
        fig_front.add_trace(go.Scatter(x=[v_a], y=[r_a], mode='markers',
            marker=dict(symbol='square',size=16,color='#f15b2b',line=dict(color='white',width=1.5)),
            name='🟠 Distribución Actual'))

    fig_front.update_layout(
        title=f"Frontera Eficiente — Portafolio de Clientes Connect  ({n_sim:,} simulaciones)",
        xaxis_title="Riesgo (σ)", yaxis_title="Rentabilidad (1 − LR)",
        yaxis=dict(tickformat='.0%'), height=500, hovermode='closest',
        legend=dict(orientation='h',y=-0.18), margin=dict(t=55,b=20))
    st.plotly_chart(fig_front, use_container_width=True)

    # Asignación óptima
    m1,m2,m3 = st.columns(3)
    m1.metric("📈 Rentabilidad Esperada", f"{opt['Rent']:.1%}")
    m2.metric("⚡ Riesgo (σ)", f"{opt['Riesgo']:.4f}")
    m3.metric("🏆 Eficiencia (Sharpe)", f"{opt['Sharpe']:.1f}")
    st.markdown("---")

    pesos_opt = {c: opt[c] for c in carteras_mk}
    df_asig = pd.DataFrame({
        'Cartera':                 carteras_mk,
        'Peso Óptimo (%)':         [pesos_opt[c]*100 for c in carteras_mk],
        'Rentabilidad Prom. (1-LR)':[mu_mk[c]      for c in carteras_mk],
        'Volatilidad σ':           [sigma_mk[c]    for c in carteras_mk],
        'LR Promedio':             [lr_pivot[c].mean() if c in lr_pivot.columns else None for c in carteras_mk],
    }).sort_values('Peso Óptimo (%)', ascending=False).reset_index(drop=True)

    # Comparativa con distribución actual
    if carts_comun:
        part_mk = {c: rev_prom.get(c,0)/rev_total_prom*100 for c in carteras_mk}
        df_asig['% Actual']    = df_asig['Cartera'].map(part_mk).round(1)
        df_asig['Cambio (pp)'] = (df_asig['Peso Óptimo (%)'] - df_asig['% Actual']).round(1)

    ca1,ca2 = st.columns([1.1,1])
    with ca1:
        fmt = {'Peso Óptimo (%)':'{:.1f}%','Rentabilidad Prom. (1-LR)':'{:.1%}',
               'Volatilidad σ':'{:.4f}','LR Promedio':'{:.3f}'}
        if '% Actual' in df_asig.columns:
            fmt['% Actual']='{:.1f}%'; fmt['Cambio (pp)']='{:+.1f}'
        st.dataframe(df_asig.style.format(fmt)
            .background_gradient(subset=['Peso Óptimo (%)'], cmap='Greens')
            .background_gradient(subset=['Rentabilidad Prom. (1-LR)'], cmap='Blues'),
            use_container_width=True, hide_index=True)
    with ca2:
        fig_dona = go.Figure(go.Pie(labels=df_asig['Cartera'],
            values=df_asig['Peso Óptimo (%)'], hole=0.45, textinfo='label+percent',
            marker=dict(colors=PAL[:len(df_asig)])))
        fig_dona.update_layout(title="Distribución óptima del portafolio",
            height=340, showlegend=False, margin=dict(t=45,b=10,l=10,r=10))
        st.plotly_chart(fig_dona, use_container_width=True)

    # Barras actual vs óptima
    if '% Actual' in df_asig.columns:
        fig_barras = go.Figure()
        fig_barras.add_trace(go.Bar(name='% Actual', x=carteras_mk,
            y=[part_mk[c] for c in carteras_mk], marker_color='#001d3d',
            text=[f"{part_mk[c]:.1f}%" for c in carteras_mk], textposition='outside'))
        fig_barras.add_trace(go.Bar(name='% Óptimo', x=carteras_mk,
            y=[pesos_opt[c]*100 for c in carteras_mk], marker_color='#f15b2b',
            text=[f"{pesos_opt[c]*100:.1f}%" for c in carteras_mk], textposition='outside'))
        fig_barras.add_hline(y=umbral_conc, line_dash='dot', line_color='red',
            annotation_text=f"Umbral {umbral_conc}%",
            annotation_font=dict(color='red',size=10))
        fig_barras.update_layout(title="Distribución actual vs. óptima",
            xaxis_title="Cartera", yaxis_title="% del Revenue", barmode='group',
            height=420, legend=dict(orientation='h',y=-0.22), margin=dict(t=55,b=20))
        st.plotly_chart(fig_barras, use_container_width=True)
else:
    st.warning(f"⚠️ Se necesitan al menos 2 carteras con {min_meses_mk}+ períodos de Loss Ratio.")

# ─────────────────────────────────────────────────────────
# SECCIÓN 8 — SEÑALES DE ACCIÓN
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">8 · Señales de Acción por Cartera</div>', unsafe_allow_html=True)
st.markdown("Diagnóstico basado en Loss Ratio histórico, tendencia de costo, clientes y frecuencia:")
st.markdown("")

for c in sorted(carteras):
    lr_s   = lr_pivot[c].dropna()  if c in lr_pivot.columns  else pd.Series(dtype=float)
    avg_s  = avg_pivot[c].dropna() if c in avg_pivot.columns else pd.Series(dtype=float)
    clts_s = clts_pivot[c].dropna()if c in clts_pivot.columns else pd.Series(dtype=float)
    freq_s = freq_pivot[c].dropna()if c in freq_pivot.columns else pd.Series(dtype=float)
    rev_s  = rev_pivot[c].dropna() if c in rev_pivot.columns  else pd.Series(dtype=float)

    if lr_s.empty and rev_s.empty: continue

    n_meses_c = max(len(lr_s), len(rev_s))
    es_nueva  = n_meses_c < 12
    tag_edad  = f" · 🆕 {n_meses_c} meses" if es_nueva else f" · {n_meses_c} meses"

    if lr_s.empty:
        cat="🔵 SIN LR"; cls="box-info"
        accion=f"Cartera de modelo Fee for Service — no tiene Loss Ratio en el reporte Sage. Monitorear revenue y clientes."
        lr_prom=None; lr_trend=""
    else:
        lr_prom = lr_s.mean()
        lr_trend = "📈" if len(lr_s)>=3 and lr_s.iloc[-1]>lr_s.iloc[-3] else "📉"
        if lr_prom > 0.90:
            cat="🔴 CRÍTICA"; cls="box-danger"
            accion=f"Loss Ratio promedio de {lr_prom:.2f} — márgenes prácticamente nulos. Repricing urgente."
        elif lr_prom > lr_target:
            cat="🟡 REVISAR"; cls="box-warn"
            accion=f"LR promedio {lr_prom:.3f} supera el objetivo {lr_target:.0%}. Evaluar repricing en próxima renovación."
        elif lr_prom <= 0.55 and (lr_s > lr_target).mean() < 0.2:
            cat="🟢 SANA"; cls="box-ok"
            accion=f"LR promedio {lr_prom:.3f} — cartera rentable y consistente. Candidata a incrementar participación."
        else:
            cat="🔵 MONITOREAR"; cls="box-info"
            accion=f"LR promedio {lr_prom:.3f}. Dentro del objetivo, vigilar tendencia."

    extras = []
    if len(avg_s)>=2 and (avg_s.iloc[-1]-avg_s.iloc[0])/avg_s.iloc[0]>0.15:
        extras.append(f"costo/servicio +{(avg_s.iloc[-1]-avg_s.iloc[0])/avg_s.iloc[0]*100:.0f}%")
    if len(clts_s)>=2 and (clts_s.iloc[-1]-clts_s.iloc[0])/clts_s.iloc[0]>0.20:
        extras.append(f"base de clientes +{(clts_s.iloc[-1]-clts_s.iloc[0])/clts_s.iloc[0]*100:.0f}%")
    if len(clts_s)>=2 and (clts_s.iloc[-1]-clts_s.iloc[0])/clts_s.iloc[0]<-0.10:
        extras.append(f"pérdida de clientes {(clts_s.iloc[-1]-clts_s.iloc[0])/clts_s.iloc[0]*100:.0f}%")
    if len(freq_s)>0 and freq_s.iloc[-1]>freq_alerta:
        extras.append(f"frecuencia en alerta ({freq_s.iloc[-1]*1000:.1f}‰)")
    extras_str = "  |  " + " · ".join(extras) if extras else ""

    badge_nueva = (' &nbsp;<span style="background:#fef3c7;color:#92400e;padding:2px 6px;'
                   'border-radius:4px;font-size:0.78rem">🆕 estadísticas preliminares</span>'
                   if es_nueva else "")

    st.markdown(
        f'<div class="{cls}"><b>{c}</b>{tag_edad} &nbsp;·&nbsp; {cat} &nbsp;·&nbsp; '
        f'{"LR: <b>" + f"{lr_prom:.3f}</b> {lr_trend}" if lr_prom is not None else "Fee for Service"}'
        f'{extras_str}{badge_nueva}<br><small>{accion}</small></div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────────────────
# SECCIÓN 9 — SÍNTESIS EJECUTIVA
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">9 · Síntesis Ejecutiva</div>', unsafe_allow_html=True)

criticas   = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].dropna().mean() > 0.90]
revisar    = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].dropna().mean() > lr_target and c not in criticas]
sanas      = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].dropna().mean() <= 0.55]
costo_alza = [c for c in carteras if c in avg_pivot.columns and len(avg_pivot[c].dropna())>=2
              and (avg_pivot[c].dropna().iloc[-1]-avg_pivot[c].dropna().iloc[0])/avg_pivot[c].dropna().iloc[0]>0.15]
crec_clts  = [c for c in carteras if c in clts_pivot.columns and len(clts_pivot[c].dropna())>=2
              and (clts_pivot[c].dropna().iloc[-1]-clts_pivot[c].dropna().iloc[0])/clts_pivot[c].dropna().iloc[0]>0.20]
maduras    = [c for c in carteras if c in rev_pivot.columns and rev_pivot[c].notna().sum()>=18]
medias     = [c for c in carteras if c in rev_pivot.columns and 6<=rev_pivot[c].notna().sum()<18]
nuevas     = [c for c in carteras if c in rev_pivot.columns and rev_pivot[c].notna().sum()<6]

lines = [
    f"**Análisis basado en {n_meses} períodos** ({mes_disp.get(meses_ord[0],'?')} → "
    f"{mes_disp.get(meses_ord[-1],'?')}) · {len(carteras)} carteras activas.",""
]
if nuevas:   lines.append(f"🆕 **Carteras nuevas** (< 6 meses): {', '.join(nuevas)}. Estadísticas preliminares.")
if medias:   lines.append(f"📋 **Carteras en desarrollo** (6–18 meses): {', '.join(medias)}.")
if maduras:  lines.append(f"✅ **Carteras maduras** (≥ 18 meses): {', '.join(maduras)}. Alta confianza estadística.")
if not en_riesgo.empty:
    top = participacion.idxmax()
    lines.append(f"⚠️ **Concentración de revenue**: {top} representa {participacion[top]:.1f}% del total.")
else:
    lines.append(f"✅ **Concentración saludable**: ninguna cartera supera el {umbral_conc}%.")
if criticas:
    lines.append(f"🔴 **Carteras críticas** (LR > 90%): {', '.join(criticas)}. Repricing urgente.")
if revisar:
    lines.append(f"🟡 **Carteras a revisar** (LR > {lr_target:.0%}): {', '.join(revisar)}.")
if sanas:
    lines.append(f"🟢 **Carteras sanas** (LR ≤ 55%): {', '.join(sanas)}. Candidatas a mayor participación.")
if costo_alza:
    lines.append(f"📈 **Inflación operativa**: {', '.join(costo_alza)} con costo/servicio +15% en el período.")
if crec_clts:
    lines.append(f"👥 **Crecimiento de cartera**: {', '.join(crec_clts)} crecieron >20% en clientes.")
lines.append(f"🎯 **Acción prioritaria**: "
    + (f"repricing de {criticas[0]}" if criticas else
       (f"revisar condiciones de {revisar[0]}" if revisar else
        "mantener monitoreo mensual del Loss Ratio y costo promedio")))

st.markdown(
    '<div class="ai-box"><h3>🔶 Síntesis Estratégica — Connect Assistance México</h3>'
    + ''.join([f'<p>{l}</p>' for l in lines if l])
    + f'<p style="opacity:0.4;font-size:0.75rem;margin-top:14px">Generado automáticamente · '
    f'{len(carteras)} carteras · {n_meses} períodos · {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>'
    '</div>',
    unsafe_allow_html=True
)

st.markdown("---")
st.caption("Connect Assistance México · Análisis Operativo del Portafolio · Universidad Panamericana · IA para el Análisis Financiero")
