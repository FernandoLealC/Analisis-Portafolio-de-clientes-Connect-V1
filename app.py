import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
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
    <p>Comportamiento por cartera · Temporalidad · Usabilidad · Costo · Loss Ratio · Markowitz sobre rentabilidad real</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── CONSTANTES ──
SECCIONES_MAPA = {
    'clientes':   ('KPIs - Number of Clients',       0.009, 0.030),
    'servicios':  ('KPIs - Service Count External',  0.0,   9999),
    'frecuencia': ('Service Frequency',              0.0,   1.0),
    'revenue':    ('Revenue - Sales',                0.0,   9e9),
    'costo_svc':  ('Service Costs External',         0.0,   9e9),
    'avg_costo':  ('Average Service Cost',           0.0,   9e9),
    'gp_at_risk': ('Gross Profit At Risk',          -9e9,   9e9),
    'loss_ratio': ('Loss Ratio %',                   0.0,   5.0),
}

CARTERAS_VALIDAS = [
    'Afirme','Crabi','HDI Seguros - Bajio','HDI Seguros - Financieras',
    'HDI Seguros - Motos','HDI Seguros - MX','HDI Seguros - Occidente',
    'Kavak','Seguros Atlas - Auto','Seguros Atlas - Equipo Pesado',
    'Seguros El Potosi','Seguros El Potosi - ACMX','Tesla - MX','Clupp - Auto',
]

PAL = px.colors.qualitative.D3 + px.colors.qualitative.Plotly

# ─────────────────────────────────────────────────────────
@st.cache_data(show_spinner="📂 Procesando reportes Sage Intacct...")
def procesar_todo(bytes_list, nombres_list):
    import io

    def parse_fecha(nombre, df_raw):
        for _, row in df_raw.head(10).iterrows():
            for cell in row:
                if isinstance(cell, str) and 'As of' in cell:
                    m = re.search(r'(\d{2}/\d{2}/\d{4})', cell)
                    if m:
                        try: return datetime.strptime(m.group(1), '%m/%d/%Y')
                        except: pass
        # desde nombre del archivo
        for pat in [r'(\d{4})[-_]?(\d{2})', r'(\d{2})[-_]?(\d{2})[-_]?(\d{2})']:
            m = re.search(pat, nombre)
            if m:
                try: return datetime.strptime(nombre[:7].replace('_','-'), '%Y-%m')
                except: pass
        return None

    # ── Patrones de sección — acepta Budget, Forecast 1, Forecast 2 ──
    # Cada var tiene lista de patrones alternativos para manejar variaciones entre años
    SECTION_PATTERNS_LOCAL = [
        ('clientes',   [r'kpis\s*-\s*number of clients']),
        ('servicios',  [r'kpis\s*-\s*service count external',
                        r'kpis\s*-\s*service count all']),  # variante 2024
        ('frecuencia', [r'^service frequency$']),
        ('revenue',    [r'^revenue\s*-\s*sales$']),
        ('costo_svc',  [r'^service costs external$']),
        ('avg_costo',  [r'^average service cost']),
        ('gp_at_risk', [r'^gross profit at risk']),
        ('loss_ratio', [r'^loss ratio\s*%$']),
    ]
    SKIP_RE = re.compile(
        r'^(total|cost of|gross profit fee|service costs external\s*$|revenue\s*-\s*services)',
        re.I
    )

    # Palabras que indican sub-cartera → NO matchear la cartera base
    _EXCL = {
        'despachos','moto','motos','siniestro','pesado','acmx',
        'fleet','demand','services','compa','employees','empleados',
        'blu','spee','dee',
    }

    def _match_cartera(nombre):
        s = nombre.strip()
        sl = s.lower()
        if not sl or sl in ('nan','none',''): return None
        # 1. Exact match
        for c in CARTERAS_VALIDAS:
            if c.lower() == sl: return c
        # 2. Containment — solo si no hay palabras extra significativas
        for c in CARTERAS_VALIDAS:
            cl = c.lower()
            if cl in sl and len(cl) > 4:
                extra = sl.replace(cl,'').strip(' -').lower()
                extra_words = set(extra.split())
                if extra_words & _EXCL: continue
                if {w for w in extra_words if len(w) > 1}: continue
                return c
        # 3. Word overlap — mínimo 75% de palabras del candidato en común
        s_words = {w for w in sl.split() if len(w) > 2}
        for c in CARTERAS_VALIDAS:
            c_words = {w for w in c.lower().split() if len(w) > 2}
            common = s_words & c_words
            if len(common) >= 2 and len(common) >= len(c_words) * 0.75:
                if not (s_words - c_words) & _EXCL:
                    return c
        return None

    def _primer_numero(row, max_cols=6):
        for ci in range(1, max_cols):
            try:
                v = str(row.iloc[ci]).strip().replace(',','')
                if v in ('','nan','None'): continue
                return float(v)
            except: pass
        return None

    def extraer_archivo(df_raw):
        """Parser robusto: detecta secciones por regex, ignora sangría y subsecciones."""
        secs = []
        seen_vars = set()
        for i, row in df_raw.iterrows():
            c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
            if not c0 or c0.lower().startswith('total'): continue
            for var, patterns in SECTION_PATTERNS_LOCAL:
                matched_pat = any(re.search(p, c0.lower()) for p in patterns)
                if matched_pat:
                    if var == 'costo_svc' and 'costo_svc' in seen_vars: continue
                    secs.append((i, var))
                    seen_vars.add(var)
                    break

        rangos = {}
        for idx, (fila, var) in enumerate(secs):
            if var in rangos: continue
            sig = secs[idx+1][0] if idx+1 < len(secs) else len(df_raw)
            rangos[var] = (fila+1, sig)

        resultado = {var: {} for var in [s[1] for s in secs]}
        for var, (ini, fin) in rangos.items():
            for i in range(ini, min(fin, len(df_raw))):
                row = df_raw.iloc[i]
                c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
                c1 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                if not c0 and not c1: continue
                if c0.lower().startswith('total'): continue
                if SKIP_RE.search(c0.lower()): continue
                nombre = c0 if c0 and c0.lower() not in ('nan','') else c1
                cart = _match_cartera(nombre)
                if not cart: continue
                val = _primer_numero(row)
                if val is not None:
                    resultado[var][cart] = val
        return resultado

    records = []
    errores = []

    for idx, (fbytes, fname) in enumerate(zip(bytes_list, nombres_list)):
        try:
            df_raw = pd.read_excel(io.BytesIO(fbytes), header=None)
            fecha = parse_fecha(fname, df_raw)
            if not fecha:
                errores.append(f"No se pudo determinar fecha de {fname}")
                continue
            mes_label = fecha.strftime('%Y-%m')
            mes_display = fecha.strftime('%b-%Y')

            # Extraer todas las secciones con el parser robusto
            extraidos = extraer_archivo(df_raw)

            # Construir registros por cartera
            todas_carteras = set()
            for d in extraidos.values():
                todas_carteras.update(d.keys())

            for cart in todas_carteras:
                rev  = extraidos['revenue'].get(cart)
                cost = extraidos['costo_svc'].get(cart)
                clts = extraidos['clientes'].get(cart)
                svcs = extraidos['servicios'].get(cart)
                freq = extraidos['frecuencia'].get(cart)
                avg  = extraidos['avg_costo'].get(cart)
                gp   = extraidos['gp_at_risk'].get(cart)
                lr   = extraidos['loss_ratio'].get(cart)

                if not rev or rev <= 0:
                    continue

                records.append({
                    'Mes': mes_label,
                    'Mes_Display': mes_display,
                    'Cartera': cart,
                    'Revenue': rev,
                    'Costo_Servicio': cost,
                    'Clientes': clts,
                    'Servicios': svcs,
                    'Frecuencia': freq,
                    'Avg_Costo_Svc': avg,
                    'GP_At_Risk': gp,
                    'Loss_Ratio': lr,
                    # Derivadas
                    'Margen_GP': (rev-cost)/rev if cost and rev > 0 else None,
                    'GP_por_Cliente': gp/clts if gp and clts and clts > 0 else None,
                    'Rev_por_Cliente': rev/clts if clts and clts > 0 else None,
                    'Costo_por_Cliente': cost/clts if cost and clts and clts > 0 else None,
                })

        except Exception as e:
            errores.append(f"{fname}: {e}")

    if not records:
        return None, errores, "No se pudieron extraer datos."

    df = pd.DataFrame(records).sort_values(['Cartera','Mes']).reset_index(drop=True)

    return df, errores, None


