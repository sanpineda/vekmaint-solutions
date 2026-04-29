"""
mantenimiento_preventivo.py — v1.0
====================================
Módulo de planificación y ejecución de mantenimiento preventivo.
Standalone : streamlit run mantenimiento_preventivo.py
Desde hub  : import mantenimiento_preventivo; mantenimiento_preventivo.run()

Alcance:
--------
• Catálogo parametrizado de rutinas preventivas por sistema
• Gestión de vehículos de la flota con su kilometraje actual
• Alertas automáticas por vencimiento de kilómetros o tiempo
• Cronograma calendario mensual de programación
• Planificación y generación de OT-P con pre-carga de:
    - Rutinas seleccionadas
    - Repuestos estándar + costo estimado
    - Responsable y ventana de ejecución
"""
import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta, date
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTES
# ═══════════════════════════════════════════════════════════════════
PENDIENTES_DB      = "ots_pendientes.json"
FLOTA_DB           = "flota_vehiculos.json"
CATALOGO_RUTINAS_DB = "catalogo_rutinas.json"

SIST_ABREV = {
    "Motor":              "MOT",
    "Frenos":             "FRE",
    "Direccion":          "DIR",
    "Suspension":         "SUS",
    "Llantas":            "LLA",
    "Refrigeracion":      "REF",
    "Electrico":          "ELE",
    "Carroceria Externa": "CAR",
    "Habitaculo":         "HAB",
    "Transmision":        "TRA",
    "General":            "GEN",
}

SISTEMAS = list(SIST_ABREV.keys())

# Catálogo por defecto (se precarga si no existe el archivo)
CATALOGO_DEFAULT = [
    # Rutinas cortas / frecuentes
    {
        "id": "RUT-001",
        "nombre": "Cambio de aceite motor y filtro",
        "sistema": "Motor",
        "periodicidad_km": 15000,
        "periodicidad_dias": 180,
        "duracion_horas": 1.5,
        "repuestos": [
            {"desc": "Aceite motor 15W-40", "cantidad": 8, "costo_unit": 35000},
            {"desc": "Filtro de aceite",    "cantidad": 1, "costo_unit": 45000},
        ],
        "mano_obra": 80000,
    },
    {
        "id": "RUT-002",
        "nombre": "Cambio filtros de aire y combustible",
        "sistema": "Motor",
        "periodicidad_km": 30000,
        "periodicidad_dias": 365,
        "duracion_horas": 1.0,
        "repuestos": [
            {"desc": "Filtro de aire",        "cantidad": 1, "costo_unit": 65000},
            {"desc": "Filtro de combustible", "cantidad": 1, "costo_unit": 55000},
        ],
        "mano_obra": 60000,
    },
    {
        "id": "RUT-003",
        "nombre": "Inspección y ajuste de frenos",
        "sistema": "Frenos",
        "periodicidad_km": 20000,
        "periodicidad_dias": 180,
        "duracion_horas": 2.0,
        "repuestos": [
            {"desc": "Pastillas de freno delanteras", "cantidad": 1, "costo_unit": 180000},
        ],
        "mano_obra": 120000,
    },
    {
        "id": "RUT-004",
        "nombre": "Cambio líquido de frenos",
        "sistema": "Frenos",
        "periodicidad_km": 40000,
        "periodicidad_dias": 365,
        "duracion_horas": 1.5,
        "repuestos": [
            {"desc": "Líquido de frenos DOT 4", "cantidad": 2, "costo_unit": 28000},
        ],
        "mano_obra": 80000,
    },
    {
        "id": "RUT-005",
        "nombre": "Rotación y balanceo de llantas",
        "sistema": "Llantas",
        "periodicidad_km": 10000,
        "periodicidad_dias": 90,
        "duracion_horas": 1.0,
        "repuestos": [],
        "mano_obra": 60000,
    },
    {
        "id": "RUT-006",
        "nombre": "Cambio refrigerante motor",
        "sistema": "Refrigeracion",
        "periodicidad_km": 50000,
        "periodicidad_dias": 730,
        "duracion_horas": 1.5,
        "repuestos": [
            {"desc": "Refrigerante concentrado", "cantidad": 4, "costo_unit": 25000},
        ],
        "mano_obra": 80000,
    },
    {
        "id": "RUT-007",
        "nombre": "Inspección sistema eléctrico y batería",
        "sistema": "Electrico",
        "periodicidad_km": 20000,
        "periodicidad_dias": 180,
        "duracion_horas": 1.0,
        "repuestos": [],
        "mano_obra": 50000,
    },
    {
        "id": "RUT-008",
        "nombre": "Alineación y balanceo",
        "sistema": "Suspension",
        "periodicidad_km": 20000,
        "periodicidad_dias": 180,
        "duracion_horas": 1.5,
        "repuestos": [],
        "mano_obra": 90000,
    },
    {
        "id": "RUT-009",
        "nombre": "Cambio aceite caja y diferencial",
        "sistema": "Transmision",
        "periodicidad_km": 60000,
        "periodicidad_dias": 730,
        "duracion_horas": 2.0,
        "repuestos": [
            {"desc": "Aceite de caja 75W-90", "cantidad": 4, "costo_unit": 42000},
        ],
        "mano_obra": 110000,
    },
    {
        "id": "RUT-010",
        "nombre": "Engrase general del chasis",
        "sistema": "General",
        "periodicidad_km": 10000,
        "periodicidad_dias": 90,
        "duracion_horas": 0.5,
        "repuestos": [
            {"desc": "Grasa multipropósito", "cantidad": 1, "costo_unit": 18000},
        ],
        "mano_obra": 30000,
    },
]


