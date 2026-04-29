"""
vekmaint_hub.py — v3.0
========================
Hub principal de Vekmaint Solutions con arquitectura de 5 módulos.

Ejecutar: streamlit run vekmaint_hub.py

Arquitectura:
-------------
1. 🔍 Inspección Preoperacional     → genera OT-CI-<SIST>-<VEH>-...
2. 🚨 Reporte de Fallas             → genera OT-CO-* (operación)
3. 📅 Mantenimiento Preventivo      → genera OT-P-<SIST>-<VEH>-...
4. 📋 Cierre de OT                  → cierra todas las OT (CI, CO, P, M)
5. 📊 Dashboard KPI & Analítica     → (próximamente) hoja de vida consolidada
"""
import streamlit as st
import json
import os
from datetime import datetime

st.set_page_config(
    page_title="Vekmaint Solutions",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ════════════════════════════════════════════════════════════
#  ROUTING CON URL QUERY PARAMS (persiste ante F5)
# ════════════════════════════════════════════════════════════
PENDIENTES_DB = "ots_pendientes.json"
FLOTA_DB      = "flota_vehiculos.json"
INSP_XLSX     = "inspecciones_vehiculares.xlsx"
MANT_XLSX     = "mantenimiento_flotas.xlsx"

VALID_MODULES = {"hub", "inspeccion", "reporte_fallas", "preventivo", "cierre_ot"}


def _sync_state_with_url():
    """Reconcilia el módulo activo con la URL para persistencia en F5."""
    qp_mod = st.query_params.get("mod")
    ss_mod = st.session_state.get("modulo")

    if ss_mod in VALID_MODULES:
        if ss_mod == "hub":
            if "mod" in st.query_params:
                st.query_params.clear()
        elif qp_mod != ss_mod:
            st.query_params["mod"] = ss_mod
        return ss_mod

    if qp_mod in VALID_MODULES and qp_mod != "hub":
        st.session_state["modulo"] = qp_mod
        return qp_mod

    st.session_state["modulo"] = "hub"
    if "mod" in st.query_params:
        st.query_params.clear()
    return "hub"


def _navigate(mod: str, clear_module_state: bool = True):
    """Navegar a un módulo actualizando URL y limpiando estado previo."""
    if clear_module_state:
        claves_limpiar = [
            # inspección
            "submitted", "finalizado", "saved_data", "inspeccion", "docs",
            "firma_png", "contador", "despacho", "ot_ci_generada", "insp_errores_modo",
            # reporte_fallas
            "fase_rf", "ot_actual_rf", "f1_data_rf",
            # cierre_ot / mantenimiento
            "fase", "ot_actual", "f1_data", "intervenciones",
            # preventivo
            "prev_tab", "prev_vehiculo_sel", "prev_rutinas_sel",
            "prev_form_data", "prev_confirmacion", "prev_ot_generada",
        ]
        for k in claves_limpiar:
            st.session_state.pop(k, None)

    if mod == "hub":
        st.query_params.clear()
    else:
        st.query_params["mod"] = mod
    st.session_state["modulo"] = mod
    st.rerun()


modulo_actual = _sync_state_with_url()


# ════════════════════════════════════════════════════════════
#  HELPERS DE ESTADÍSTICAS
# ════════════════════════════════════════════════════════════
def count_pendientes() -> int:
    if not os.path.exists(PENDIENTES_DB):
        return 0
    try:
        with open(PENDIENTES_DB, encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


def count_pendientes_por_prefijo(prefijo: str) -> int:
    if not os.path.exists(PENDIENTES_DB):
        return 0
    try:
        with open(PENDIENTES_DB, encoding="utf-8") as f:
            db = json.load(f)
        return sum(1 for k in db if k.startswith(prefijo))
    except Exception:
        return 0


def count_inspecciones_hoy() -> int:
    try:
        import pandas as pd
        if os.path.exists(INSP_XLSX):
            df = pd.read_excel(INSP_XLSX, engine="openpyxl")
            hoy = datetime.now().strftime("%Y-%m-%d")
            return int(df["Fecha_Hora"].astype(str).str.startswith(hoy).sum())
    except Exception:
        pass
    return 0


def count_vehiculos_flota() -> int:
    if not os.path.exists(FLOTA_DB):
        return 0
    try:
        with open(FLOTA_DB, encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


def evaluar_rutinas_flota():
    """
    Evalúa el estado de todas las rutinas de toda la flota.
    Retorna lista de dicts con: vehiculo, km_actual, rutina_id, rutina_nombre,
                                sistema, estado, km_restantes, dias_restantes, pct_consumido.

    Estados (alineado con módulo preventivo):
    • vencida:  ≥ 100% del periodo (km o días)
    • critico:  ≥ 95%
    • proxima:  ≥ 80%
    • vigente:  < 80%
    """
    from datetime import date
    resultados = []
    try:
        if not os.path.exists(FLOTA_DB):
            return resultados
        with open(FLOTA_DB, encoding="utf-8") as f:
            flota = json.load(f)
        if not os.path.exists("catalogo_rutinas.json"):
            return resultados
        with open("catalogo_rutinas.json", encoding="utf-8") as f:
            catalogo = json.load(f)

        hoy = date.today()
        for veh_id, vdata in flota.items():
            km_actual = vdata.get("km_actual", 0)
            ultimas = vdata.get("rutinas_ultimas", {})
            for rut in catalogo:
                ult = ultimas.get(rut["id"], {})
                if not ult:
                    estado, km_rest, dias_rest, pct = "nunca_ejecutada", 0, 0, 0.0
                else:
                    try:
                        fecha_ult = datetime.strptime(ult.get("fecha", ""), "%Y-%m-%d").date()
                    except Exception:
                        continue
                    km_transc   = max(0, km_actual - ult.get("km", 0))
                    dias_transc = (hoy - fecha_ult).days
                    km_rest   = rut["periodicidad_km"] - km_transc
                    dias_rest = rut["periodicidad_dias"] - dias_transc
                    pct_km   = km_transc / rut["periodicidad_km"] if rut["periodicidad_km"] > 0 else 0
                    pct_dias = dias_transc / rut["periodicidad_dias"] if rut["periodicidad_dias"] > 0 else 0
                    pct = max(pct_km, pct_dias)
                    if pct >= 1.0:    estado = "vencida"
                    elif pct >= 0.95: estado = "critico"
                    elif pct >= 0.80: estado = "proxima"
                    else:             estado = "vigente"
                resultados.append({
                    "vehiculo":       veh_id,
                    "km_actual":      km_actual,
                    "rutina_id":      rut["id"],
                    "rutina_nombre":  rut["nombre"],
                    "sistema":        rut["sistema"],
                    "estado":         estado,
                    "km_restantes":   km_rest,
                    "dias_restantes": dias_rest,
                    "pct_consumido":  pct,
                })
    except Exception:
        pass
    return resultados


def count_rutinas_por_estado():
    """Retorna dict {estado: count}"""
    rs = evaluar_rutinas_flota()
    counts = {"vencida": 0, "critico": 0, "proxima": 0, "vigente": 0, "nunca_ejecutada": 0}
    for r in rs:
        counts[r["estado"]] = counts.get(r["estado"], 0) + 1
    return counts


def preventivos_programados_hoy():
    """
    Retorna lista de OT-P planificadas con fecha programada == hoy.
    """
    from datetime import date
    if not os.path.exists(PENDIENTES_DB):
        return []
    try:
        with open(PENDIENTES_DB, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return []

    hoy = date.today()
    programados = []
    for ot, datos in db.items():
        if not ot.startswith("OT-P-"):
            continue
        fecha_str = datos.get("Fecha_Programada", "")
        try:
            fp = fecha_str.split(" ")[0] if " " in fecha_str else fecha_str
            fp_date = datetime.strptime(fp, "%Y-%m-%d").date()
        except Exception:
            continue
        if fp_date == hoy:
            programados.append({
                "ot":       ot,
                "vehiculo": datos.get("Numero_Interno", ""),
                "sistema":  datos.get("Sistema", ""),
                "hora":     fecha_str.split(" ")[1] if " " in fecha_str else "",
            })
    return programados


# ════════════════════════════════════════════════════════════
#  DISPATCH — si hay un módulo activo, ejecutarlo y salir
# ════════════════════════════════════════════════════════════
if modulo_actual == "inspeccion":
    try:
        import inspeccion_vehicular
        inspeccion_vehicular.run()
    except ImportError as e:
        st.error(f"No se encontró `inspeccion_vehicular.py` ({e}). Verifica que esté en la misma carpeta.")
        if st.button("← Volver al Hub"):
            _navigate("hub")
    st.stop()

if modulo_actual == "reporte_fallas":
    try:
        import reporte_fallas
        reporte_fallas.run()
    except ImportError as e:
        st.error(f"No se encontró `reporte_fallas.py` ({e}). Verifica que esté en la misma carpeta.")
        if st.button("← Volver al Hub"):
            _navigate("hub")
    st.stop()

if modulo_actual == "preventivo":
    try:
        import mantenimiento_preventivo
        mantenimiento_preventivo.run()
    except ImportError as e:
        st.error(f"No se encontró `mantenimiento_preventivo.py` ({e}). Verifica que esté en la misma carpeta.")
        if st.button("← Volver al Hub"):
            _navigate("hub")
    st.stop()

if modulo_actual == "cierre_ot":
    try:
        import cierre_ot
        cierre_ot.run()
    except ImportError as e:
        st.error(f"No se encontró `cierre_ot.py` ({e}). Verifica que esté en la misma carpeta.")
        if st.button("← Volver al Hub"):
            _navigate("hub")
    st.stop()


# ════════════════════════════════════════════════════════════
#  HUB — landing principal
# ════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@300;400;600;700;800;900&family=Inter:wght@300;400;500;600&display=swap');
:root{
    --bg:#080C14;--surface:#0E1420;--surface2:#141B28;--border:#1E2A3D;
    --text:#E8EEF8;--muted:#7A8CA8;
    --blue:#2B7EFF;--orange:#FF6B00;--green:#18B754;--purple:#7C4DFF;--red:#F85149;
    --radius:16px;
}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;font-family:'Inter',sans-serif}
.hub-header{display:flex;align-items:center;gap:1.2rem;padding:1.8rem 0 1.2rem 0;margin-bottom:.5rem;border-bottom:1px solid var(--border)}
.hub-logo{width:52px;height:52px;background:linear-gradient(135deg,#FF6B00,#FF9A40);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:26px;flex-shrink:0;box-shadow:0 0 24px rgba(255,107,0,.4)}
.hub-brand h1{font-family:'Exo 2',sans-serif;font-weight:900;font-size:1.8rem;color:var(--text);margin:0;letter-spacing:-.03em}
.hub-brand .tagline{font-size:.78rem;color:var(--muted);font-style:italic}
.hub-date{margin-left:auto;text-align:right;font-size:.78rem;color:var(--muted);line-height:1.5}
.hub-date strong{color:var(--text);font-weight:600}
.stats-bar{display:flex;gap:10px;margin:1rem 0 1.5rem 0;flex-wrap:wrap}
.stat-chip{display:flex;align-items:center;gap:7px;background:var(--surface2);border:1px solid var(--border);border-radius:30px;padding:5px 14px;font-size:.78rem;color:var(--muted)}
.stat-chip .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.stat-chip strong{color:var(--text);font-weight:600;margin:0 1px}
.module-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.4rem 1.2rem 1rem 1.2rem;position:relative;overflow:hidden;transition:all .25s ease;min-height:200px}
.module-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:var(--radius) var(--radius) 0 0}
.module-card.blue::before{background:linear-gradient(90deg,var(--blue),#60A5FF)}
.module-card.red::before{background:linear-gradient(90deg,var(--red),#FF8A80)}
.module-card.purple::before{background:linear-gradient(90deg,var(--purple),#B47AFF)}
.module-card.green::before{background:linear-gradient(90deg,var(--green),#50E090)}
.module-card.gray::before{background:linear-gradient(90deg,#4A6080,#7A8CA8)}
.module-card.gray{opacity:.55}
.card-icon-circle{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;margin-bottom:.8rem;flex-shrink:0}
.card-icon-circle.blue{background:rgba(43,126,255,.15)}
.card-icon-circle.red{background:rgba(248,81,73,.15)}
.card-icon-circle.purple{background:rgba(124,77,255,.15)}
.card-icon-circle.green{background:rgba(24,183,84,.15)}
.card-icon-circle.gray{background:rgba(122,140,168,.15)}
.card-title{font-family:'Exo 2',sans-serif;font-weight:700;font-size:.95rem;color:var(--text);margin-bottom:.3rem;line-height:1.3}
.card-desc{font-size:.76rem;color:var(--muted);line-height:1.45}
.card-badge{display:inline-block;font-size:.66rem;font-weight:700;padding:2px 9px;border-radius:20px;margin-top:.5rem;text-transform:uppercase;letter-spacing:.05em}
.badge-blue{background:rgba(43,126,255,.15);color:var(--blue);border:1px solid rgba(43,126,255,.3)}
.badge-red{background:rgba(248,81,73,.15);color:var(--red);border:1px solid rgba(248,81,73,.3)}
.badge-purple{background:rgba(124,77,255,.15);color:var(--purple);border:1px solid rgba(124,77,255,.3)}
.badge-green{background:rgba(24,183,84,.15);color:var(--green);border:1px solid rgba(24,183,84,.3)}
.badge-orange{background:rgba(255,107,0,.15);color:var(--orange);border:1px solid rgba(255,107,0,.3)}
.badge-gray{background:rgba(122,140,168,.15);color:#A0B0C8;border:1px solid rgba(122,140,168,.3)}
[data-testid="stButton"] button{background:transparent!important;color:var(--muted)!important;border:1px solid var(--border)!important;border-radius:8px!important;font-family:'Inter',sans-serif!important;font-size:.78rem!important;font-weight:600!important;padding:.4rem .9rem!important;transition:all .2s!important;margin-top:.6rem!important}
[data-testid="stButton"] button:hover{color:var(--text)!important;border-color:var(--text)!important;background:var(--surface2)!important;transform:none!important;box-shadow:none!important}
.btn-exit button{color:#F85149!important;border-color:rgba(248,81,73,.3)!important}
.btn-exit button:hover{background:rgba(248,81,73,.1)!important;border-color:#F85149!important;color:#F85149!important}
.hub-divider{border:none;border-top:1px solid var(--border);margin:1.5rem 0}
.hub-footer{text-align:center;font-size:.72rem;color:var(--muted);padding:1rem 0 .5rem;border-top:1px solid var(--border);margin-top:2rem}
.integration-note{background:rgba(255,107,0,.06);border:1px solid rgba(255,107,0,.2);border-radius:10px;padding:.7rem 1rem;font-size:.78rem;color:#FF9A40;margin:.3rem 0 1rem 0}
.alert-banner{border-radius:12px;padding:.9rem 1.2rem;margin:.4rem 0 1rem 0}
.alert-banner.alert-red{background:rgba(248,81,73,.08);border:1px solid rgba(248,81,73,.4);border-left:4px solid #F85149}
.alert-banner.alert-yellow{background:rgba(210,153,34,.07);border:1px solid rgba(210,153,34,.35);border-left:4px solid #D29922}
.alert-banner.alert-purple{background:rgba(124,77,255,.07);border:1px solid rgba(124,77,255,.4);border-left:4px solid #7C4DFF}
.alert-banner-title{font-family:'Exo 2',sans-serif;font-size:.92rem;font-weight:700;margin-bottom:.5rem;letter-spacing:-.01em}
.alert-banner.alert-red .alert-banner-title{color:#F85149}
.alert-banner.alert-yellow .alert-banner-title{color:#D29922}
.alert-banner.alert-purple .alert-banner-title{color:#B47AFF}
.alert-banner-content{display:flex;flex-direction:column;gap:.3rem}
.alert-row-red,.alert-row-yellow{padding:.4rem .7rem;border-radius:6px;font-size:.82rem;background:rgba(0,0,0,.2)}
.alert-row-red{border-left:2px solid #F85149}
.alert-row-yellow{border-left:2px solid #D29922}
.alert-chip-purple{display:inline-block;background:rgba(124,77,255,.18);color:#B47AFF;border:1px solid rgba(124,77,255,.4);border-radius:18px;padding:3px 12px;font-size:.78rem;font-weight:600;margin-right:.4rem;margin-bottom:.3rem}
#MainMenu,footer,header{visibility:hidden}.block-container{padding-top:0!important;max-width:1200px!important}
@media(max-width:768px){.hub-brand h1{font-size:1.3rem}.hub-date{display:none}}
</style>
""", unsafe_allow_html=True)

# ── Cálculo de estadísticas ─────────────────────
n_pend     = count_pendientes()
n_pend_ci  = count_pendientes_por_prefijo("OT-CI-")
n_pend_co  = count_pendientes_por_prefijo("OT-CO-")
n_pend_p   = count_pendientes_por_prefijo("OT-P-")
n_pend_m   = count_pendientes_por_prefijo("OT-M-")
n_hoy      = count_inspecciones_hoy()
n_flota    = count_vehiculos_flota()
rutinas_evaluadas = evaluar_rutinas_flota()
counts_rutinas = {"vencida": 0, "critico": 0, "proxima": 0, "vigente": 0, "nunca_ejecutada": 0}
for r in rutinas_evaluadas:
    counts_rutinas[r["estado"]] = counts_rutinas.get(r["estado"], 0) + 1
n_vencidas = counts_rutinas["vencida"]
n_criticas = counts_rutinas["critico"]
n_proximas = counts_rutinas["proxima"]
preventivos_hoy = preventivos_programados_hoy()
hora_str   = datetime.now().strftime("%H:%M")
fecha_str  = datetime.now().strftime("%A, %d de %B de %Y")

st.markdown(f"""
<div class="hub-header">
  <div class="hub-logo">🔧</div>
  <div class="hub-brand">
    <h1>Vekmaint Solutions</h1>
    <span class="tagline">Vehicle Knowledge for Maintenance Solutions</span>
  </div>
  <div class="hub-date"><strong>{hora_str}</strong><br>{fecha_str}</div>
</div>
""", unsafe_allow_html=True)

# ── Stats bar ───────────────────────────────────
dot_pend = "var(--orange)" if n_pend > 0 else "var(--green)"
dot_venc = "var(--red)" if n_vencidas > 0 else ("var(--orange)" if n_criticas > 0 else "var(--green)")
st.markdown(f"""
<div class="stats-bar">
  <div class="stat-chip"><span class="dot" style="background:{dot_pend}"></span>
    <strong>{n_pend}</strong> OT{'s' if n_pend!=1 else ''} pendiente{'s' if n_pend!=1 else ''}</div>
  <div class="stat-chip"><span class="dot" style="background:var(--blue)"></span>
    <strong>{n_hoy}</strong> inspección{'es' if n_hoy!=1 else ''} hoy</div>
  <div class="stat-chip"><span class="dot" style="background:var(--purple)"></span>
    <strong>{n_flota}</strong> vehículo{'s' if n_flota!=1 else ''} en flota</div>
  <div class="stat-chip"><span class="dot" style="background:{dot_venc}"></span>
    <strong>{n_vencidas}</strong> vencida{'s' if n_vencidas!=1 else ''} ·
    <strong>{n_criticas}</strong> crítica{'s' if n_criticas!=1 else ''} ·
    <strong>{n_proximas}</strong> próxima{'s' if n_proximas!=1 else ''}</div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════
#  BANNER 1 — Preventivos programados HOY
# ════════════════════════════════════════════════════
if preventivos_hoy:
    items_hoy_html = ""
    for p in preventivos_hoy[:5]:
        items_hoy_html += f"""<span class="alert-chip-purple">
          🚛 {p['vehiculo']} · {p['sistema']}{(' · ' + p['hora']) if p['hora'] else ''}
        </span>"""
    extra = f" · +{len(preventivos_hoy) - 5} más" if len(preventivos_hoy) > 5 else ""
    st.markdown(f"""<div class="alert-banner alert-purple">
      <div class="alert-banner-title">📅 Preventivos programados para HOY ({len(preventivos_hoy)})</div>
      <div class="alert-banner-content">
        {items_hoy_html}
        <span style="font-size:.75rem;color:var(--muted);margin-left:.4rem">{extra}</span>
      </div>
      <div style="font-size:.75rem;color:var(--muted);margin-top:.4rem">
        Estos vehículos requieren atención del taller hoy. Acceda a <strong style="color:var(--text)">Cierre de OT</strong> para completar la intervención.
      </div>
    </div>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════
#  BANNER 2 — Rutinas VENCIDAS (crítico operativo)
# ════════════════════════════════════════════════════
rutinas_vencidas = sorted(
    [r for r in rutinas_evaluadas if r["estado"] == "vencida"],
    key=lambda x: -x["pct_consumido"]
)
if rutinas_vencidas:
    items_html = ""
    for r in rutinas_vencidas[:5]:
        km_exc = abs(r["km_restantes"]) if r["km_restantes"] < 0 else 0
        info_extra = f" · {km_exc:,} km excedidos".replace(",", ".") if km_exc > 0 else ""
        items_html += f"""<div class="alert-row-red">
          <div><strong style="color:var(--text)">Vehículo {r['vehiculo']}</strong> · {r['rutina_nombre']}{info_extra}</div>
          <div style="font-size:.75rem;color:var(--muted)">{r['rutina_id']} · Sistema: {r['sistema']}</div>
        </div>"""
    extra = f"<div style='font-size:.78rem;color:var(--muted);margin-top:.3rem'>+ {len(rutinas_vencidas) - 5} rutinas vencidas adicionales</div>" if len(rutinas_vencidas) > 5 else ""
    st.markdown(f"""<div class="alert-banner alert-red">
      <div class="alert-banner-title">🔴 {len(rutinas_vencidas)} rutina{'s' if len(rutinas_vencidas)!=1 else ''} vencida{'s' if len(rutinas_vencidas)!=1 else ''} — Acción inmediata requerida</div>
      <div class="alert-banner-content">
        {items_html}
        {extra}
      </div>
    </div>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════
#  BANNER 3 — Rutinas PRÓXIMAS A VENCER (críticas + próximas)
# ════════════════════════════════════════════════════
rutinas_advert = sorted(
    [r for r in rutinas_evaluadas if r["estado"] in ("critico", "proxima")],
    key=lambda x: -x["pct_consumido"]
)
if rutinas_advert:
    items_html = ""
    for r in rutinas_advert[:5]:
        chip = "🟠" if r["estado"] == "critico" else "🟡"
        pct = r["pct_consumido"] * 100
        items_html += f"""<div class="alert-row-yellow">
          <div>{chip} <strong style="color:var(--text)">Vehículo {r['vehiculo']}</strong> · {r['rutina_nombre']}</div>
          <div style="font-size:.75rem;color:var(--muted)">{r['rutina_id']} · {pct:.0f}% consumido · {r['km_restantes']:,} km restantes</div>
        </div>""".replace(",", ".")
    extra = f"<div style='font-size:.78rem;color:var(--muted);margin-top:.3rem'>+ {len(rutinas_advert) - 5} rutinas adicionales próximas a vencer</div>" if len(rutinas_advert) > 5 else ""
    st.markdown(f"""<div class="alert-banner alert-yellow">
      <div class="alert-banner-title">🟠 {n_criticas} crítica{'s' if n_criticas!=1 else ''} · 🟡 {n_proximas} próxima{'s' if n_proximas!=1 else ''} a vencer</div>
      <div class="alert-banner-content">
        {items_html}
        {extra}
      </div>
      <div style="font-size:.75rem;color:var(--muted);margin-top:.4rem">
        Planifique antes de que venzan en el módulo <strong style="color:var(--text)">Mantenimiento Preventivo</strong>.
      </div>
    </div>""", unsafe_allow_html=True)

# Notificación de OTs pendientes
if n_pend > 0:
    desglose = []
    if n_pend_ci: desglose.append(f"{n_pend_ci} de inspección")
    if n_pend_co: desglose.append(f"{n_pend_co} de operación")
    if n_pend_p:  desglose.append(f"{n_pend_p} preventiva{'s' if n_pend_p > 1 else ''}")
    if n_pend_m:  desglose.append(f"{n_pend_m} mayor{'es' if n_pend_m > 1 else ''}")
    st.markdown(f"""<div class="integration-note">
      🔗 <strong>{n_pend} OT{' pendiente' if n_pend==1 else 's pendientes'} de cierre</strong>
      ({' · '.join(desglose)}) — Acceda al módulo <strong>Cierre de OT</strong> para completarlas.
    </div>""", unsafe_allow_html=True)

# ── TARJETAS DE MÓDULOS (5 en layout 3+2) ──────────
# Fila 1: tres módulos de captura
col1, col2, col3 = st.columns(3, gap="medium")

with col1:
    badge_insp = f'<span class="card-badge badge-blue">{n_hoy} hoy</span>' if n_hoy > 0 else ""
    st.markdown(f"""
    <div class="module-card blue">
      <div class="card-icon-circle blue">🔍</div>
      <div class="card-title">Inspección Preoperacional</div>
      <div class="card-desc">Control técnico diario antes de salir a operación.
        Genera OT-CI por cada sistema con novedad si el despacho no se autoriza.</div>
      {badge_insp}
    </div>""", unsafe_allow_html=True)
    if st.button("→ Abrir Inspección", key="btn_insp", use_container_width=True):
        _navigate("inspeccion")

with col2:
    badge_rf = (f'<span class="card-badge badge-red">{n_pend_co} pendiente{"s" if n_pend_co != 1 else ""}</span>'
                if n_pend_co > 0 else '<span class="card-badge badge-red">Correctivo</span>')
    st.markdown(f"""
    <div class="module-card red">
      <div class="card-icon-circle red">🚨</div>
      <div class="card-title">Reporte de Fallas</div>
      <div class="card-desc">Reportar fallas detectadas en operación. Incluye criticidad
        (Alta/Media/Baja) y generación automática de OT correctiva (OT-CO).</div>
      {badge_rf}
    </div>""", unsafe_allow_html=True)
    if st.button("→ Reportar Falla", key="btn_rf", use_container_width=True):
        _navigate("reporte_fallas")

with col3:
    if n_vencidas > 0:
        badge_prev = f'<span class="card-badge badge-red">{n_vencidas} vencida{"s" if n_vencidas != 1 else ""}</span>'
    elif n_criticas > 0:
        badge_prev = f'<span class="card-badge badge-orange">{n_criticas} crítica{"s" if n_criticas != 1 else ""}</span>'
    elif n_pend_p > 0:
        badge_prev = f'<span class="card-badge badge-purple">{n_pend_p} programada{"s" if n_pend_p != 1 else ""}</span>'
    else:
        badge_prev = '<span class="card-badge badge-purple">Planificación</span>'
    st.markdown(f"""
    <div class="module-card purple">
      <div class="card-icon-circle purple">📅</div>
      <div class="card-title">Mantenimiento Preventivo</div>
      <div class="card-desc">Catálogo de rutinas, alertas por vencimiento de km o fecha,
        calendario mensual y generación de OT-P con costos y recursos.</div>
      {badge_prev}
    </div>""", unsafe_allow_html=True)
    if st.button("→ Planificar Preventivo", key="btn_prev", use_container_width=True):
        _navigate("preventivo")

# Fila 2: módulos de salida / reporte
col4, col5 = st.columns(2, gap="medium")

with col4:
    pend_label = (f'<span class="card-badge badge-orange">{n_pend} pendiente{"s" if n_pend!=1 else ""}</span>'
                  if n_pend > 0 else '<span class="card-badge badge-green">Al día</span>')
    st.markdown(f"""
    <div class="module-card green">
      <div class="card-icon-circle green">📋</div>
      <div class="card-title">Cierre de Orden de Trabajo</div>
      <div class="card-desc">El mecánico completa la intervención técnica: causa raíz (correctivos),
        repuestos, costos reales y soporte. Soporta OT-CI, OT-CO, OT-P y OT-M.</div>
      {pend_label}
    </div>""", unsafe_allow_html=True)
    if st.button("→ Cerrar OT", key="btn_ot", use_container_width=True):
        _navigate("cierre_ot")

with col5:
    st.markdown("""
    <div class="module-card gray">
      <div class="card-icon-circle gray">📊</div>
      <div class="card-title">Dashboard KPI &amp; Analítica</div>
      <div class="card-desc">Hoja de vida consolidada del vehículo, Pareto de fallas,
        MTBF, cumplimiento del plan preventivo, razón correctivo/preventivo, costos por km.</div>
      <span class="card-badge badge-gray">Próximamente — integración Power BI</span>
    </div>""", unsafe_allow_html=True)
    st.button("→ Próximamente", key="btn_dash", use_container_width=True, disabled=True)

# ── Footer ────────────────────────────────────
st.markdown("<div class='hub-divider'></div>", unsafe_allow_html=True)
col_info, col_exit = st.columns([4, 1])
with col_info:
    st.markdown("""<p style='font-size:.72rem;color:#4A6080;margin:0'>
      <strong style='color:#7A8CA8'>Archivos de datos:</strong>
      <code>inspecciones_vehiculares.xlsx</code> ·
      <code>mantenimiento_flotas.xlsx</code> ·
      <code>ots_pendientes.json</code> ·
      <code>flota_vehiculos.json</code> ·
      <code>catalogo_rutinas.json</code>
    </p>""", unsafe_allow_html=True)
with col_exit:
    st.markdown('<div class="btn-exit">', unsafe_allow_html=True)
    if st.button("🚪 Salir", key="btn_exit", use_container_width=True):
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("""
<div class="hub-footer">
  Vekmaint Solutions v3.0 &nbsp;·&nbsp;
  Vehicle Knowledge for Maintenance Solutions &nbsp;·&nbsp;
  ISO 55000 · UITP · Resolución 40595 / 00315
</div>
""", unsafe_allow_html=True)