@st.cache_data(show_spinner="🎲 Simulación Monte Carlo...")
def monte_carlo_lr(mu_t, cov_flat, n_prov, n_sim, carteras_t):
    """Markowitz sobre (1 - Loss Ratio): mayor = mejor, minimizar volatilidad."""
    mu_arr  = np.array(mu_t)
    cov_mat = np.array(cov_flat).reshape(n_prov, n_prov)
    carteras = list(carteras_t)
    np.random.seed(42)
    res = np.zeros((n_sim, 3 + n_prov))
    for i in range(n_sim):
        w = np.random.random(n_prov); w /= w.sum()
        r_port  = float(np.dot(w, mu_arr))
        vol_port = float(np.sqrt(w @ cov_mat @ w))
        res[i] = [r_port, vol_port, r_port/vol_port if vol_port>0 else 0] + list(w)
    df_s = pd.DataFrame(res, columns=['Rentabilidad','Riesgo','Sharpe']+carteras)
    return df_s, df_s.loc[df_s['Sharpe'].idxmax()], df_s.loc[df_s['Riesgo'].idxmin()]

# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    archivos = st.file_uploader(
        "📂 Reportes KPIs Sage (.xlsx)",
        type=["xlsx"], accept_multiple_files=True,
        help="Sube todos los meses disponibles. Funciona con Budget o Forecast."
    )
    st.markdown("---")
    lr_target  = st.slider("📉 Loss Ratio objetivo (máx)", 40, 85, 65, 5) / 100
    freq_alerta = st.slider("⚡ Alerta frecuencia (sv/cliente)", 5, 25, 12, 1) / 1000
    umbral_conc = st.slider("⚠️ Umbral concentración revenue (%)", 15, 40, 25, 5)
    n_sim = st.select_slider("🎲 Simulaciones Monte Carlo", [1000,3000,5000,10000,20000], 5000)
    st.markdown("---")
    carteras_sel = st.multiselect(
        "🔍 Filtrar carteras",
        options=CARTERAS_VALIDAS,
        default=[],
        help="Deja vacío para ver todas"
    )
    st.caption("Connect Assistance México\nAnálisis Operativo del Portafolio\nUniversidad Panamericana")

if not archivos:
    st.info("👈 Sube los reportes KPIs mensuales de Sage Intacct.")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("""
        **¿Qué archivos?**
        - `KPIs - Actuals vs Budget by Segment.xlsx`
        - `KPIs - Actuals vs Forecast by Segment.xlsx`
        - Uno por mes — sube todos juntos
        """)
    with c2:
        st.markdown("""
        **¿Qué analiza?**
        1. Concentración de revenue
        2. Clientes: crecimiento y base
        3. Servicios y temporalidad
        4. Frecuencia de uso (usabilidad)
        5. Costo promedio por servicio
        6. Loss Ratio histórico
        7. Markowitz sobre rentabilidad real
        8. Señales de acción por cartera
        """)
    st.stop()

# ── PROCESAR ──
fb = [f.read() for f in archivos]
fn = [f.name for f in archivos]
df_all, errores, error_fatal = procesar_todo(fb, fn)

if error_fatal:
    st.error(f"❌ {error_fatal}")
    st.stop()
if errores:
    with st.expander(f"⚠️ {len(errores)} advertencia(s) al procesar"):
        for e in errores: st.write(f"- {e}")

# Filtrar carteras si se seleccionaron
if carteras_sel:
    df_all = df_all[df_all['Cartera'].isin(carteras_sel)]

carteras = sorted(df_all['Cartera'].unique().tolist())
meses_ord = sorted(df_all['Mes'].unique().tolist())
n_meses = len(meses_ord)

# Etiquetas display
mes_display_map = df_all.groupby('Mes')['Mes_Display'].first().to_dict()
xticks = [mes_display_map.get(m, m) for m in meses_ord]

st.success(f"✅ **{len([f for f in archivos])} archivos** · **{len(carteras)} carteras** · **{n_meses} períodos** (de {mes_display_map.get(meses_ord[0],'?')} a {mes_display_map.get(meses_ord[-1],'?')})")