# ═══════════════════════════════════════════════════════════════════
#  PERSISTENCIA
# ═══════════════════════════════════════════════════════════════════
def _cargar_catalogo():
    if os.path.exists(CATALOGO_RUTINAS_DB):
        try:
            with open(CATALOGO_RUTINAS_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Precarga default
    _guardar_catalogo(CATALOGO_DEFAULT)
    return CATALOGO_DEFAULT


def _guardar_catalogo(data):
    with open(CATALOGO_RUTINAS_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _cargar_flota():
    """
    Estructura por vehículo:
    {
      "0042": {
        "km_actual": 125000,
        "km_actualizado_en": "2026-04-23",
        "rutinas_ultimas": {
            "RUT-001": {"km": 120000, "fecha": "2026-01-15"},
            ...
        }
      }
    }
    """
    if os.path.exists(FLOTA_DB):
        try:
            with open(FLOTA_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _guardar_flota(data):
    with open(FLOTA_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _cargar_pendientes():
    if not os.path.exists(PENDIENTES_DB):
        return {}
    try:
        with open(PENDIENTES_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_pendientes(data):
    with open(PENDIENTES_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _registrar_ot_pendiente(ot, datos):
    db = _cargar_pendientes()
    db[ot] = datos
    _guardar_pendientes(db)


# ═══════════════════════════════════════════════════════════════════
#  LÓGICA DE NEGOCIO
# ═══════════════════════════════════════════════════════════════════
def _generar_ot_p(vehiculo, sistema_principal):
    """Genera radicado OT-P con sistema abreviado."""
    now = datetime.now()
    veh = vehiculo.strip().upper().replace(" ", "")[:6]
    sist = SIST_ABREV.get(sistema_principal, "GEN")
    return f"OT-P-{sist}-{veh}-{now.strftime('%y%m%d')}-{now.strftime('%H%M')}"


def _calcular_estado_rutina(km_actual, ultima_km, ultima_fecha_str, periodicidad_km, periodicidad_dias):
    """
    Evalúa si una rutina está vencida, crítica, próxima o vigente.
    Retorna: ('vigente'|'proxima'|'critico'|'vencida'|'nunca_ejecutada', km_restantes, dias_restantes, pct_consumido)

    Umbrales (basados en flota urbana ~3000 km/mes):
    • vencida:          ≥ 100% del periodo (km o días)
    • critico:          ≥ 95%   (~7-10 días de margen)
    • proxima:          ≥ 80%   (~1 mes de margen logístico)
    • vigente:          < 80%
    • nunca_ejecutada:  sin registro previo
    """
    if ultima_km is None or ultima_fecha_str is None:
        return ("nunca_ejecutada", 0, 0, 0.0)

    try:
        ultima_fecha = datetime.strptime(ultima_fecha_str, "%Y-%m-%d").date()
    except Exception:
        return ("nunca_ejecutada", 0, 0, 0.0)

    hoy = date.today()
    km_transc   = max(0, km_actual - ultima_km)
    dias_transc = (hoy - ultima_fecha).days
    km_restantes   = periodicidad_km - km_transc
    dias_restantes = periodicidad_dias - dias_transc

    # Porcentaje consumido: el mayor de los dos (km o tiempo)
    pct_km   = km_transc / periodicidad_km if periodicidad_km > 0 else 0
    pct_dias = dias_transc / periodicidad_dias if periodicidad_dias > 0 else 0
    pct = max(pct_km, pct_dias)

    if pct >= 1.0:
        return ("vencida", km_restantes, dias_restantes, pct)
    if pct >= 0.95:
        return ("critico", km_restantes, dias_restantes, pct)
    if pct >= 0.80:
        return ("proxima", km_restantes, dias_restantes, pct)
    return ("vigente", km_restantes, dias_restantes, pct)


def _evaluar_flota_completa(flota, catalogo):
    """
    Para cada vehículo de la flota, evalúa el estado de todas las rutinas.
    Retorna lista de dicts con: vehiculo, km_actual, rutina_id, rutina_nombre, sistema,
                                estado, km_restantes, dias_restantes, pct_consumido
    """
    resultados = []
    for veh_id, veh_data in flota.items():
        km_actual = veh_data.get("km_actual", 0)
        ultimas = veh_data.get("rutinas_ultimas", {})
        for rut in catalogo:
            rid = rut["id"]
            ult = ultimas.get(rid, {})
            estado, km_rest, dias_rest, pct = _calcular_estado_rutina(
                km_actual, ult.get("km"), ult.get("fecha"),
                rut["periodicidad_km"], rut["periodicidad_dias"]
            )
            resultados.append({
                "vehiculo":        veh_id,
                "km_actual":       km_actual,
                "rutina_id":       rid,
                "rutina_nombre":   rut["nombre"],
                "sistema":         rut["sistema"],
                "periodicidad_km": rut["periodicidad_km"],
                "estado":          estado,
                "km_restantes":    km_rest,
                "dias_restantes":  dias_rest,
                "pct_consumido":   pct,
                "ultima_km":       ult.get("km"),
                "ultima_fecha":    ult.get("fecha"),
            })
    return resultados


def _fmt_moneda(v):
    return f"$ {v:,.0f}".replace(",", ".") if v else "$ 0"


def _volver_al_hub():
    for k in ["prev_tab", "prev_vehiculo_sel", "prev_rutinas_sel",
              "prev_form_data", "prev_confirmacion", "prev_ot_generada"]:
        st.session_state.pop(k, None)
    st.session_state["modulo"] = "hub"
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.rerun()


# ═══════════════════════════════════════════════════════════════════
#  CSS
# ═══════════════════════════════════════════════════════════════════
CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@700;800&family=Inter:wght@300;400;500;600&display=swap');
:root{--primary:#7C4DFF;--primary-dk:#5E32D0;--bg:#0D1117;--surface:#161B22;--surface2:#21262D;
      --border:#30363D;--text:#E6EDF3;--muted:#8B949E;--green:#3FB950;--yellow:#D29922;
      --red:#F85149;--blue:#0A84FF;--orange:#FF6B00;--radius:12px;}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;font-family:'Inter',sans-serif}
.app-header{background:linear-gradient(135deg,#0D1117,#1A0D2E,#0D1117);border-bottom:1px solid #2D1F4A;padding:1.3rem 2rem;margin:0 -1rem 2rem -1rem;display:flex;align-items:center;gap:1rem}
.app-header h1{font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.5rem;color:var(--text);margin:0}
.app-header .sub{font-size:.78rem;color:var(--muted);margin:0}
.badge-pill{background:var(--primary);color:white;padding:.2rem .8rem;border-radius:20px;font-size:.7rem;font-weight:600;text-transform:uppercase}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.3rem;margin-bottom:1rem}
.card-title{font-family:'Exo 2',sans-serif;font-size:.92rem;font-weight:700;color:var(--primary);margin-bottom:.8rem;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--border);padding-bottom:.5rem}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:1rem}
.kpi-grid.kpi-grid-5{grid-template-columns:repeat(5,1fr)}
.kpi-box{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:.8rem 1rem;border-left:3px solid var(--primary)}
.kpi-box.kpi-red{border-left-color:var(--red)}
.kpi-box.kpi-orange{border-left-color:var(--orange)}
.kpi-box.kpi-yellow{border-left-color:var(--yellow)}
.kpi-box.kpi-green{border-left-color:var(--green)}
.kpi-box.kpi-blue{border-left-color:var(--blue)}
.kpi-label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.kpi-value{font-family:'Exo 2',sans-serif;font-size:1.6rem;font-weight:800;color:var(--text);margin-top:.2rem}
.kpi-sub{font-size:.72rem;color:var(--muted);margin-top:.1rem}
.alerta-row{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.7rem 1rem;margin-bottom:.4rem;display:grid;grid-template-columns:1fr 2fr 1fr 1fr 1fr;gap:.8rem;align-items:center;font-size:.85rem}
.alerta-row.vencida{border-left:4px solid var(--red);background:rgba(248,81,73,.05)}
.alerta-row.critico{border-left:4px solid var(--orange);background:rgba(255,107,0,.05)}
.alerta-row.proxima{border-left:4px solid var(--yellow);background:rgba(210,153,34,.05)}
.alerta-row.nunca{border-left:4px solid var(--blue);background:rgba(10,132,255,.05)}
.chip-vencida{background:rgba(248,81,73,.15);color:var(--red);border:1px solid var(--red);padding:2px 10px;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.chip-critico{background:rgba(255,107,0,.15);color:var(--orange);border:1px solid var(--orange);padding:2px 10px;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.chip-proxima{background:rgba(210,153,34,.15);color:var(--yellow);border:1px solid var(--yellow);padding:2px 10px;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.chip-vigente{background:rgba(63,185,80,.12);color:var(--green);border:1px solid var(--green);padding:2px 10px;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.chip-nunca{background:rgba(10,132,255,.12);color:var(--blue);border:1px solid var(--blue);padding:2px 10px;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.catalog-card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:.8rem 1rem;margin-bottom:.5rem;display:grid;grid-template-columns:auto 1fr auto auto;gap:.8rem;align-items:center}
.catalog-id{font-family:'Exo 2',sans-serif;color:var(--primary);font-weight:700;font-size:.85rem;letter-spacing:.05em}
.catalog-name{font-size:.9rem;font-weight:600;color:var(--text)}
.catalog-meta{font-size:.72rem;color:var(--muted);margin-top:.15rem}
.catalog-period{text-align:right;font-size:.78rem;color:var(--muted)}
.catalog-period strong{color:var(--text);font-weight:600}
.ot-generated-big{background:linear-gradient(135deg,#1A0D2E,#0D1117);border:2px solid var(--primary);border-radius:14px;padding:1.4rem 1.8rem;margin:1.2rem 0;box-shadow:0 0 24px rgba(124,77,255,.25);text-align:center}
.ot-generated-label{font-size:.78rem;color:#8B949E;text-transform:uppercase;letter-spacing:.12em;font-weight:600}
.ot-generated-number{font-family:'Exo 2',sans-serif;font-size:1.8rem;font-weight:800;color:var(--primary);margin:.4rem 0;letter-spacing:.02em}
.costo-display{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.8rem 1.2rem;text-align:center}
.costo-label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.3rem}
.costo-valor{font-family:'Exo 2',sans-serif;font-size:1.55rem;font-weight:800;color:var(--primary);letter-spacing:.01em}
.empty-state{text-align:center;padding:2.5rem 1rem;color:var(--muted)}
.empty-state h3{color:var(--text);font-family:'Exo 2',sans-serif;margin:.5rem 0}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input{background:var(--surface2)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:8px!important;font-family:'Inter',sans-serif!important}
[data-testid="stSelectbox"]>div>div{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:8px!important}
[data-testid="stButton"] button{background:var(--primary)!important;color:white!important;border:none!important;border-radius:8px!important;font-family:'Exo 2',sans-serif!important;font-weight:700!important;font-size:.88rem!important;padding:.55rem 1.2rem!important;text-transform:uppercase!important;letter-spacing:.05em!important}
[data-testid="stButton"] button:hover{background:var(--primary-dk)!important;transform:translateY(-1px);box-shadow:0 4px 16px rgba(124,77,255,.3)!important}
[data-testid="stButton"] button:disabled{background:var(--surface2)!important;color:var(--muted)!important;transform:none!important;box-shadow:none!important}
.btn-green button{background:#2EA043!important}.btn-green button:hover{background:#3FB950!important}
.btn-blue button{background:#005FCC!important}.btn-blue button:hover{background:#0A84FF!important}
.btn-gray button{background:var(--surface2)!important;color:var(--muted)!important;border:1px solid var(--border)!important}
.btn-back button{background:var(--surface2)!important;color:var(--muted)!important;border:1px solid var(--border)!important;text-transform:none!important;font-size:.82rem!important;font-weight:500!important;padding:.4rem 1rem!important;letter-spacing:normal!important}
.btn-back button:hover{background:var(--border)!important;color:var(--text)!important;transform:none!important;box-shadow:none!important}
[data-baseweb="tab-list"]{background:var(--surface)!important;border-radius:8px!important;padding:.3rem!important;gap:.3rem!important}
[data-baseweb="tab"]{background:transparent!important;color:var(--muted)!important;border-radius:6px!important;font-family:'Inter',sans-serif!important;font-weight:600!important;font-size:.85rem!important;padding:.5rem 1.2rem!important}
[data-baseweb="tab"][aria-selected="true"]{background:var(--primary)!important;color:white!important}
/* ── Calendario mensual ── */
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:4px}
.cal-header{margin-bottom:8px}
.cal-day-name{text-align:center;font-family:'Exo 2',sans-serif;font-weight:700;font-size:.75rem;color:var(--muted);padding:.4rem;letter-spacing:.1em;text-transform:uppercase}
.cal-week{margin-bottom:4px}
.cal-cell{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.5rem .4rem;min-height:90px;display:flex;flex-direction:column;gap:3px;transition:all .15s}
.cal-cell.cal-empty{background:transparent;border:1px dashed var(--border);opacity:.3}
.cal-cell.cal-today{border:2px solid var(--purple);background:rgba(124,77,255,.08);box-shadow:0 0 12px rgba(124,77,255,.2)}
.cal-cell.cal-past{opacity:.55}
.cal-cell.cal-has-events{border-color:var(--purple)}
.cal-day-num{font-family:'Exo 2',sans-serif;font-weight:700;font-size:.85rem;color:var(--text);margin-bottom:2px}
.cal-cell.cal-today .cal-day-num{color:var(--purple);font-size:.95rem}
.cal-event{background:rgba(124,77,255,.18);color:var(--text);border-left:2px solid var(--purple);border-radius:4px;padding:2px 5px;font-size:.68rem;font-weight:600;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cal-event-overdue{background:rgba(248,81,73,.18);color:var(--text);border-left:2px solid var(--red);border-radius:4px;padding:2px 5px;font-size:.68rem;font-weight:600;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cal-event-more{font-size:.65rem;color:var(--muted);font-style:italic;text-align:center;padding-top:1px}
#MainMenu,footer,header{visibility:hidden}.block-container{padding-top:0!important}
</style>"""


# ═══════════════════════════════════════════════════════════════════
#  ESTADO
# ═══════════════════════════════════════════════════════════════════
def _init_state():
    defaults = {
        "prev_tab":          0,
        "prev_vehiculo_sel": None,
        "prev_rutinas_sel":  [],
        "prev_form_data":    None,
        "prev_confirmacion": False,
        "prev_ot_generada":  None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _render_back_button(key_suffix):
    if st.session_state.get("modulo") == "preventivo":
        st.markdown('<div class="btn-back">', unsafe_allow_html=True)
        if st.button("← Volver al Hub", key=f"btn_back_prev_{key_suffix}"):
            _volver_al_hub()
        st.markdown('</div>', unsafe_allow_html=True)


def _header():
    st.markdown("""
    <div class="app-header">
      <div style="font-size:2rem">📅</div>
      <div>
        <h1>Mantenimiento Preventivo</h1>
        <p class="sub">Planificación · Rutinas · Calendario · Generación de OT-P</p>
      </div>
      <div style="margin-left:auto"><span class="badge-pill">Planificación</span></div>
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 1 — DASHBOARD DE ALERTAS
# ═══════════════════════════════════════════════════════════════════
def _tab_dashboard(flota, catalogo):
    if not flota:
        st.markdown("""<div class="empty-state">
          <div style="font-size:3rem">🚛</div>
          <h3>No hay vehículos registrados en la flota</h3>
          <p>Vaya a la pestaña <strong>Flota</strong> para dar de alta vehículos y actualizar su kilometraje.</p>
        </div>""", unsafe_allow_html=True)
        return

    evaluaciones = _evaluar_flota_completa(flota, catalogo)
    vencidas  = [e for e in evaluaciones if e["estado"] == "vencida"]
    criticas  = [e for e in evaluaciones if e["estado"] == "critico"]
    proximas  = [e for e in evaluaciones if e["estado"] == "proxima"]
    nunca     = [e for e in evaluaciones if e["estado"] == "nunca_ejecutada"]
    vigentes  = [e for e in evaluaciones if e["estado"] == "vigente"]

    # KPIs (5 niveles)
    st.markdown(f"""<div class="kpi-grid kpi-grid-5">
      <div class="kpi-box kpi-red">
        <div class="kpi-label">🔴 Vencidas</div>
        <div class="kpi-value">{len(vencidas)}</div>
        <div class="kpi-sub">≥ 100% del periodo</div>
      </div>
      <div class="kpi-box kpi-orange">
        <div class="kpi-label">🟠 Críticas</div>
        <div class="kpi-value">{len(criticas)}</div>
        <div class="kpi-sub">95% – 100% (~7 días)</div>
      </div>
      <div class="kpi-box kpi-yellow">
        <div class="kpi-label">🟡 Próximas</div>
        <div class="kpi-value">{len(proximas)}</div>
        <div class="kpi-sub">80% – 95% (~1 mes)</div>
      </div>
      <div class="kpi-box kpi-blue">
        <div class="kpi-label">🔵 Sin registro</div>
        <div class="kpi-value">{len(nunca)}</div>
        <div class="kpi-sub">Nunca ejecutadas</div>
      </div>
      <div class="kpi-box kpi-green">
        <div class="kpi-label">🟢 Vigentes</div>
        <div class="kpi-value">{len(vigentes)}</div>
        <div class="kpi-sub">Sin acción requerida</div>
      </div>
    </div>""", unsafe_allow_html=True)

    # Rutinas vencidas, críticas y próximas (priorizadas)
    prioritarias = vencidas + criticas + proximas
    if prioritarias:
        st.markdown('<div class="card"><div class="card-title">🚨 Rutinas que requieren atención</div>',
                    unsafe_allow_html=True)

        # Orden: vencidas → críticas → próximas → por % consumido descendente
        orden_estado = {"vencida": 0, "critico": 1, "proxima": 2}
        prioritarias.sort(key=lambda x: (orden_estado.get(x["estado"], 99),
                                          -x.get("pct_consumido", 0)))

        chip_data = {
            "vencida": ("chip-vencida", "VENCIDA",  "alerta-row vencida"),
            "critico": ("chip-critico", "CRÍTICA",  "alerta-row critico"),
            "proxima": ("chip-proxima", "PRÓXIMA",  "alerta-row proxima"),
        }

        for e in prioritarias[:30]:
            chip_cls, chip_txt, row_cls = chip_data[e["estado"]]
            pct = e.get("pct_consumido", 0) * 100

            km_info = f"{abs(e['km_restantes']):,} km excedidos" if e["km_restantes"] < 0 \
                      else f"{e['km_restantes']:,} km restantes"
            dias_info = f"{abs(e['dias_restantes'])} días excedidos" if e["dias_restantes"] < 0 \
                        else f"{e['dias_restantes']} días restantes"

            st.markdown(f"""<div class="{row_cls}">
              <div><strong style="color:var(--text)">Vehículo {e['vehiculo']}</strong><br>
                <span style="font-size:.72rem;color:var(--muted)">{e['km_actual']:,} km · {pct:.0f}% consumido</span></div>
              <div><strong style="color:var(--text);font-size:.88rem">{e['rutina_nombre']}</strong><br>
                <span style="font-size:.72rem;color:var(--muted)">{e['rutina_id']} · Sistema: {e['sistema']}</span></div>
              <div style="font-size:.78rem;color:var(--text)">{km_info.replace(',', '.')}</div>
              <div style="font-size:.78rem;color:var(--text)">{dias_info}</div>
              <div style="text-align:right"><span class="{chip_cls}">{chip_txt}</span></div>
            </div>""", unsafe_allow_html=True)

        if len(prioritarias) > 30:
            st.caption(f"+ {len(prioritarias) - 30} alertas adicionales")

        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.success("✅ Todas las rutinas de la flota están al día. No hay acciones pendientes.")


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 2 — PLANIFICAR Y GENERAR OT-P
# ═══════════════════════════════════════════════════════════════════
def _tab_planificar(flota, catalogo):
    # Pantalla de confirmación tras generar la OT
    if st.session_state.get("prev_confirmacion") and st.session_state.get("prev_ot_generada"):
        ot = st.session_state["prev_ot_generada"]
        data = st.session_state.get("prev_form_data", {})

        st.markdown(f"""<div class="ot-generated-big">
          <div class="ot-generated-label">✅ Se ha generado la OT Preventiva</div>
          <div class="ot-generated-number">{ot}</div>
          <div style="color:#8B949E;font-size:.85rem">Registro planificado — disponible en módulo Cierre de OT cuando se ejecute.</div>
        </div>""", unsafe_allow_html=True)

        st.markdown(f"""<div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:1rem 1.2rem;margin-bottom:1.5rem">
          <div style="font-size:.78rem;color:#8B949E;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.4rem">Resumen de la planificación</div>
          <div style="font-size:.9rem;line-height:1.7">
            <strong>Vehículo:</strong> {data.get('vehiculo', '')} &nbsp;·&nbsp;
            <strong>Fecha programada:</strong> {data.get('fecha_programada', '')} {data.get('hora_programada', '')}<br>
            <strong>Rutinas:</strong> {len(data.get('rutinas', []))} seleccionadas<br>
            <strong>Responsable:</strong> {data.get('responsable', '')} &nbsp;·&nbsp;
            <strong>Proveedor:</strong> {data.get('proveedor', '')}<br>
            <strong>Costo estimado total:</strong> <span style="color:var(--primary);font-weight:700">{_fmt_moneda(data.get('costo_total_est', 0))}</span>
          </div>
        </div>""", unsafe_allow_html=True)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown('<div class="btn-green">', unsafe_allow_html=True)
            if st.button("Planificar otra OT-P", use_container_width=True, key="prev_another"):
                for k in ["prev_vehiculo_sel", "prev_rutinas_sel", "prev_form_data",
                          "prev_confirmacion", "prev_ot_generada"]:
                    st.session_state.pop(k, None)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with col_b:
            st.markdown('<div class="btn-blue">', unsafe_allow_html=True)
            if st.button("Ir al Cierre de OT", use_container_width=True, key="prev_goto_close"):
                st.session_state["modulo"] = "cierre_ot"
                st.session_state["fase"] = "2"
                st.session_state["ot_actual"] = ot
                st.session_state["intervenciones"] = [{"desc": "", "cantidad": 1, "costo": 0.0}]
                try:
                    st.query_params["mod"] = "cierre_ot"
                except Exception:
                    pass
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with col_c:
            st.markdown('<div class="btn-gray">', unsafe_allow_html=True)
            if st.button("Volver al Hub", use_container_width=True, key="prev_to_hub"):
                _volver_al_hub()
            st.markdown('</div>', unsafe_allow_html=True)
        return

    if not flota:
        st.info("⚠️ No hay vehículos registrados. Vaya a la pestaña **Flota** para agregarlos.")
        return

    # ── SELECCIÓN DE VEHÍCULO ─────────────────────
    st.markdown('<div class="card"><div class="card-title">1️⃣ Seleccionar Vehículo</div>',
                unsafe_allow_html=True)
    vehiculos_ids = sorted(flota.keys())

    # Si vino un vehículo preseleccionado desde el hub, ubicar su índice
    veh_pre = st.session_state.pop("prev_veh_preseleccionado", None)
    idx_default = 0
    if veh_pre and veh_pre in vehiculos_ids:
        idx_default = vehiculos_ids.index(veh_pre)

    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        vehiculo_sel = st.selectbox("Vehículo a planificar *",
                                      options=vehiculos_ids,
                                      index=idx_default, key="planif_veh")
    with col_v2:
        if vehiculo_sel and vehiculo_sel in flota:
            km_actual = flota[vehiculo_sel].get("km_actual", 0)
            st.markdown(f"""<div class="costo-display" style="margin-top:.3rem">
              <div class="costo-label">KM Actual</div>
              <div class="costo-valor" style="color:var(--blue)">{km_actual:,}</div>
            </div>""".replace(',', '.'), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if not vehiculo_sel:
        return

    # ── SUGERENCIA DE RUTINAS ─────────────────────
    evaluaciones_veh = [
        e for e in _evaluar_flota_completa({vehiculo_sel: flota[vehiculo_sel]}, catalogo)
    ]
    sugeridas = [e for e in evaluaciones_veh
                 if e["estado"] in ("vencida", "critico", "proxima", "nunca_ejecutada")]

    st.markdown('<div class="card"><div class="card-title">2️⃣ Seleccionar Rutinas a Ejecutar</div>',
                unsafe_allow_html=True)

    if sugeridas:
        n_venc = sum(1 for s in sugeridas if s["estado"] == "vencida")
        st.markdown(f"""<div style="background:rgba(210,153,34,.08);border-left:3px solid var(--yellow);border-radius:6px;padding:.6rem 1rem;margin-bottom:1rem;font-size:.82rem">
          💡 <strong>{len(sugeridas)} rutina{'s' if len(sugeridas)>1 else ''} sugerida{'s' if len(sugeridas)>1 else ''}</strong> para este vehículo
          ({n_venc} vencida{'s' if n_venc != 1 else ''} · {len(sugeridas)-n_venc} próxima{'s' if len(sugeridas)-n_venc != 1 else ''} / sin registro)
        </div>""", unsafe_allow_html=True)
    else:
        st.info("ℹ️ Todas las rutinas de este vehículo están vigentes. Puede seleccionar manualmente si desea adelantar alguna.")

    # Lista de rutinas con checkboxes
    rutinas_sel_ids = []
    estados_por_id = {e["rutina_id"]: e for e in evaluaciones_veh}

    for rut in catalogo:
        ev = estados_por_id.get(rut["id"], {})
        estado = ev.get("estado", "vigente")
        chip_map = {
            "vencida":          ('chip-vencida', '🔴 VENCIDA'),
            "critico":          ('chip-critico', '🟠 CRÍTICA'),
            "proxima":          ('chip-proxima', '🟡 PRÓXIMA'),
            "nunca_ejecutada":  ('chip-nunca',   '🔵 SIN REGISTRO'),
            "vigente":          ('chip-vigente', '🟢 VIGENTE'),
        }
        chip_cls, chip_txt = chip_map[estado]

        col_check, col_info, col_period, col_chip = st.columns([0.3, 3, 1.2, 1])
        with col_check:
            # Pre-seleccionar vencidas, críticas, próximas y sin registro
            default_check = estado in ("vencida", "critico", "proxima", "nunca_ejecutada")
            checked = st.checkbox("_chk", value=default_check,
                                    key=f"chk_{rut['id']}", label_visibility="collapsed")
            if checked:
                rutinas_sel_ids.append(rut["id"])
        with col_info:
            st.markdown(f"""<div style="padding-top:.3rem">
              <div style="font-size:.88rem;font-weight:600;color:var(--text)">{rut['nombre']}</div>
              <div style="font-size:.72rem;color:var(--muted)">
                <strong>{rut['id']}</strong> · Sistema: {rut['sistema']} ·
                Duración: {rut['duracion_horas']} h
              </div>
            </div>""", unsafe_allow_html=True)
        with col_period:
            st.markdown(f"""<div style="padding-top:.4rem;font-size:.75rem;color:var(--muted);text-align:right">
              <strong style="color:var(--text)">{rut['periodicidad_km']:,} km</strong><br>
              <span>o {rut['periodicidad_dias']} días</span>
            </div>""".replace(',', '.'), unsafe_allow_html=True)
        with col_chip:
            st.markdown(f'<div style="padding-top:.4rem;text-align:right"><span class="{chip_cls}">{chip_txt}</span></div>',
                        unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    if not rutinas_sel_ids:
        st.warning("⚠️ Seleccione al menos una rutina para continuar.")
        return

    # ── CÁLCULO DE COSTOS Y DURACIÓN ─────────────
    rutinas_sel = [r for r in catalogo if r["id"] in rutinas_sel_ids]
    costo_repuestos_total = sum(
        sum(rep["cantidad"] * rep["costo_unit"] for rep in r["repuestos"])
        for r in rutinas_sel
    )
    costo_mano_obra_total = sum(r["mano_obra"] for r in rutinas_sel)
    duracion_total        = sum(r["duracion_horas"] for r in rutinas_sel)
    costo_total_est       = costo_repuestos_total + costo_mano_obra_total

    # Sistema principal = el más frecuente entre las rutinas seleccionadas
    from collections import Counter
    sistemas_counts = Counter(r["sistema"] for r in rutinas_sel)
    sistema_principal = sistemas_counts.most_common(1)[0][0]

    st.markdown('<div class="card"><div class="card-title">3️⃣ Resumen de Costos Estimados</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="costo-display"><div class="costo-label">Repuestos</div><div class="costo-valor">{_fmt_moneda(costo_repuestos_total)}</div></div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="costo-display"><div class="costo-label">Mano de Obra</div><div class="costo-valor">{_fmt_moneda(costo_mano_obra_total)}</div></div>',
                    unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="costo-display"><div class="costo-label">Duración Est.</div><div class="costo-valor" style="color:var(--blue)">{duracion_total:.1f} h</div></div>',
                    unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="costo-display"><div class="costo-label">Costo Total Est.</div><div class="costo-valor" style="color:var(--green)">{_fmt_moneda(costo_total_est)}</div></div>',
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── PROGRAMACIÓN ──────────────────────────────
    st.markdown('<div class="card"><div class="card-title">4️⃣ Programación y Recursos</div>',
                unsafe_allow_html=True)
    col_f, col_h = st.columns(2)
    with col_f:
        fecha_prog = st.date_input("Fecha programada *",
                                     value=date.today() + timedelta(days=3),
                                     min_value=date.today(),
                                     key="prev_fecha")
    with col_h:
        hora_prog = st.time_input("Hora programada *",
                                    value=datetime.strptime("08:00", "%H:%M").time(),
                                    key="prev_hora")

    col_r, col_p = st.columns(2)
    with col_r:
        responsable = st.text_input("Responsable de la ejecución *",
                                      placeholder="Ej: Jefe de taller Juan Pérez",
                                      key="prev_resp")
    with col_p:
        proveedor = st.text_input("Proveedor / Taller *",
                                    placeholder="Ej: Taller Central Vekmaint",
                                    key="prev_prov")

    observaciones = st.text_area("Observaciones de la planificación (opcional)",
                                   placeholder="Cualquier nota relevante para el mecánico",
                                   max_chars=300, key="prev_obs")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── GENERAR OT-P ──────────────────────────────
    form_ok = bool(responsable.strip()) and bool(proveedor.strip())
    col_g1, col_g2 = st.columns([3, 1])
    with col_g1:
        generar = st.button("✅ GENERAR OT PREVENTIVA",
                             disabled=not form_ok, use_container_width=True,
                             key="prev_generar_ot")
    with col_g2:
        if st.button("Limpiar", use_container_width=True, key="prev_clear"):
            for k in list(st.session_state.keys()):
                if k.startswith("chk_") or k.startswith("prev_"):
                    if k not in ("prev_tab",):
                        st.session_state.pop(k, None)
            st.rerun()

    if generar and form_ok:
        ot_num = _generar_ot_p(vehiculo_sel, sistema_principal)

        # Descripción concatenada de rutinas (para Modo_Falla, que en preventivo es el detalle)
        rutinas_desc = " + ".join(r["nombre"] for r in rutinas_sel)
        repuestos_desc = " | ".join(
            f"{rep['cantidad']}x {rep['desc']}"
            for r in rutinas_sel for rep in r["repuestos"]
        )

        f1_data = {
            "Fecha_Inicio_Inactividad": f"{fecha_prog} {hora_prog}",
            "Fecha_Registro_F1":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Fecha_Programada":         f"{fecha_prog} {hora_prog}",
            "OT":                       ot_num,
            "Numero_Interno":           vehiculo_sel.upper(),
            "Conductor":                "N/A - Preventivo",
            "Tipo_Mantenimiento":       "P",
            "Kilometraje":              flota[vehiculo_sel].get("km_actual", 0),
            "Sistema":                  sistema_principal,
            "Modo_Falla":               rutinas_desc[:200],  # se reutiliza el campo para mostrar rutinas
            "Rutinas_IDs":              ",".join(rutinas_sel_ids),
            "Rutinas_Nombres":          rutinas_desc,
            "Repuestos_Planificados":   repuestos_desc,
            "Costo_Estimado_Repuestos": costo_repuestos_total,
            "Costo_Estimado_Mano_Obra": costo_mano_obra_total,
            "Costo_Estimado_Total":     costo_total_est,
            "Duracion_Estimada_Horas":  duracion_total,
            "Responsable_Planificado":  responsable.strip(),
            "Proveedor_Planificado":    proveedor.strip(),
            "Observaciones_Plan":       observaciones.strip(),
            "Estado_OT":                "P",
            "Origen":                   "Mantenimiento_Preventivo",
        }
        _registrar_ot_pendiente(ot_num, f1_data)

        st.session_state["prev_confirmacion"] = True
        st.session_state["prev_ot_generada"]  = ot_num
        st.session_state["prev_form_data"]    = {
            "vehiculo":         vehiculo_sel,
            "fecha_programada": str(fecha_prog),
            "hora_programada":  str(hora_prog),
            "rutinas":          rutinas_sel_ids,
            "responsable":      responsable.strip(),
            "proveedor":        proveedor.strip(),
            "costo_total_est":  costo_total_est,
        }
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 3 — CRONOGRAMA GANTT
# ═══════════════════════════════════════════════════════════════════
def _tab_cronograma(flota, catalogo):
    """
    Calendario mensual de programación de mantenimientos preventivos.
    Muestra las OT-P programadas (planificadas en pestaña Planificar) en cuadrícula
    Lunes-Domingo. Cada día muestra los preventivos agendados para ese día.
    """
    import calendar as _cal

    # ── Estado de navegación del calendario ──
    today = date.today()
    if "prev_cal_year" not in st.session_state:
        st.session_state["prev_cal_year"] = today.year
    if "prev_cal_month" not in st.session_state:
        st.session_state["prev_cal_month"] = today.month
    cal_year  = st.session_state["prev_cal_year"]
    cal_month = st.session_state["prev_cal_month"]

    # ── Cargar OT-P pendientes (preventivos planificados) ──
    pendientes = _cargar_pendientes()
    eventos_por_dia = {}  # {date_obj: [evento, ...]}

    for ot, datos in pendientes.items():
        if not ot.startswith("OT-P-"):
            continue
        fecha_prog_str = datos.get("Fecha_Programada", "")
        try:
            # Formato esperado: "YYYY-MM-DD HH:MM:SS" o "YYYY-MM-DD"
            fp = fecha_prog_str.split(" ")[0] if " " in fecha_prog_str else fecha_prog_str
            fp_date = datetime.strptime(fp, "%Y-%m-%d").date()
        except Exception:
            continue
        eventos_por_dia.setdefault(fp_date, []).append({
            "ot":         ot,
            "vehiculo":   datos.get("Numero_Interno", ""),
            "sistema":    datos.get("Sistema", ""),
            "rutinas":    datos.get("Rutinas_Nombres", ""),
            "responsable": datos.get("Responsable_Planificado", ""),
            "fecha":      fp_date,
            "hora":       fecha_prog_str.split(" ")[1] if " " in fecha_prog_str else "",
        })

    # ── Encabezado: navegación de mes ──
    meses_es = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    col_prev, col_titulo, col_hoy, col_next = st.columns([1, 4, 1, 1])
    with col_prev:
        if st.button("← Mes anterior", key="cal_prev", use_container_width=True):
            if cal_month == 1:
                st.session_state["prev_cal_year"] = cal_year - 1
                st.session_state["prev_cal_month"] = 12
            else:
                st.session_state["prev_cal_month"] = cal_month - 1
            st.rerun()
    with col_titulo:
        st.markdown(f"""<div style="text-align:center;padding:.4rem 0">
          <div style="font-family:'Exo 2',sans-serif;font-size:1.4rem;font-weight:800;color:var(--text)">
            {meses_es[cal_month]} {cal_year}
          </div>
        </div>""", unsafe_allow_html=True)
    with col_hoy:
        if st.button("Hoy", key="cal_hoy", use_container_width=True):
            st.session_state["prev_cal_year"] = today.year
            st.session_state["prev_cal_month"] = today.month
            st.rerun()
    with col_next:
        if st.button("Mes siguiente →", key="cal_next", use_container_width=True):
            if cal_month == 12:
                st.session_state["prev_cal_year"] = cal_year + 1
                st.session_state["prev_cal_month"] = 1
            else:
                st.session_state["prev_cal_month"] = cal_month + 1
            st.rerun()

    # Total preventivos del mes
    n_mes = sum(len(evs) for d, evs in eventos_por_dia.items()
                if d.year == cal_year and d.month == cal_month)
    st.markdown(f"""<div style="text-align:center;font-size:.85rem;color:var(--muted);margin-bottom:1rem">
      <strong style="color:var(--purple)">{n_mes}</strong>
      preventivo{'s' if n_mes != 1 else ''} programado{'s' if n_mes != 1 else ''} en este mes
    </div>""", unsafe_allow_html=True)

    # ── Construir matriz del calendario ──
    # calendar.monthcalendar devuelve listas de semanas con días (0 = día fuera del mes)
    _cal.setfirstweekday(_cal.MONDAY)
    semanas = _cal.monthcalendar(cal_year, cal_month)

    # ── Dibujar encabezado de días ──
    dias_sem = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
    header_html = '<div class="cal-grid cal-header">'
    for d in dias_sem:
        header_html += f'<div class="cal-day-name">{d}</div>'
    header_html += '</div>'
    st.markdown(header_html, unsafe_allow_html=True)

    # ── Dibujar celdas ──
    for semana in semanas:
        st.markdown('<div class="cal-grid cal-week">', unsafe_allow_html=True)
        for dia_num in semana:
            if dia_num == 0:
                st.markdown('<div class="cal-cell cal-empty"></div>', unsafe_allow_html=True)
                continue

            fecha_celda = date(cal_year, cal_month, dia_num)
            es_hoy = (fecha_celda == today)
            es_pasado = (fecha_celda < today)
            eventos = eventos_por_dia.get(fecha_celda, [])

            cell_classes = ["cal-cell"]
            if es_hoy:    cell_classes.append("cal-today")
            if es_pasado and not es_hoy: cell_classes.append("cal-past")
            if eventos:   cell_classes.append("cal-has-events")

            eventos_html = ""
            for ev in eventos[:3]:
                color_cls = "cal-event-overdue" if (es_pasado and not es_hoy) else "cal-event"
                eventos_html += f"""<div class="{color_cls}" title="{ev['ot']}">
                  {ev['vehiculo']} · {ev['sistema'][:10]}
                </div>"""
            if len(eventos) > 3:
                eventos_html += f'<div class="cal-event-more">+{len(eventos) - 3} más</div>'

            cell_html = f"""<div class="{' '.join(cell_classes)}">
              <div class="cal-day-num">{dia_num}</div>
              {eventos_html}
            </div>"""
            st.markdown(cell_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Detalle del día seleccionado / día con eventos ──
    if eventos_por_dia:
        dias_mes_con_eventos = sorted(d for d in eventos_por_dia
                                       if d.year == cal_year and d.month == cal_month)
        if dias_mes_con_eventos:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="card"><div class="card-title">📋 Detalle de programaciones del mes</div>',
                        unsafe_allow_html=True)
            for d in dias_mes_con_eventos:
                evs = eventos_por_dia[d]
                fecha_str = d.strftime("%A %d de %B").capitalize()
                st.markdown(f"""<div style="font-family:'Exo 2',sans-serif;font-size:.95rem;font-weight:700;color:var(--purple);margin:.8rem 0 .4rem">
                  📅 {fecha_str}
                </div>""", unsafe_allow_html=True)
                for ev in evs:
                    rutinas_corto = ev["rutinas"][:80] + ("..." if len(ev["rutinas"]) > 80 else "")
                    st.markdown(f"""<div style="background:var(--surface2);border:1px solid var(--border);border-left:3px solid var(--purple);border-radius:8px;padding:.6rem 1rem;margin-bottom:.4rem">
                      <div style="display:flex;justify-content:space-between;align-items:center">
                        <strong style="color:var(--text)">Vehículo {ev['vehiculo']}</strong>
                        <span style="font-size:.72rem;color:var(--muted);font-family:'Exo 2',sans-serif;font-weight:700">{ev['ot']}</span>
                      </div>
                      <div style="font-size:.78rem;color:var(--muted);margin-top:.2rem">
                        🔧 <strong style="color:var(--text)">{ev['sistema']}</strong> ·
                        {ev['hora'] if ev['hora'] else '—'} ·
                        Responsable: {ev['responsable'] or '—'}
                      </div>
                      <div style="font-size:.78rem;color:var(--muted);margin-top:.3rem">
                        {rutinas_corto}
                      </div>
                    </div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("ℹ️ No hay preventivos programados aún. Vaya a la pestaña **Planificar y Generar OT** para programar mantenimientos.")


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 4 — GESTIÓN DE FLOTA
# ═══════════════════════════════════════════════════════════════════
def _tab_flota(flota, catalogo):
    st.markdown('<div class="card"><div class="card-title">🚛 Registrar / Actualizar Vehículo</div>',
                unsafe_allow_html=True)

    # Toggle entre nuevo vehículo y actualizar uno existente
    if flota:
        modo = st.radio("Acción:", options=["📝 Actualizar existente", "➕ Registrar nuevo"],
                         horizontal=True, key="flota_modo")
    else:
        modo = "➕ Registrar nuevo"
        st.caption("Aún no hay vehículos. Registre el primero.")

    if modo == "📝 Actualizar existente" and flota:
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col1:
            ids_flota = sorted(flota.keys())
            veh_id_sel = st.selectbox("Vehículo a actualizar", options=ids_flota,
                                        key="flota_id_sel")
            veh_id = veh_id_sel
        # Pre-llenar marca/modelo desde el registro existente
        existente = flota.get(veh_id, {})
        with col2:
            marca = st.text_input("Marca", value=existente.get("marca", ""),
                                    key="flota_marca_upd")
        with col3:
            modelo = st.text_input("Modelo", value=existente.get("modelo", ""),
                                     key="flota_modelo_upd")
        with col4:
            km_anterior = existente.get("km_actual", 0)
            km_nuevo = st.number_input(
                "Nuevo kilometraje *", min_value=0, step=100,
                value=km_anterior, key="flota_km_upd", format="%d",
                help=f"Km actual registrado: {km_anterior:,}".replace(",", ".")
            )
            if km_nuevo > 0:
                delta = km_nuevo - km_anterior
                color = "var(--primary)" if delta >= 0 else "var(--red)"
                signo = "+" if delta >= 0 else ""
                st.markdown(f"<div style='font-size:.85rem;color:{color};font-weight:600;margin-top:-.4rem'>"
                            f"{km_nuevo:,} km".replace(",", ".") +
                            (f" <span style='color:var(--muted);font-weight:400;font-size:.78rem'>"
                             f"({signo}{delta:,} desde último)</span>".replace(",", ".")
                             if delta != 0 else "") + "</div>", unsafe_allow_html=True)
    else:
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col1:
            veh_id = st.text_input("Número interno *", placeholder="Ej: 0042", key="flota_id")
        with col2:
            marca = st.text_input("Marca", placeholder="Ej: Volvo", key="flota_marca")
        with col3:
            modelo = st.text_input("Modelo", placeholder="Ej: B7R", key="flota_modelo")
        with col4:
            km_nuevo = st.number_input("Kilometraje actual *", min_value=0, step=100,
                                          value=0, key="flota_km", format="%d")
            if km_nuevo > 0:
                st.markdown(f"<div style='font-size:.85rem;color:var(--primary);font-weight:600;margin-top:-.4rem'>"
                            f"{km_nuevo:,} km".replace(",", ".") + "</div>", unsafe_allow_html=True)

    if st.button("Guardar / Actualizar", key="flota_save",
                 disabled=(not veh_id.strip() or km_nuevo == 0)):
        veh_key = veh_id.strip().upper()
        if veh_key not in flota:
            flota[veh_key] = {
                "km_actual":         km_nuevo,
                "km_actualizado_en": date.today().isoformat(),
                "marca":             marca.strip(),
                "modelo":            modelo.strip(),
                "rutinas_ultimas":   {},
            }
            msg = f"✅ Vehículo {veh_key} registrado con {km_nuevo:,} km"
        else:
            flota[veh_key]["km_actual"]         = km_nuevo
            flota[veh_key]["km_actualizado_en"] = date.today().isoformat()
            if marca.strip(): flota[veh_key]["marca"]  = marca.strip()
            if modelo.strip(): flota[veh_key]["modelo"] = modelo.strip()
            msg = f"✅ Vehículo {veh_key} actualizado a {km_nuevo:,} km"
        _guardar_flota(flota)
        st.success(msg.replace(',', '.'))
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Lista de flota actual
    if flota:
        st.markdown('<div class="card"><div class="card-title">📋 Flota registrada</div>',
                    unsafe_allow_html=True)
        flota_data = []
        for vid, vdata in sorted(flota.items()):
            marca_v  = vdata.get('marca', '—') or '—'
            modelo_v = vdata.get('modelo', '—') or '—'
            flota_data.append({
                "Vehículo":         vid,
                "Marca":            marca_v,
                "Modelo":           modelo_v,
                "Km actual":        f"{vdata.get('km_actual', 0):,}".replace(',', '.'),
                "Actualizado":      vdata.get('km_actualizado_en', '—'),
                "Rutinas con reg.": len(vdata.get('rutinas_ultimas', {})),
            })
        st.dataframe(pd.DataFrame(flota_data), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Registrar ejecución manual de una rutina (para inicialización de datos)
        with st.expander("📝 Registrar ejecución previa de una rutina (opcional)"):
            st.caption("Útil al cargar datos históricos para que el sistema calcule los vencimientos desde esa fecha.")
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                veh_reg = st.selectbox("Vehículo", options=sorted(flota.keys()), key="reg_veh")
            with col_b:
                rut_opciones = {r["id"]: f"{r['id']} - {r['nombre']}" for r in catalogo}
                rut_reg = st.selectbox("Rutina", options=list(rut_opciones.keys()),
                                         format_func=lambda x: rut_opciones[x], key="reg_rut")
            with col_c:
                km_reg = st.number_input("Km ejecución", min_value=0, step=100,
                                           value=0, key="reg_km", format="%d")
                if km_reg > 0:
                    st.markdown(f"<div style='font-size:.78rem;color:var(--primary);font-weight:600;margin-top:-.4rem'>"
                                f"{km_reg:,} km".replace(",", ".") + "</div>", unsafe_allow_html=True)
            with col_d:
                fecha_reg = st.date_input("Fecha", value=date.today(), key="reg_fecha")
            if st.button("Guardar registro histórico", key="reg_save"):
                if "rutinas_ultimas" not in flota[veh_reg]:
                    flota[veh_reg]["rutinas_ultimas"] = {}
                flota[veh_reg]["rutinas_ultimas"][rut_reg] = {
                    "km":    km_reg,
                    "fecha": fecha_reg.isoformat(),
                }
                _guardar_flota(flota)
                st.success(f"✅ Registrado: {rut_reg} en vehículo {veh_reg} a los {km_reg:,} km".replace(',', '.'))
                st.rerun()
    else:
        st.info("ℹ️ No hay vehículos registrados. Registre el primer vehículo arriba.")


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 5 — CATÁLOGO DE RUTINAS
# ═══════════════════════════════════════════════════════════════════
def _tab_catalogo(catalogo):
    st.markdown('<div class="card"><div class="card-title">📚 Catálogo de Rutinas Preventivas</div>',
                unsafe_allow_html=True)
    st.caption(f"El catálogo contiene {len(catalogo)} rutinas parametrizadas. "
               "Cada rutina incluye periodicidad (km/días), repuestos estándar y costo de mano de obra.")

    for r in catalogo:
        costo_rep = sum(rep["cantidad"] * rep["costo_unit"] for rep in r["repuestos"])
        costo_tot = costo_rep + r["mano_obra"]
        n_rep = len(r["repuestos"])

        st.markdown(f"""<div class="catalog-card">
          <div class="catalog-id">{r['id']}</div>
          <div>
            <div class="catalog-name">{r['nombre']}</div>
            <div class="catalog-meta">
              Sistema: <strong>{r['sistema']}</strong> ·
              Duración: {r['duracion_horas']} h ·
              {n_rep} repuesto{'s' if n_rep != 1 else ''} ·
              Mano de obra: {_fmt_moneda(r['mano_obra'])}
            </div>
          </div>
          <div class="catalog-period">
            cada <strong>{r['periodicidad_km']:,} km</strong><br>
            <span>o <strong>{r['periodicidad_dias']} días</strong></span>
          </div>
          <div class="catalog-period">
            Costo est.<br>
            <strong style="color:var(--primary)">{_fmt_moneda(costo_tot)}</strong>
          </div>
        </div>""".replace(',', '.'), unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.caption("💡 El catálogo es editable desde el archivo `catalogo_rutinas.json` (edición avanzada en próxima versión).")


# ═══════════════════════════════════════════════════════════════════
#  run()
# ═══════════════════════════════════════════════════════════════════
def run():
    _init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    _render_back_button("main")
    _header()

    flota    = _cargar_flota()
    catalogo = _cargar_catalogo()

    tab_dash, tab_plan, tab_cron, tab_flota, tab_cat = st.tabs([
        "📊 Dashboard de Alertas",
        "📝 Planificar y Generar OT",
        "📅 Calendario",
        "🚛 Flota",
        "📚 Catálogo de Rutinas",
    ])

    with tab_dash:
        _tab_dashboard(flota, catalogo)
    with tab_plan:
        _tab_planificar(flota, catalogo)
    with tab_cron:
        _tab_cronograma(flota, catalogo)
    with tab_flota:
        _tab_flota(flota, catalogo)
    with tab_cat:
        _tab_catalogo(catalogo)


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        st.set_page_config(page_title="Mantenimiento Preventivo",
                           page_icon="📅", layout="wide",
                           initial_sidebar_state="collapsed")
    except Exception:
        pass
    run()