def pivot(col, fillna=None):
    """Pivotea datos manteniendo NaN donde la cartera no existía ese mes.
    fillna solo se usa cuando se necesita explícitamente (ej. para cálculos de suma).
    Las gráficas plotly con NaN automáticamente muestran gaps (sin conectar puntos)."""
    p = df_all.pivot_table(index='Mes', columns='Cartera', values=col, aggfunc='mean')
    p = p.reindex(meses_ord)  # mantiene NaN donde no hay datos
    if fillna is not None: p = p.fillna(fillna)
    return p

# ─────────────────────────────────────────────────────────
# SECCIÓN 0 — CONCENTRACIÓN DE REVENUE
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">0 · Concentración de Revenue por Cartera</div>', unsafe_allow_html=True)

rev_pivot = pivot('Revenue')
rev_prom  = rev_pivot.mean()
rev_total = rev_prom.sum()
participacion = (rev_prom / rev_total * 100).sort_values(ascending=False)

c1,c2 = st.columns([1.1,1])
with c1:
    df_conc = pd.DataFrame({
        'Cartera': participacion.index,
        'Revenue Prom. ($)': rev_prom[participacion.index].round(0),
        'Participación (%)': participacion.values.round(1),
    }).reset_index(drop=True)
    def hl(v): return "background-color:#fdecea;font-weight:bold" if isinstance(v,float) and v > umbral_conc else ""
    st.dataframe(
        df_conc.style.map(hl, subset=['Participación (%)'])
            .format({'Revenue Prom. ($)':'${:,.0f}','Participación (%)':'{:.1f}%'}),
        use_container_width=True, hide_index=True
    )
    en_riesgo = participacion[participacion > umbral_conc]
    for c,p in en_riesgo.items():
        st.markdown(f'<div class="box-warn">⚠️ <b>{c}</b> concentra <b>{p:.1f}%</b> del revenue — supera umbral {umbral_conc}%.</div>', unsafe_allow_html=True)
    if en_riesgo.empty:
        st.markdown(f'<div class="box-ok">✅ Ninguna cartera supera el umbral de {umbral_conc}%.</div>', unsafe_allow_html=True)

with c2:
    colors = ["#e53935" if participacion[c] > umbral_conc else "#001d3d" for c in participacion.index]
    fig = go.Figure(go.Pie(labels=participacion.index, values=participacion.values,
        hole=0.45, textinfo="label+percent", marker=dict(colors=colors)))
    fig.update_layout(title="Concentración actual", height=320, showlegend=False, margin=dict(t=40,b=5,l=5,r=5))
    st.plotly_chart(fig, use_container_width=True)

# Revenue apilado en el tiempo
fig_rev = go.Figure()
for i,c in enumerate(carteras):
    if c in rev_pivot.columns:
        fig_rev.add_trace(go.Bar(
            x=xticks, y=rev_pivot[c].values,
            name=c, marker_color=PAL[i % len(PAL)],
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>${{y:,.0f}}<extra></extra>"
        ))
fig_rev.update_layout(barmode='stack', title="Revenue mensual acumulado por cartera",
    xaxis_title="Mes", yaxis_title="Revenue ($)",
    height=370, legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_rev, use_container_width=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 1 — CLIENTES: CRECIMIENTO Y BASE
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">1 · Clientes Activos — Crecimiento y Base por Cartera</div>', unsafe_allow_html=True)

clts_pivot = pivot('Clientes')

fig_clts = go.Figure()
for i,c in enumerate(carteras):
    if c in clts_pivot.columns and clts_pivot[c].notna().sum() >= 2:
        fig_clts.add_trace(go.Scatter(
            x=xticks, y=clts_pivot[c].values,
            mode='lines+markers', name=c,
            line=dict(width=2, color=PAL[i % len(PAL)]),
            marker=dict(size=5),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>{{y:,.0f}} clientes<extra></extra>"
        ))
fig_clts.update_layout(title="Evolución de Clientes Activos por Cartera",
    xaxis_title="Mes", yaxis_title="Clientes activos",
    height=400, hovermode='x unified',
    legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_clts, use_container_width=True)

# Crecimiento % de clientes (primer vs último mes disponible)
crec_data = []
for c in carteras:
    if c in clts_pivot.columns:
        serie = clts_pivot[c].dropna()
        if len(serie) >= 2:
            ini, fin = serie.iloc[0], serie.iloc[-1]
            crec = (fin - ini) / ini * 100
            crec_data.append({'Cartera': c, 'Inicio': ini, 'Fin': fin, 'Crecimiento (%)': crec})
if crec_data:
    df_crec = pd.DataFrame(crec_data).sort_values('Crecimiento (%)', ascending=False)
    def hl_crec(v): 
        if isinstance(v, float):
            if v > 20: return "background-color:#e8f5e9;color:#1b5e20"
            if v < -10: return "background-color:#fdecea;color:#7f1d1d"
        return ""
    st.dataframe(
        df_crec.style.map(hl_crec, subset=['Crecimiento (%)'])
            .format({'Inicio':'{:,.0f}','Fin':'{:,.0f}','Crecimiento (%)':'{:+.1f}%'}),
        use_container_width=True, hide_index=True
    )

# ─────────────────────────────────────────────────────────
# SECCIÓN 2 — SERVICIOS Y TEMPORALIDAD
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">2 · Servicios y Temporalidad — ¿Cuándo se dispara la demanda?</div>', unsafe_allow_html=True)

svc_pivot = pivot('Servicios')

# Heatmap de servicios por mes/cartera
carteras_con_svc = [c for c in carteras if c in svc_pivot.columns and svc_pivot[c].notna().sum() >= 2]
if carteras_con_svc:
    mat_svc = svc_pivot[carteras_con_svc].T
    fig_heat = px.imshow(mat_svc.values,
        x=xticks, y=carteras_con_svc,
        color_continuous_scale='RdYlGn_r',
        labels=dict(color='Servicios'),
        aspect='auto',
        title="Heatmap de Servicios por Cartera y Mes  (rojo = pico de demanda)")
    fig_heat.update_layout(height=max(300, len(carteras_con_svc)*35 + 80), margin=dict(t=55,b=20))
    st.plotly_chart(fig_heat, use_container_width=True)
    st.markdown('<div class="box-info">💡 Los <b>picos rojos</b> indican los meses de mayor demanda de servicios por cartera. Identifica si hay coincidencia entre carteras (riesgo sistémico de costo) o si los picos están dispersos (diversificación natural).</div>', unsafe_allow_html=True)

# Líneas de servicios
fig_svc = go.Figure()
for i,c in enumerate(carteras_con_svc):
    fig_svc.add_trace(go.Scatter(
        x=xticks, y=svc_pivot[c].values,
        mode='lines+markers', name=c,
        line=dict(width=2, color=PAL[i % len(PAL)]),
        hovertemplate=f"<b>{c}</b><br>%{{x}}<br>{{y:,.0f}} servicios<extra></extra>"
    ))
fig_svc.update_layout(title="Evolución de Servicios Mensuales por Cartera",
    xaxis_title="Mes", yaxis_title="Número de servicios",
    height=370, hovermode='x unified',
    legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_svc, use_container_width=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 3 — FRECUENCIA DE USO (USABILIDAD)
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">3 · Frecuencia de Uso — Usabilidad e Impacto en el Costo</div>', unsafe_allow_html=True)

freq_pivot = pivot('Frecuencia')

st.markdown(f'<div class="box-info">💡 <b>Frecuencia = servicios / clientes activos.</b> Cuando la frecuencia sube, más clientes usan el servicio — lo que encarece el costo total aunque el precio por certificado no cambie. La línea de alerta está en <b>{freq_alerta*1000:.0f}‰</b> (configurable en sidebar).</div>', unsafe_allow_html=True)

fig_freq = go.Figure()
for i,c in enumerate(carteras):
    if c in freq_pivot.columns and freq_pivot[c].notna().sum() >= 2:
        fig_freq.add_trace(go.Scatter(
            x=xticks, y=freq_pivot[c].values * 100,  # en porcentaje
            mode='lines+markers', name=c,
            line=dict(width=2, color=PAL[i % len(PAL)]),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>Frecuencia: %{{y:.3f}}%<extra></extra>"
        ))
fig_freq.add_hline(y=freq_alerta*100, line_dash='dot', line_color='#f15b2b',
    annotation_text=f"Alerta {freq_alerta*1000:.0f}‰",
    annotation_font=dict(color='#f15b2b', size=10))
fig_freq.update_layout(title="Frecuencia de Uso por Cartera (% de clientes que usaron el servicio)",
    xaxis_title="Mes", yaxis_title="Frecuencia (%)",
    height=400, hovermode='x unified',
    legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_freq, use_container_width=True)

# Correlación de frecuencias entre carteras
freq_carteras = [c for c in carteras if c in freq_pivot.columns and freq_pivot[c].notna().sum() >= 3]
if len(freq_carteras) >= 2:
    corr_freq = freq_pivot[freq_carteras].corr().round(2)
    fig_corr = px.imshow(corr_freq, text_auto=True,
        color_continuous_scale='RdBu_r', zmin=-1, zmax=1,
        title="Correlación de frecuencia de uso entre carteras  (alta = picos de costo simultáneos)",
        aspect='auto')
    fig_corr.update_layout(height=380, margin=dict(t=55,b=10))
    st.plotly_chart(fig_corr, use_container_width=True)
    st.markdown('<div class="box-info">💡 Carteras con <b>alta correlación de frecuencia</b> tienen sus picos de costo en los mismos meses — no diversifican el riesgo operativo. Carteras con correlación baja o negativa absorben demanda en momentos distintos.</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 4 — COSTO PROMEDIO POR SERVICIO
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">4 · Costo Promedio por Servicio — Tendencia e Inflación Operativa</div>', unsafe_allow_html=True)

avg_pivot = pivot('Avg_Costo_Svc')

st.markdown('<div class="box-info">💡 El costo promedio por servicio refleja la <b>inflación operativa</b>. Si sube sistemáticamente sin que el precio contratado haya cambiado, el margen se comprime mes a mes aunque el volumen sea estable.</div>', unsafe_allow_html=True)

fig_avg = go.Figure()
for i,c in enumerate(carteras):
    if c in avg_pivot.columns and avg_pivot[c].notna().sum() >= 2:
        y = avg_pivot[c].values
        fig_avg.add_trace(go.Scatter(
            x=xticks, y=y,
            mode='lines+markers', name=c,
            line=dict(width=2, color=PAL[i % len(PAL)]),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>${{y:.2f}} / servicio<extra></extra>"
        ))
        # Línea de tendencia
        x_num = np.arange(len([v for v in y if not np.isnan(v) if v is not None]))
        y_clean = np.array([v for v in y if v is not None and not np.isnan(v)])
        if len(y_clean) >= 3:
            z = np.polyfit(x_num, y_clean, 1)
            p = np.poly1d(z)
            fig_avg.add_trace(go.Scatter(
                x=xticks[-len(y_clean):], y=p(x_num),
                mode='lines', name=f"{c} (tendencia)",
                line=dict(width=1, dash='dot', color=PAL[i % len(PAL)]),
                showlegend=False, opacity=0.5,
            ))
fig_avg.update_layout(title="Costo Promedio por Servicio — con líneas de tendencia",
    xaxis_title="Mes", yaxis_title="Costo por servicio ($)",
    height=420, hovermode='x unified',
    legend=dict(orientation='h',y=-0.3), margin=dict(t=50,b=10))
st.plotly_chart(fig_avg, use_container_width=True)

# Tabla resumen de variación de costo
avg_resumen = []
for c in carteras:
    if c in avg_pivot.columns:
        serie = avg_pivot[c].dropna()
        if len(serie) >= 2:
            ini, fin = serie.iloc[0], serie.iloc[-1]
            var_pct = (fin - ini) / ini * 100
            avg_resumen.append({
                'Cartera': c,
                'Costo inicial ($)': ini,
                'Costo actual ($)': fin,
                'Variación (%)': var_pct,
                'Tendencia': '📈 Subiendo' if var_pct > 5 else ('📉 Bajando' if var_pct < -5 else '➡️ Estable'),
            })
if avg_resumen:
    df_avg = pd.DataFrame(avg_resumen).sort_values('Variación (%)', ascending=False)
    def hl_var(v):
        if isinstance(v, float):
            if v > 20: return "background-color:#fdecea"
            if v > 10: return "background-color:#fff8e1"
            if v < -5: return "background-color:#e8f5e9"
        return ""
    st.dataframe(
        df_avg.style.map(hl_var, subset=['Variación (%)'])
            .format({'Costo inicial ($)':'${:.2f}','Costo actual ($)':'${:.2f}','Variación (%)':'{:+.1f}%'}),
        use_container_width=True, hide_index=True
    )

# ─────────────────────────────────────────────────────────
# SECCIÓN 5 — LOSS RATIO HISTÓRICO Y TEMPORALIDAD
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">5 · Loss Ratio — Historial, Alertas y Temporalidad</div>', unsafe_allow_html=True)

lr_pivot = pivot('Loss_Ratio')

st.markdown(f'<div class="box-info">💡 <b>Loss Ratio = Costo de Servicio / Revenue.</b> La línea roja en {lr_target:.0%} es el límite objetivo. Valores > 1.0 indican pérdida directa en el servicio. Observa si los picos son estacionales (temporada alta) o si hay deterioro estructural sostenido.</div>', unsafe_allow_html=True)

fig_lr = go.Figure()
for i,c in enumerate(carteras):
    if c in lr_pivot.columns and lr_pivot[c].notna().sum() >= 2:
        y = lr_pivot[c].values
        fig_lr.add_trace(go.Scatter(
            x=xticks, y=y,
            mode='lines+markers', name=c,
            line=dict(width=2.5, color=PAL[i % len(PAL)]),
            marker=dict(size=5),
            hovertemplate=f"<b>{c}</b><br>%{{x}}<br>LR: %{{y:.3f}}<extra></extra>"
        ))
fig_lr.add_hline(y=lr_target, line_dash='dot', line_color='#f15b2b', line_width=2,
    annotation_text=f"Objetivo {lr_target:.0%}",
    annotation_font=dict(color='#f15b2b', size=11))
fig_lr.add_hline(y=1.0, line_dash='solid', line_color='#7f1d1d', line_width=1.5,
    annotation_text="LR=1.0: sin margen", annotation_position='bottom right',
    annotation_font=dict(color='#7f1d1d', size=9))
fig_lr.update_layout(
    title="Evolución del Loss Ratio por Cartera  (< línea naranja = saludable)",
    xaxis_title="Mes", yaxis_title="Loss Ratio",
    height=450, hovermode='x unified',
    legend=dict(orientation='h',y=-0.3), margin=dict(t=55,b=10)
)
st.plotly_chart(fig_lr, use_container_width=True)

# Heatmap de Loss Ratio
lr_carteras = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].notna().sum() >= 2]
if lr_carteras:
    mat_lr = lr_pivot[lr_carteras].T
    fig_lr_heat = px.imshow(mat_lr.values,
        x=xticks, y=lr_carteras,
        color_continuous_scale='RdYlGn_r', zmin=0, zmax=1.2,
        labels=dict(color='Loss Ratio'),
        aspect='auto',
        title="Heatmap Loss Ratio  (rojo intenso = cartera en problema ese mes)")
    fig_lr_heat.update_layout(height=max(300, len(lr_carteras)*35+80), margin=dict(t=55,b=10))
    st.plotly_chart(fig_lr_heat, use_container_width=True)

# Resumen LR
lr_resumen = []
for c in carteras:
    if c in lr_pivot.columns:
        serie = lr_pivot[c].dropna()
        if len(serie) >= 1:
            pct_sobre = (serie > lr_target).mean() * 100
            lr_resumen.append({
                'Cartera': c,
                'Meses con datos': len(serie),
                'LR Promedio': serie.mean(),
                'LR Máximo': serie.max(),
                'LR Mínimo': serie.min(),
                'Meses sobre objetivo (%)': pct_sobre,
                'Estado': '🔴 CRÍTICO' if serie.mean() > 0.85 else (
                          '🟡 REVISAR' if serie.mean() > lr_target else '🟢 OK'),
            })
if lr_resumen:
    df_lr_res = pd.DataFrame(lr_resumen).sort_values('LR Promedio', ascending=False)
    def hl_lr(v):
        if isinstance(v, float):
            if v > 0.85: return "background-color:#fdecea;font-weight:bold"
            if v > lr_target: return "background-color:#fff8e1"
        return ""
    st.dataframe(
        df_lr_res.style.map(hl_lr, subset=['LR Promedio','LR Máximo'])
            .format({'LR Promedio':'{:.3f}','LR Máximo':'{:.3f}','LR Mínimo':'{:.3f}',
                     'Meses sobre objetivo (%)':'{:.0f}%'}),
        use_container_width=True, hide_index=True
    )

# ─────────────────────────────────────────────────────────
# SECCIÓN 6 — REVENUE POR CLIENTE Y MARGEN POR CLIENTE
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">6 · Ingreso y Costo por Cliente — Rentabilidad Real por Certificado</div>', unsafe_allow_html=True)

rpc_pivot  = pivot('Rev_por_Cliente')
cpc_pivot  = pivot('Costo_por_Cliente')
gpc_pivot  = pivot('GP_por_Cliente')

c1,c2 = st.columns(2)
with c1:
    fig_rpc = go.Figure()
    for i,c in enumerate(carteras):
        if c in rpc_pivot.columns and rpc_pivot[c].notna().sum() >= 2:
            fig_rpc.add_trace(go.Scatter(
                x=xticks, y=rpc_pivot[c].values,
                mode='lines+markers', name=c,
                line=dict(width=2, color=PAL[i % len(PAL)]),
                hovertemplate=f"<b>{c}</b><br>${{y:.3f}}/cliente<extra></extra>"
            ))
    fig_rpc.update_layout(title="Revenue por cliente ($)",
        xaxis_title="Mes", yaxis_title="$/cliente",
        height=340, hovermode='x unified',
        legend=dict(orientation='h',y=-0.4), margin=dict(t=50,b=10))
    st.plotly_chart(fig_rpc, use_container_width=True)

with c2:
    fig_gpc = go.Figure()
    for i,c in enumerate(carteras):
        if c in gpc_pivot.columns and gpc_pivot[c].notna().sum() >= 2:
            fig_gpc.add_trace(go.Scatter(
                x=xticks, y=gpc_pivot[c].values,
                mode='lines+markers', name=c,
                line=dict(width=2, color=PAL[i % len(PAL)]),
                hovertemplate=f"<b>{c}</b><br>GP ${{y:.3f}}/cliente<extra></extra>"
            ))
    fig_gpc.update_layout(title="GP At Risk por cliente ($)",
        xaxis_title="Mes", yaxis_title="GP$/cliente",
        height=340, hovermode='x unified',
        legend=dict(orientation='h',y=-0.4), margin=dict(t=50,b=10))
    st.plotly_chart(fig_gpc, use_container_width=True)

# ─────────────────────────────────────────────────────────
# SECCIÓN 7 — MARKOWITZ SOBRE LOSS RATIO INVERTIDO
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">7 · Optimización Markowitz — Portafolio por Rentabilidad Real (1 − Loss Ratio)</div>', unsafe_allow_html=True)

st.markdown("""
<div class="box-info">
💡 <b>¿Por qué (1 - Loss Ratio) y no el Margen GP?</b><br>
El Margen GP del reporte Sage es el margen "At Risk" del modelo de asistencia — no el margen operativo completo. 
Su rango es muy estrecho (85-99%) y no diferencia bien las carteras.<br>
El <b>Loss Ratio</b> en cambio varía entre 0.45 y 0.95 entre carteras y mide directamente 
cuánto del revenue se va en costo de servicio. 
<b>(1 - LR)</b> = rentabilidad operativa real: cuánto queda de cada peso de ingreso después del servicio. 
Esta variable sí tiene variación real, diferencia carteras y tiene significado estratégico.
</div>
""", unsafe_allow_html=True)

# Construir serie histórica de (1 - LR)
lr_hist = lr_pivot.copy()
rentab_pivot = 1 - lr_hist  # mayor = mejor

carteras_mk = [c for c in carteras if c in rentab_pivot.columns 
               and rentab_pivot[c].notna().sum() >= min_meses_mk
               and rentab_pivot[c].std() > 0]

excluidas_mk = [c for c in carteras if c in rentab_pivot.columns
                and 0 < rentab_pivot[c].notna().sum() < min_meses_mk]
if excluidas_mk:
    st.markdown(
        f'<div class="box-warn">📅 <b>{len(excluidas_mk)} cartera(s) excluida(s) del modelo Markowitz</b> '
        f'por tener menos de {min_meses_mk} meses de Loss Ratio: <b>{", ".join(excluidas_mk)}</b>. '
        f'Historial insuficiente para calcular volatilidad confiable. '
        f'Reduce el mínimo en el sidebar si quieres incluirlas con menos datos.</div>',
        unsafe_allow_html=True
    )

if len(carteras_mk) >= 2:
    mu_mk    = rentab_pivot[carteras_mk].mean()
    sigma_mk = rentab_pivot[carteras_mk].std()
    cov_mk   = rentab_pivot[carteras_mk].cov().values

    # Mapa riesgo-rentabilidad
    fig_mapa = go.Figure()
    for i,c in enumerate(carteras_mk):
        fig_mapa.add_trace(go.Scatter(
            x=[sigma_mk[c]], y=[mu_mk[c]],
            mode='markers+text', text=[c], textposition='top center',
            marker=dict(size=20, color=PAL[i % len(PAL)], line=dict(color='white',width=1.5)),
            name=c,
            hovertemplate=f"<b>{c}</b><br>Rentabilidad: {mu_mk[c]:.1%}<br>σ: {sigma_mk[c]:.4f}<extra></extra>"
        ))
    fig_mapa.add_hline(y=(1-lr_target), line_dash='dash', line_color='#f15b2b',
        annotation_text=f"Rentabilidad objetivo {1-lr_target:.0%}",
        annotation_font=dict(color='#f15b2b', size=9))
    fig_mapa.add_vline(x=sigma_mk.median(), line_dash='dot', line_color='#aaa', line_width=1)
    fig_mapa.add_hline(y=mu_mk.median(), line_dash='dot', line_color='#aaa', line_width=1)
    fig_mapa.update_layout(
        title="Mapa Riesgo–Rentabilidad  (esquina superior izquierda = ideal ⭐)",
        xaxis_title="Riesgo — Volatilidad de (1 - LR)",
        yaxis_title="Rentabilidad Promedio (1 - LR)",
        yaxis=dict(tickformat='.0%'),
        height=420, showlegend=False, margin=dict(t=55,b=30)
    )
    st.plotly_chart(fig_mapa, use_container_width=True)

    # Monte Carlo
    df_sim, opt, minr = monte_carlo_lr(
        tuple(mu_mk.values), tuple(cov_mk.flatten()),
        len(carteras_mk), n_sim, tuple(carteras_mk)
    )

    fig_front = go.Figure()
    fig_front.add_trace(go.Scatter(
        x=df_sim['Riesgo'], y=df_sim['Rentabilidad'],
        mode='markers',
        marker=dict(color=df_sim['Sharpe'], colorscale='Viridis', size=3, opacity=0.5,
                    colorbar=dict(title='Eficiencia', thickness=12, len=0.7)),
        name='Portafolios simulados',
        hovertemplate='Riesgo: %{x:.4f}<br>Rentabilidad: %{y:.1%}<extra></extra>'
    ))
    fig_front.add_trace(go.Scatter(
        x=[minr['Riesgo']], y=[minr['Rentabilidad']], mode='markers',
        marker=dict(symbol='diamond', size=18, color='#1976d2', line=dict(color='white',width=1.5)),
        name='🔵 Mínimo Riesgo',
    ))
    fig_front.add_trace(go.Scatter(
        x=[opt['Riesgo']], y=[opt['Rentabilidad']], mode='markers',
        marker=dict(symbol='star', size=24, color='#e53935', line=dict(color='white',width=1.5)),
        name='⭐ Portafolio Óptimo',
    ))
    # Distribución actual
    rev_ult = rev_pivot.iloc[-1] if len(rev_pivot) > 0 else None
    if rev_ult is not None:
        carts_comun = [c for c in carteras_mk if c in rev_ult.index and pd.notna(rev_ult[c])]
        if carts_comun:
            w_act = np.array([rev_ult[c] for c in carts_comun])
            w_act = w_act / w_act.sum()
            mu_act = np.array([mu_mk[c] for c in carts_comun])
            cov_act = rentab_pivot[carts_comun].cov().values
            r_act_val = float(np.dot(w_act, mu_act))
            v_act_val = float(np.sqrt(w_act @ cov_act @ w_act))
            fig_front.add_trace(go.Scatter(
                x=[v_act_val], y=[r_act_val], mode='markers',
                marker=dict(symbol='square', size=16, color='#f15b2b', line=dict(color='white',width=1.5)),
                name='🟠 Distribución Actual',
            ))

    fig_front.update_layout(
        title=f"Frontera Eficiente — Portafolio de Clientes Connect  ({n_sim:,} simulaciones)",
        xaxis_title="Riesgo (σ de la Rentabilidad)",
        yaxis_title="Rentabilidad (1 − Loss Ratio)",
        yaxis=dict(tickformat='.0%'),
        height=500, hovermode='closest',
        legend=dict(orientation='h',y=-0.18), margin=dict(t=55,b=20)
    )
    st.plotly_chart(fig_front, use_container_width=True)

    # Asignación óptima
    st.markdown("**Asignación óptima del portafolio:**")
    m1,m2,m3 = st.columns(3)
    m1.metric("📈 Rentabilidad Esperada", f"{opt['Rentabilidad']:.1%}")
    m2.metric("⚡ Riesgo (σ)", f"{opt['Riesgo']:.4f}")
    m3.metric("🏆 Eficiencia (Sharpe)", f"{opt['Sharpe']:.1f}")
    st.markdown("---")

    pesos = {c: opt[c] for c in carteras_mk}
    df_asig = pd.DataFrame({
        'Cartera': carteras_mk,
        'Peso Óptimo (%)': [pesos[c]*100 for c in carteras_mk],
        'Rentabilidad Prom. (1-LR)': [mu_mk[c] for c in carteras_mk],
        'Volatilidad σ': [sigma_mk[c] for c in carteras_mk],
        'LR Promedio': [lr_pivot[c].mean() if c in lr_pivot.columns else None for c in carteras_mk],
    }).sort_values('Peso Óptimo (%)', ascending=False).reset_index(drop=True)

    c1,c2 = st.columns([1.1,1])
    with c1:
        st.dataframe(
            df_asig.style.format({
                'Peso Óptimo (%)': '{:.1f}%',
                'Rentabilidad Prom. (1-LR)': '{:.1%}',
                'Volatilidad σ': '{:.4f}',
                'LR Promedio': '{:.3f}',
            }).background_gradient(subset=['Peso Óptimo (%)'], cmap='Greens')
              .background_gradient(subset=['Rentabilidad Prom. (1-LR)'], cmap='Blues'),
            use_container_width=True, hide_index=True
        )
    with c2:
        fig_dona = go.Figure(go.Pie(
            labels=df_asig['Cartera'], values=df_asig['Peso Óptimo (%)'],
            hole=0.45, textinfo='label+percent',
            marker=dict(colors=PAL[:len(df_asig)])
        ))
        fig_dona.update_layout(
            title="Distribución óptima del revenue",
            height=340, showlegend=False, margin=dict(t=45,b=10,l=10,r=10)
        )
        st.plotly_chart(fig_dona, use_container_width=True)
else:
    st.warning("⚠️ Se necesitan al menos 2 carteras con 3+ períodos de Loss Ratio para el modelo Markowitz.")

# ─────────────────────────────────────────────────────────
# SECCIÓN 8 — SEÑALES DE ACCIÓN POR CARTERA
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">8 · Señales de Acción por Cartera</div>', unsafe_allow_html=True)

st.markdown("Diagnóstico basado en Loss Ratio histórico, tendencia de costo, crecimiento de clientes y frecuencia de uso:")
st.markdown("")

for c in sorted(carteras):
    lr_serie  = lr_pivot[c].dropna()   if c in lr_pivot.columns  else pd.Series(dtype=float)
    avg_serie = avg_pivot[c].dropna()  if c in avg_pivot.columns else pd.Series(dtype=float)
    clts_serie = clts_pivot[c].dropna() if c in clts_pivot.columns else pd.Series(dtype=float)
    freq_serie = freq_pivot[c].dropna() if c in freq_pivot.columns else pd.Series(dtype=float)
    rev_serie  = rev_pivot[c].dropna()  if c in rev_pivot.columns  else pd.Series(dtype=float)

    if lr_serie.empty and rev_serie.empty: continue

    # Antigüedad de la cartera
    n_meses_cart = max(len(lr_serie), len(rev_serie))
    es_nueva = n_meses_cart < 12
    es_reciente = 12 <= n_meses_cart < 18
    tag_edad = f" · 🆕 {n_meses_cart} meses" if es_nueva else (
               f" · 📋 {n_meses_cart} meses" if es_reciente else
               f" · {n_meses_cart} meses")

    if lr_serie.empty: continue

    lr_prom = lr_serie.mean()
    lr_ult  = lr_serie.iloc[-1] if len(lr_serie) > 0 else lr_prom
    lr_trend = "📈" if len(lr_serie) >= 3 and lr_serie.iloc[-1] > lr_serie.iloc[-3] else "📉"

    avg_var = ((avg_serie.iloc[-1] - avg_serie.iloc[0]) / avg_serie.iloc[0] * 100) if len(avg_serie) >= 2 else 0
    clts_var = ((clts_serie.iloc[-1] - clts_serie.iloc[0]) / clts_serie.iloc[0] * 100) if len(clts_serie) >= 2 else 0
    freq_ult = freq_serie.iloc[-1] if len(freq_serie) > 0 else 0

    # Clasificar
    if lr_prom > 0.90:
        cat = "🔴 CRÍTICA"; cls_box = "box-danger"
        accion = f"Loss Ratio promedio de {lr_prom:.2f} — por encima de 1.0 en algunos períodos. Requiere análisis urgente de precio y costo de servicio."
    elif lr_prom > lr_target:
        cat = "🟡 REVISAR"; cls_box = "box-warn"
        accion = f"LR promedio de {lr_prom:.3f} supera el objetivo de {lr_target:.0%}. Evaluar repricing o reducción de costos."
    elif lr_prom <= 0.55 and (lr_serie > lr_target).mean() < 0.2:
        cat = "🟢 SANA"; cls_box = "box-ok"
        accion = f"LR promedio de {lr_prom:.3f} — cartera rentable y consistente. Candidata a incrementar participación."
    else:
        cat = "🔵 MONITOREAR"; cls_box = "box-info"
        accion = f"LR promedio de {lr_prom:.3f}. Dentro del objetivo pero vigilar tendencia."

    extras = []
    if avg_var > 15: extras.append(f"costo/servicio +{avg_var:.0f}% en el período")
    if clts_var > 20: extras.append(f"base de clientes +{clts_var:.0f}%")
    if clts_var < -10: extras.append(f"pérdida de clientes {clts_var:.0f}%")
    if freq_ult > freq_alerta: extras.append(f"frecuencia de uso en alerta ({freq_ult*1000:.1f}‰)")
    extras_str = "  |  " + " · ".join(extras) if extras else ""

    advertencia_nueva = ""
    if es_nueva:
        advertencia_nueva = f' &nbsp;<span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;font-size:0.8rem">🆕 cartera nueva · solo {n_meses_cart} meses de historial · estadísticas preliminares</span>'

    st.markdown(
        f'<div class="{cls_box}">'
        f'<b>{c}</b>{tag_edad} &nbsp;·&nbsp; {cat} &nbsp;·&nbsp; '
        f'LR: <b>{lr_prom:.3f}</b> {lr_trend}{extras_str}{advertencia_nueva}<br>'
        f'<small>{accion}</small>'
        f'</div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────────────────
# SECCIÓN 9 — SÍNTESIS EJECUTIVA
# ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">9 · Síntesis Ejecutiva</div>', unsafe_allow_html=True)

# Generar comentarios
criticas  = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].dropna().mean() > 0.90]
revisar   = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].dropna().mean() > lr_target and c not in criticas]
sanas     = [c for c in carteras if c in lr_pivot.columns and lr_pivot[c].dropna().mean() <= 0.55]
costo_alza = [c for c in carteras if c in avg_pivot.columns and len(avg_pivot[c].dropna()) >= 2
              and (avg_pivot[c].dropna().iloc[-1] - avg_pivot[c].dropna().iloc[0]) / avg_pivot[c].dropna().iloc[0] > 0.15]
crec_clts = [c for c in carteras if c in clts_pivot.columns and len(clts_pivot[c].dropna()) >= 2
             and (clts_pivot[c].dropna().iloc[-1] - clts_pivot[c].dropna().iloc[0]) / clts_pivot[c].dropna().iloc[0] > 0.20]

# Clasificar carteras por madurez
carteras_maduras  = [c for c in carteras if c in rev_pivot.columns and rev_pivot[c].notna().sum() >= 18]
carteras_medias   = [c for c in carteras if c in rev_pivot.columns and 6 <= rev_pivot[c].notna().sum() < 18]
carteras_nuevas   = [c for c in carteras if c in rev_pivot.columns and rev_pivot[c].notna().sum() < 6]

lines = [
    f"**Análisis basado en {n_meses} períodos** ({mes_display_map.get(meses_ord[0],'?')} → {mes_display_map.get(meses_ord[-1],'?')}) · {len(carteras)} carteras activas.",
    "",
]
if carteras_nuevas:
    lines.append(f"🆕 **Carteras nuevas** (< 6 meses): {', '.join(carteras_nuevas)}. Sus estadísticas son preliminares — el análisis ganará confianza con más historial.")
if carteras_medias:
    lines.append(f"📋 **Carteras en desarrollo** (6–18 meses): {', '.join(carteras_medias)}. Historial suficiente para tendencias, pero el modelo Markowitz las pondera con menor confianza.")
if carteras_maduras:
    lines.append(f"✅ **Carteras maduras** (≥ 18 meses): {', '.join(carteras_maduras)}. Historial completo — las conclusiones del modelo son estadísticamente confiables.")

if criticas:
    lines.append(f"🔴 **Carteras críticas** (LR > 90%): {', '.join(criticas)}. Estas carteras están operando con márgenes prácticamente nulos o negativos en servicios. El costo de servicio consume casi todo el revenue. Requieren repricing urgente o renegociación de condiciones.")
if revisar:
    lines.append(f"🟡 **Carteras a revisar** (LR > {lr_target:.0%}): {', '.join(revisar)}. Márgenes por debajo del objetivo. Evaluar incremento de precio en próxima renovación de contrato.")
if sanas:
    lines.append(f"🟢 **Carteras sanas** (LR ≤ 55%): {', '.join(sanas)}. Rentabilidad operativa positiva y consistente. El modelo Markowitz sugiere incrementar su participación relativa en el portafolio.")
if costo_alza:
    lines.append(f"📈 **Inflación operativa detectada**: {', '.join(costo_alza)} muestran costo por servicio con tendencia ascendente > 15% en el período analizado. Si el precio contratado no ha cambiado, el margen se está comprimiendo por inflación del costo.")
if crec_clts:
    lines.append(f"👥 **Crecimiento de cartera**: {', '.join(crec_clts)} han crecido > 20% en clientes. Vigilar que el crecimiento en volumen no esté viniendo acompañado de un aumento en frecuencia de uso que presione el costo.")

if en_riesgo.any() if hasattr(en_riesgo, 'any') else en_riesgo:
    top = participacion.idxmax()
    lines.append(f"⚠️ **Concentración de revenue**: {top} representa {participacion[top]:.1f}% del revenue total. Diversificar el portafolio reduce el riesgo ante una renegociación o pérdida de esa cartera.")

lines.append(f"🎯 **Acción prioritaria**: {'repricing de ' + criticas[0] if criticas else ('revisar condiciones de ' + revisar[0] if revisar else 'mantener monitoreo mensual del Loss Ratio y costo promedio por servicio')}.")

st.markdown(
    '<div class="ai-box"><h3>🔶 Síntesis Estratégica — Connect Assistance México</h3>' +
    ''.join([f'<p>{l}</p>' for l in lines if l]) +
    f'<p style="opacity:0.45;font-size:0.75rem;margin-top:14px">Generado automáticamente · {len(carteras)} carteras · {n_meses} períodos · {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>'
    '</div>',
    unsafe_allow_html=True
)

st.markdown("---")
st.caption("Connect Assistance México · Análisis Operativo del Portafolio de Clientes · Universidad Panamericana · IA para el Análisis Financiero")
