"""
mantenimiento_preventivo.py — v2.0
====================================
Módulo de planificación de mantenimiento preventivo con arquitectura simplificada
de 2 pestañas:
  1. Planificación: calendario mensual + panel lateral con rutinas pendientes priorizadas
  2. Flota & Catálogo: gestión administrativa

Flujo principal:
  Click rutina del panel → click día del calendario → Generar OTs

Reglas:
- Las rutinas se priorizan por % consumido (vencidas → críticas → próximas → sin reg.)
- Múltiples rutinas del mismo vehículo en el mismo día se consolidan en UNA OT-P
- El kilometraje viene de la inspección preoperacional (auto-actualiza flota)
- Una vez generada la OT-P, las rutinas desaparecen del panel
- Cuando se cierre la OT, se actualizan rutinas_ultimas y vuelven a calcular
"""
import streamlit as st
import pandas as pd
import json
import os
import calendar as _cal
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict, Counter

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTES Y CATÁLOGO
# ═══════════════════════════════════════════════════════════════════
PENDIENTES_DB       = "ots_pendientes.json"
FLOTA_DB            = "flota_vehiculos.json"
CATALOGO_RUTINAS_DB = "catalogo_rutinas.json"

SIST_ABREV = {
    "Motor":                        "MOT", "Frenos":             "FRE",
    "Direccion":                    "DIR", "Suspension":         "SUS",
    "Llantas":                      "LLA", "Refrigeracion":      "REF",
    "Electrico":                    "ELE",
    "Carroceria Externa - Chasis":  "CCH",
    "Habitaculo":                   "HAB", "Transmision":        "TRA",
}
# Prefijo especial para OT-P que involucra múltiples sistemas
SIST_VARIOS = "VAR"

CATALOGO_DEFAULT = [
    {"id": "RUT-001", "nombre": "Cambio de aceite motor y filtro", "sistema": "Motor",
     "periodicidad_km": 15000, "periodicidad_dias": 180, "duracion_horas": 1.5,
     "repuestos": [
         {"desc": "Aceite motor 15W-40", "cantidad": 8, "costo_unit": 35000},
         {"desc": "Filtro de aceite",    "cantidad": 1, "costo_unit": 45000}],
     "mano_obra": 80000},
    {"id": "RUT-002", "nombre": "Cambio filtros de aire y combustible", "sistema": "Motor",
     "periodicidad_km": 30000, "periodicidad_dias": 365, "duracion_horas": 1.0,
     "repuestos": [
         {"desc": "Filtro de aire",        "cantidad": 1, "costo_unit": 65000},
         {"desc": "Filtro de combustible", "cantidad": 1, "costo_unit": 55000}],
     "mano_obra": 60000},
    {"id": "RUT-003", "nombre": "Inspección y ajuste de frenos", "sistema": "Frenos",
     "periodicidad_km": 20000, "periodicidad_dias": 180, "duracion_horas": 2.0,
     "repuestos": [{"desc": "Pastillas de freno delanteras", "cantidad": 1, "costo_unit": 180000}],
     "mano_obra": 120000},
    {"id": "RUT-004", "nombre": "Cambio líquido de frenos", "sistema": "Frenos",
     "periodicidad_km": 40000, "periodicidad_dias": 365, "duracion_horas": 1.5,
     "repuestos": [{"desc": "Líquido de frenos DOT 4", "cantidad": 2, "costo_unit": 28000}],
     "mano_obra": 80000},
    {"id": "RUT-005", "nombre": "Rotación y balanceo de llantas", "sistema": "Llantas",
     "periodicidad_km": 10000, "periodicidad_dias": 90, "duracion_horas": 1.0,
     "repuestos": [], "mano_obra": 60000},
    {"id": "RUT-006", "nombre": "Cambio refrigerante motor", "sistema": "Refrigeracion",
     "periodicidad_km": 50000, "periodicidad_dias": 730, "duracion_horas": 1.5,
     "repuestos": [{"desc": "Refrigerante concentrado", "cantidad": 4, "costo_unit": 25000}],
     "mano_obra": 80000},
    {"id": "RUT-007", "nombre": "Inspección sistema eléctrico y batería", "sistema": "Electrico",
     "periodicidad_km": 20000, "periodicidad_dias": 180, "duracion_horas": 1.0,
     "repuestos": [], "mano_obra": 50000},
    {"id": "RUT-008", "nombre": "Alineación y balanceo", "sistema": "Suspension",
     "periodicidad_km": 20000, "periodicidad_dias": 180, "duracion_horas": 1.5,
     "repuestos": [], "mano_obra": 90000},
    {"id": "RUT-009", "nombre": "Cambio aceite caja y diferencial", "sistema": "Transmision",
     "periodicidad_km": 60000, "periodicidad_dias": 730, "duracion_horas": 2.0,
     "repuestos": [{"desc": "Aceite de caja 75W-90", "cantidad": 4, "costo_unit": 42000}],
     "mano_obra": 110000},
    {"id": "RUT-010", "nombre": "Engrase general del chasis", "sistema": "Carroceria Externa - Chasis",
     "periodicidad_km": 10000, "periodicidad_dias": 90, "duracion_horas": 0.5,
     "repuestos": [{"desc": "Grasa multipropósito", "cantidad": 1, "costo_unit": 18000}],
     "mano_obra": 30000},
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
    _guardar_catalogo(CATALOGO_DEFAULT)
    return CATALOGO_DEFAULT


def _guardar_catalogo(data):
    with open(CATALOGO_RUTINAS_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _cargar_flota():
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


# ═══════════════════════════════════════════════════════════════════
#  LÓGICA DE NEGOCIO
# ═══════════════════════════════════════════════════════════════════
def _generar_ot_p(vehiculo, sistema_principal, multiples_sistemas=False):
    """
    Genera el radicado de la OT-P.
    Si la OT involucra MÁS DE UN SISTEMA distinto, se usa el prefijo 'VAR' (varios)
    en lugar de la abreviatura del sistema principal.
    """
    now = datetime.now()
    veh = vehiculo.strip().upper().replace(" ", "")[:6]
    if multiples_sistemas:
        sist = SIST_VARIOS
    else:
        sist = SIST_ABREV.get(sistema_principal, "GEN")
    return f"OT-P-{sist}-{veh}-{now.strftime('%y%m%d')}-{now.strftime('%H%M')}"


def _calcular_estado_rutina(km_actual, ultima_km, ultima_fecha_str, periodicidad_km, periodicidad_dias):
    """
    Evalúa el estado de una rutina basándose en km recorridos y tiempo transcurrido
    desde la última ejecución.

    Si NO hay registro previo de ejecución (vehículo recién dado de alta), el sistema
    INFIERE la última ejecución teórica como el último múltiplo de la periodicidad
    que el vehículo ya superó. Esto permite que un bus con 124.600 km muestre RUT-001
    (cada 15.000 km) como vigente al 30.6% (faltan 5.400 km para los 135.000 km),
    en lugar de "sin registro".

    Estados:
    - vencida:  ≥ 100% del periodo (km o días)
    - critico:  ≥ 95%
    - proxima:  ≥ 80%
    - vigente:  < 80%
    - nunca_ejecutada: solo si km_actual = 0 (vehículo sin operación)
    """
    hoy = date.today()

    # ── Caso 1: hay registro previo explícito ──
    if ultima_km is not None and ultima_fecha_str is not None:
        try:
            ultima_fecha = datetime.strptime(ultima_fecha_str, "%Y-%m-%d").date()
        except Exception:
            ultima_fecha = None

        if ultima_fecha is not None:
            km_transc   = max(0, km_actual - ultima_km)
            dias_transc = (hoy - ultima_fecha).days
            km_restantes   = periodicidad_km - km_transc
            dias_restantes = periodicidad_dias - dias_transc
            pct_km   = km_transc / periodicidad_km if periodicidad_km > 0 else 0
            pct_dias = dias_transc / periodicidad_dias if periodicidad_dias > 0 else 0
            pct = max(pct_km, pct_dias)
            if pct >= 1.0:    return ("vencida", km_restantes, dias_restantes, pct)
            if pct >= 0.95:   return ("critico", km_restantes, dias_restantes, pct)
            if pct >= 0.80:   return ("proxima", km_restantes, dias_restantes, pct)
            return ("vigente", km_restantes, dias_restantes, pct)

    # ── Caso 2: NO hay registro — inferir basándose en múltiplos de periodicidad ──
    if km_actual <= 0:
        # Vehículo sin operación todavía
        return ("nunca_ejecutada", periodicidad_km, periodicidad_dias, 0.0)

    if periodicidad_km <= 0:
        return ("nunca_ejecutada", 0, 0, 0.0)

    # Calcular el último múltiplo de periodicidad_km que el vehículo ya superó.
    # Ej: km_actual=124.600, periodicidad=15.000 → último múltiplo = 120.000
    # Ej: km_actual=299.800, periodicidad=15.000 → último múltiplo = 285.000
    # Ej: km_actual=10.000, periodicidad=15.000 → último múltiplo = 0 (no ha pasado nunca)
    multiplo_pasado = (km_actual // periodicidad_km) * periodicidad_km

    if multiplo_pasado == 0:
        # El vehículo aún no ha alcanzado el primer múltiplo de la periodicidad.
        # Ej: bus con 8.000 km y rutina cada 15.000 km — todavía no debe ejecutarse
        # Calcular cuánto le falta para el primer hito
        km_restantes = periodicidad_km - km_actual
        pct = km_actual / periodicidad_km
        if pct >= 0.95:   return ("critico", km_restantes, periodicidad_dias, pct)
        if pct >= 0.80:   return ("proxima", km_restantes, periodicidad_dias, pct)
        return ("vigente", km_restantes, periodicidad_dias, pct)

    # El vehículo YA superó al menos un hito de la rutina.
    # El próximo hito es multiplo_pasado + periodicidad_km
    proximo_hito = multiplo_pasado + periodicidad_km
    km_transc = km_actual - multiplo_pasado          # km desde el último hito teórico
    km_restantes = proximo_hito - km_actual          # km hasta el próximo

    pct_km = km_transc / periodicidad_km
    # Por días: estimamos basado en operación promedio (~100 km/día). Para inferencia
    # asumimos que el último hito teórico se cumplió "hace km_transc / 100 días".
    # Esto es aproximado pero coherente con la realidad operativa.
    dias_estimados_transc = int(km_transc / 100)  # asume 100 km/día promedio
    dias_restantes = max(0, periodicidad_dias - dias_estimados_transc)
    pct_dias = dias_estimados_transc / periodicidad_dias if periodicidad_dias > 0 else 0
    pct = max(pct_km, pct_dias)

    if pct >= 1.0:    return ("vencida", km_restantes, dias_restantes, pct)
    if pct >= 0.95:   return ("critico", km_restantes, dias_restantes, pct)
    if pct >= 0.80:   return ("proxima", km_restantes, dias_restantes, pct)
    return ("vigente", km_restantes, dias_restantes, pct)


def _evaluar_flota_completa(flota, catalogo):
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
                "marca":           veh_data.get("marca", ""),
                "modelo":          veh_data.get("modelo", ""),
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


def _rutinas_priorizadas(flota, catalogo):
    """Lista de rutinas que requieren acción, ordenadas por urgencia.
       Excluye las que ya tienen una OT-P pendiente O están en borradores
       (programadas pero aún sin generar OT)."""
    todas = _evaluar_flota_completa(flota, catalogo)
    requieren = [r for r in todas if r["estado"] in ("vencida", "critico", "proxima", "nunca_ejecutada")]

    # 1. Excluir las que ya tienen OT-P pendiente
    pendientes = _cargar_pendientes()
    rutinas_ya_programadas = set()
    for ot, datos in pendientes.items():
        if not ot.startswith("OT-P-"):
            continue
        veh = datos.get("Numero_Interno", "")
        for rid in datos.get("Rutinas_IDs", "").split(","):
            rid = rid.strip()
            if rid:
                rutinas_ya_programadas.add((veh, rid))

    # 2. Excluir las que están en borradores (todavía sin OT generada)
    borradores = st.session_state.get("prev_borradores", {})
    for (veh, _fecha), rids in borradores.items():
        for rid in rids:
            rutinas_ya_programadas.add((veh, rid))

    requieren = [r for r in requieren
                 if (r["vehiculo"], r["rutina_id"]) not in rutinas_ya_programadas]

    orden = {"vencida": 0, "critico": 1, "proxima": 2, "nunca_ejecutada": 3}
    requieren.sort(key=lambda x: (orden.get(x["estado"], 99), -x.get("pct_consumido", 0)))
    return requieren


def _calcular_costo_rutina(rut):
    rep = sum(r["cantidad"] * r["costo_unit"] for r in rut["repuestos"])
    return {
        "repuestos": rep,
        "mano_obra": rut["mano_obra"],
        "total":     rep + rut["mano_obra"],
        "duracion":  rut["duracion_horas"],
    }


def _fmt_moneda(v):
    return f"$ {v:,.0f}".replace(",", ".") if v else "$ 0"


def _generar_ots_desde_borradores(borradores, flota, catalogo):
    """
    `borradores`: dict {(veh, fecha_iso): [rutina_id, ...]}
    Para cada (veh, fecha), genera UNA OT-P consolidando sus rutinas.
    La hora se toma de prev_horas_borrador o por defecto 08:00.
    """
    cat_by_id = {r["id"]: r for r in catalogo}
    horas_borr = st.session_state.get("prev_horas_borrador", {})
    creadas = []

    for (veh, fecha_iso), rutinas_ids in borradores.items():
        rutinas_obj = [cat_by_id[rid] for rid in rutinas_ids if rid in cat_by_id]
        if not rutinas_obj:
            continue

        costo_rep = sum(_calcular_costo_rutina(r)["repuestos"] for r in rutinas_obj)
        costo_mo  = sum(_calcular_costo_rutina(r)["mano_obra"] for r in rutinas_obj)
        duracion  = sum(_calcular_costo_rutina(r)["duracion"]  for r in rutinas_obj)
        costo_tot = costo_rep + costo_mo

        sistemas_counts = Counter(r["sistema"] for r in rutinas_obj)
        sistema_principal = sistemas_counts.most_common(1)[0][0]
        # Si la OT involucra más de un sistema distinto, usar prefijo VAR
        sistemas_unicos = list(sistemas_counts.keys())
        es_multiples_sistemas = len(sistemas_unicos) > 1
        # Texto descriptivo del sistema en la OT (todos los sistemas o solo uno)
        sistema_label = " + ".join(sistemas_unicos) if es_multiples_sistemas else sistema_principal

        rutinas_desc = " + ".join(r["nombre"] for r in rutinas_obj)
        repuestos_desc = " | ".join(
            f"{rep['cantidad']}x {rep['desc']}"
            for r in rutinas_obj for rep in r["repuestos"]
        )

        # Hora seleccionada por el usuario, o 08:00 por defecto
        hora_str = horas_borr.get((veh, fecha_iso), "08:00") + ":00"
        fecha_hora_completa = f"{fecha_iso} {hora_str}"

        ot_num = _generar_ot_p(veh, sistema_principal, multiples_sistemas=es_multiples_sistemas)
        km_actual_veh = flota.get(veh, {}).get("km_actual", 0)

        f1_data = {
            "Fecha_Inicio_Inactividad": fecha_hora_completa,
            "Fecha_Registro_F1":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Fecha_Programada":         fecha_hora_completa,
            "OT":                       ot_num,
            "Numero_Interno":           veh,
            "Conductor":                "N/A - Preventivo",
            "Tipo_Mantenimiento":       "P",
            "Kilometraje":              km_actual_veh,
            "Sistema":                  sistema_label,
            "Modo_Falla":               rutinas_desc[:200],
            "Rutinas_IDs":              ",".join(rid for rid in rutinas_ids),
            "Rutinas_Nombres":          rutinas_desc,
            "Repuestos_Planificados":   repuestos_desc,
            "Costo_Estimado_Repuestos": costo_rep,
            "Costo_Estimado_Mano_Obra": costo_mo,
            "Costo_Estimado_Total":     costo_tot,
            "Duracion_Estimada_Horas":  duracion,
            "Responsable_Planificado":  "Por asignar",
            "Proveedor_Planificado":    "Por asignar",
            "Observaciones_Plan":       "",
            "Estado_OT":                "P",
            "Origen":                   "Mantenimiento_Preventivo",
        }
        db = _cargar_pendientes()
        db[ot_num] = f1_data
        _guardar_pendientes(db)
        creadas.append(ot_num)

    return creadas


def _calcular_kpis(flota, catalogo):
    todas = _evaluar_flota_completa(flota, catalogo)
    if not todas:
        return {"cumplimiento": 0, "vencidas": 0, "criticas": 0,
                "proximas": 0, "vigentes": 0, "sin_reg": 0, "ot_p_pendientes": 0,
                "total_rutinas": 0}
    vencidas = sum(1 for r in todas if r["estado"] == "vencida")
    criticas = sum(1 for r in todas if r["estado"] == "critico")
    proximas = sum(1 for r in todas if r["estado"] == "proxima")
    vigentes = sum(1 for r in todas if r["estado"] == "vigente")
    sin_reg  = sum(1 for r in todas if r["estado"] == "nunca_ejecutada")
    cumplimiento = round((1 - vencidas / len(todas)) * 100) if len(todas) > 0 else 100
    pendientes = _cargar_pendientes()
    n_otp = sum(1 for k in pendientes if k.startswith("OT-P-"))
    return {
        "cumplimiento":     cumplimiento,
        "vencidas":         vencidas,
        "criticas":         criticas,
        "proximas":         proximas,
        "vigentes":         vigentes,
        "sin_reg":          sin_reg,
        "ot_p_pendientes":  n_otp,
        "total_rutinas":    len(todas),
    }


def _volver_al_hub():
    for k in ["prev_borradores", "prev_horas_borrador", "prev_rutina_seleccionada",
              "prev_cal_year", "prev_cal_month", "prev_ots_creadas", "prev_dia_detalle"]:
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
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:1.5rem}
.kpi-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;display:flex;align-items:center;gap:.9rem}
.kpi-icon{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0;font-weight:800}
.kpi-icon.icon-green{background:rgba(63,185,80,.15);color:var(--green)}
.kpi-icon.icon-purple{background:rgba(124,77,255,.15);color:var(--primary)}
.kpi-icon.icon-red{background:rgba(248,81,73,.15);color:var(--red)}
.kpi-icon.icon-orange{background:rgba(255,107,0,.15);color:var(--orange)}
.kpi-text{flex:1}
.kpi-label-small{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-weight:600;margin-bottom:.1rem}
.kpi-value-big{font-family:'Exo 2',sans-serif;font-size:1.6rem;font-weight:800;color:var(--text);line-height:1.1}
.section-title{font-family:'Exo 2',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text);margin:0 0 .8rem 0;display:flex;align-items:center;gap:.5rem}
.routine-panel{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem;height:fit-content}
.routine-panel-title{font-family:'Exo 2',sans-serif;font-size:.95rem;font-weight:700;color:var(--text);margin-bottom:.4rem;padding-bottom:.5rem;border-bottom:1px solid var(--border)}
.routine-panel-sub{font-size:.72rem;color:var(--muted);margin-bottom:.8rem}
.routine-chip{display:inline-block;padding:1px 6px;border-radius:10px;font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.chip-vencida{background:rgba(248,81,73,.18);color:var(--red);border:1px solid rgba(248,81,73,.4)}
.chip-critico{background:rgba(255,107,0,.18);color:var(--orange);border:1px solid rgba(255,107,0,.4)}
.chip-proxima{background:rgba(210,153,34,.15);color:var(--yellow);border:1px solid rgba(210,153,34,.4)}
.chip-nunca{background:rgba(10,132,255,.15);color:var(--blue);border:1px solid rgba(10,132,255,.4)}
.cal-wrapper{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem}
.cal-day-name{text-align:center;font-family:'Exo 2',sans-serif;font-weight:700;font-size:.72rem;color:var(--muted);padding:.3rem;letter-spacing:.1em;text-transform:uppercase}
.cal-cell-empty{background:transparent;border:1px dashed var(--border);opacity:.25;border-radius:8px;min-height:75px}
.selection-banner{background:linear-gradient(90deg,rgba(124,77,255,.15),rgba(124,77,255,.05));border:1px solid var(--primary);border-radius:10px;padding:.7rem 1rem;margin-bottom:1rem;font-size:.85rem}
.selection-banner strong{color:var(--primary)}
.borrador-summary{background:rgba(124,77,255,.06);border:1px dashed var(--primary);border-radius:10px;padding:.7rem 1rem;margin:1rem 0;font-size:.82rem}
.borrador-summary strong{color:var(--primary)}
[data-testid="stButton"] button{background:var(--primary)!important;color:white!important;border:none!important;border-radius:8px!important;font-family:'Exo 2',sans-serif!important;font-weight:700!important;font-size:.85rem!important;padding:.5rem 1rem!important;text-transform:uppercase!important;letter-spacing:.04em!important;transition:all .15s}
[data-testid="stButton"] button:hover{background:var(--primary-dk)!important;transform:translateY(-1px);box-shadow:0 4px 16px rgba(124,77,255,.3)!important}
[data-testid="stButton"] button:disabled{background:var(--surface2)!important;color:var(--muted)!important;transform:none!important;box-shadow:none!important}
.btn-day button{background:var(--surface2)!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:8px!important;font-family:'Inter',sans-serif!important;font-weight:500!important;text-transform:none!important;padding:.4rem .3rem!important;letter-spacing:normal!important;font-size:.7rem!important;line-height:1.15!important;min-height:75px;width:100%;white-space:pre-line!important}
.btn-day button:hover{background:rgba(124,77,255,.12)!important;border-color:var(--primary)!important;transform:none!important;box-shadow:none!important}
.btn-day-today button{border:2px solid var(--primary)!important;background:rgba(124,77,255,.08)!important}
.btn-day-past button{opacity:.55}
.btn-day-busy button{border-color:var(--primary)!important;background:rgba(124,77,255,.05)!important}
.btn-day-active button{border:2px solid var(--orange)!important;background:rgba(255,107,0,.10)!important;box-shadow:0 0 12px rgba(255,107,0,.25)!important}
/* ── Panel de detalle del día ── */
.day-detail-panel{background:rgba(0,0,0,.25);border:1px solid var(--primary);border-radius:12px;padding:1rem 1.2rem;margin-top:1rem}
.day-detail-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;padding-bottom:.6rem;border-bottom:1px solid var(--border)}
.day-detail-title{font-family:'Exo 2',sans-serif;font-size:1rem;font-weight:800;color:var(--primary)}
.day-detail-sub{font-size:.74rem;color:var(--muted);margin-top:.1rem}
.day-detail-veh{background:var(--surface2);border:1px solid var(--border);border-left:4px solid var(--primary);border-radius:8px;padding:.7rem .9rem;margin-bottom:.6rem}
.day-detail-veh-otp{background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.4);border-left:4px solid var(--green);border-radius:8px;padding:.7rem .9rem;margin-bottom:.6rem}
.day-detail-veh-header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;margin-bottom:.4rem}
.day-detail-veh-name{font-family:'Exo 2',sans-serif;font-weight:700;font-size:.92rem;color:var(--text)}
.day-detail-veh-meta{font-size:.72rem;color:var(--muted)}
.day-detail-rutina{background:rgba(0,0,0,.2);border-radius:6px;padding:.4rem .6rem;font-size:.78rem;color:var(--text);margin-bottom:.3rem}
.btn-quitar button{background:rgba(248,81,73,.12)!important;color:var(--red)!important;border:1px solid rgba(248,81,73,.3)!important;border-radius:6px!important;font-size:.85rem!important;font-weight:700!important;text-transform:none!important;padding:.3rem!important;letter-spacing:normal!important;min-height:32px}
.btn-quitar button:hover{background:rgba(248,81,73,.25)!important;border-color:var(--red)!important;transform:none!important;box-shadow:none!important}
.btn-cerrar-detalle button{background:var(--surface2)!important;color:var(--muted)!important;border:1px solid var(--border)!important;text-transform:none!important;font-size:.78rem!important;font-weight:500!important;letter-spacing:normal!important;padding:.4rem .8rem!important;margin-top:.6rem!important}
.btn-cerrar-detalle button:hover{background:var(--border)!important;color:var(--text)!important;transform:none!important;box-shadow:none!important}
.btn-routine button{background:var(--surface2)!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:8px!important;font-family:'Inter',sans-serif!important;font-weight:500!important;text-transform:none!important;padding:.55rem .7rem!important;letter-spacing:normal!important;font-size:.78rem!important;text-align:left!important;line-height:1.3!important;width:100%;min-height:55px;white-space:pre-line!important}
.btn-routine button:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.3)!important}
/* El coloreo de los botones de rutinas se inyecta dinámicamente desde _render_panel_rutinas */
.btn-nav button{background:var(--surface2)!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:8px!important;text-transform:none!important;font-size:.78rem!important;font-weight:500!important;letter-spacing:normal!important;padding:.4rem .8rem!important}
.btn-nav button:hover{background:var(--border)!important;transform:none!important;box-shadow:none!important}
.btn-back button{background:var(--surface2)!important;color:var(--muted)!important;border:1px solid var(--border)!important;text-transform:none!important;font-size:.82rem!important;font-weight:500!important;padding:.4rem 1rem!important;letter-spacing:normal!important}
.btn-back button:hover{background:var(--border)!important;color:var(--text)!important;transform:none!important;box-shadow:none!important}
.btn-generate button{background:linear-gradient(135deg,#FF6B00,#FF9A40)!important;font-size:.95rem!important;padding:.7rem 1.4rem!important;box-shadow:0 0 20px rgba(255,107,0,.3)}
.btn-generate button:hover{box-shadow:0 0 28px rgba(255,107,0,.5)!important}
.btn-clear button{background:rgba(248,81,73,.12)!important;color:var(--red)!important;border:1px solid rgba(248,81,73,.3)!important;text-transform:none!important;font-size:.78rem!important}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input{background:var(--surface2)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:8px!important;font-family:'Inter',sans-serif!important}
[data-testid="stSelectbox"]>div>div{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:8px!important}
[data-baseweb="tab-list"]{background:var(--surface)!important;border-radius:8px!important;padding:.3rem!important;gap:.3rem!important}
[data-baseweb="tab"]{background:transparent!important;color:var(--muted)!important;border-radius:6px!important;font-family:'Inter',sans-serif!important;font-weight:600!important;font-size:.85rem!important;padding:.5rem 1.2rem!important}
[data-baseweb="tab"][aria-selected="true"]{background:var(--primary)!important;color:white!important}
.empty-msg{text-align:center;padding:2rem 1rem;color:var(--muted);font-size:.85rem}
.empty-msg strong{color:var(--text);display:block;font-size:1rem;margin-bottom:.3rem;font-family:'Exo 2',sans-serif}
#MainMenu,footer,header{visibility:hidden}.block-container{padding-top:0!important;max-width:1400px!important}
@media(max-width:768px){
  .kpi-row{grid-template-columns:repeat(2,1fr)}
  .cal-wrapper{padding:.6rem}
}
</style>"""


# ═══════════════════════════════════════════════════════════════════
#  ESTADO
# ═══════════════════════════════════════════════════════════════════
def _init_state():
    today = date.today()
    defaults = {
        "prev_borradores":           {},     # {(veh, fecha_iso): [rutina_id, ...]}
        "prev_horas_borrador":       {},     # {(veh, fecha_iso): "HH:MM"}
        "prev_rutina_seleccionada":  None,
        "prev_cal_year":             today.year,
        "prev_cal_month":            today.month,
        "prev_dia_detalle":          None,   # fecha_iso del día abierto en el detalle
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
        <p class="sub">Planificación · Calendario · Generación automática de OT-P</p>
      </div>
      <div style="margin-left:auto"><span class="badge-pill">Plan</span></div>
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 1 — PLANIFICACIÓN (vista principal)
# ═══════════════════════════════════════════════════════════════════
def _tab_planificacion(flota, catalogo):
    if not flota:
        st.markdown("""<div class="empty-msg">
          <strong>🚛 No hay vehículos en la flota</strong>
          Vaya a la pestaña <strong>Flota & Catálogo</strong> para registrar vehículos
          o realice una inspección preoperacional para que se autoregistren.
        </div>""", unsafe_allow_html=True)
        return

    # ── KPIs ───────────────────────────────────────
    kpis = _calcular_kpis(flota, catalogo)
    st.markdown(f"""<div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-icon icon-green">✓</div>
        <div class="kpi-text">
          <div class="kpi-label-small">Cumplimiento Plan</div>
          <div class="kpi-value-big">{kpis['cumplimiento']}%</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon icon-purple">📋</div>
        <div class="kpi-text">
          <div class="kpi-label-small">OT-P Pendientes</div>
          <div class="kpi-value-big">{kpis['ot_p_pendientes']}</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon icon-red">⚠</div>
        <div class="kpi-text">
          <div class="kpi-label-small">Rutinas Vencidas</div>
          <div class="kpi-value-big">{kpis['vencidas']}</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon icon-orange">!</div>
        <div class="kpi-text">
          <div class="kpi-label-small">Críticas / Próximas</div>
          <div class="kpi-value-big">{kpis['criticas']} / {kpis['proximas']}</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Indicador de selección activa ─────────────
    sel = st.session_state.get("prev_rutina_seleccionada")
    if sel:
        veh_sel, rid_sel = sel
        rut_obj = next((r for r in catalogo if r["id"] == rid_sel), None)
        if rut_obj:
            st.markdown(f"""<div class="selection-banner">
              ✋ <strong>Rutina seleccionada:</strong> Veh <strong>{veh_sel}</strong> · {rid_sel} · {rut_obj['nombre']}
              <span style="color:var(--muted);margin-left:.6rem">→ Ahora haga click en el día del calendario para programarla.</span>
            </div>""", unsafe_allow_html=True)

    # ── Borradores resumen ────────────────────────
    borradores = st.session_state.get("prev_borradores", {})
    if borradores:
        n_borr = sum(len(v) for v in borradores.values())
        n_ots_a_generar = len(borradores)
        st.markdown(f"""<div class="borrador-summary">
          📝 <strong>{n_borr} rutina{'s' if n_borr != 1 else ''}</strong> programada{'s' if n_borr != 1 else ''}
          en el calendario (se consolidan en <strong>{n_ots_a_generar} OT{'s' if n_ots_a_generar != 1 else ''} preventiva{'s' if n_ots_a_generar != 1 else ''}</strong>
          al generar). <span style="color:var(--muted)">Haga click en un día con programación para ver detalles, ajustar la hora o quitar rutinas.</span>
        </div>""", unsafe_allow_html=True)

    # ── Layout: calendario + panel rutinas ────────
    col_cal, col_panel = st.columns([2, 1], gap="medium")

    with col_cal:
        _render_calendario(flota, catalogo, borradores)

        # Botones de acción
        st.markdown("<br>", unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            st.markdown('<div class="btn-generate">', unsafe_allow_html=True)
            if st.button("✅ GENERAR OTs PREVENTIVAS",
                         disabled=not borradores, use_container_width=True,
                         key="btn_generar_otp"):
                creadas = _generar_ots_desde_borradores(borradores, flota, catalogo)
                st.session_state["prev_borradores"] = {}
                st.session_state["prev_horas_borrador"] = {}
                st.session_state["prev_rutina_seleccionada"] = None
                st.session_state["prev_dia_detalle"] = None
                st.session_state["prev_ots_creadas"] = creadas
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with col_btn2:
            if borradores:
                st.markdown('<div class="btn-clear">', unsafe_allow_html=True)
                if st.button("🗑 Limpiar borradores", use_container_width=True,
                             key="btn_limpiar_borr"):
                    st.session_state["prev_borradores"] = {}
                    st.session_state["prev_horas_borrador"] = {}
                    st.session_state["prev_rutina_seleccionada"] = None
                    st.session_state["prev_dia_detalle"] = None
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.get("prev_ots_creadas"):
            ots = st.session_state.pop("prev_ots_creadas")
            preview = ", ".join(ots[:3]) + (f" ... y {len(ots) - 3} más" if len(ots) > 3 else "")
            st.success(f"✅ Se generaron {len(ots)} OT{'s' if len(ots)!=1 else ''} preventiva{'s' if len(ots)!=1 else ''}: {preview}")

    with col_panel:
        _render_panel_rutinas(flota, catalogo)


# ═══════════════════════════════════════════════════════════════════
#  RENDER: CALENDARIO MENSUAL
# ═══════════════════════════════════════════════════════════════════
def _render_calendario(flota, catalogo, borradores):
    today = date.today()
    cal_year  = st.session_state["prev_cal_year"]
    cal_month = st.session_state["prev_cal_month"]
    meses_es = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    # Cargar OT-P pendientes
    pendientes = _cargar_pendientes()
    otp_por_dia = defaultdict(list)
    for ot, datos in pendientes.items():
        if not ot.startswith("OT-P-"):
            continue
        fp_str = datos.get("Fecha_Programada", "")
        try:
            fp = fp_str.split(" ")[0] if " " in fp_str else fp_str
            fp_date = datetime.strptime(fp, "%Y-%m-%d").date()
        except Exception:
            continue
        otp_por_dia[fp_date].append({
            "ot": ot, "veh": datos.get("Numero_Interno", ""),
            "sistema": datos.get("Sistema", ""),
        })

    # Borradores por día
    borr_por_dia = defaultdict(list)
    for (veh, fecha_iso), rids in borradores.items():
        try:
            d = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
            for rid in rids:
                borr_por_dia[d].append((veh, rid))
        except Exception:
            continue

    st.markdown('<div class="cal-wrapper">', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">📅 Programación y Planificación</div>',
                unsafe_allow_html=True)

    col_p, col_t, col_h, col_n = st.columns([1, 3, 1, 1])
    with col_p:
        st.markdown('<div class="btn-nav">', unsafe_allow_html=True)
        if st.button("←", key="cal_prev", use_container_width=True):
            if cal_month == 1:
                st.session_state["prev_cal_year"] -= 1
                st.session_state["prev_cal_month"] = 12
            else:
                st.session_state["prev_cal_month"] -= 1
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with col_t:
        st.markdown(f"""<div style="text-align:center;padding:.3rem 0">
          <div style="font-family:'Exo 2',sans-serif;font-size:1.15rem;font-weight:800;color:var(--text)">
            {meses_es[cal_month]} {cal_year}
          </div>
          <div style="font-size:.72rem;color:var(--muted)">Vista Mensual de Flota</div>
        </div>""", unsafe_allow_html=True)
    with col_h:
        st.markdown('<div class="btn-nav">', unsafe_allow_html=True)
        if st.button("Hoy", key="cal_hoy", use_container_width=True):
            st.session_state["prev_cal_year"] = today.year
            st.session_state["prev_cal_month"] = today.month
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with col_n:
        st.markdown('<div class="btn-nav">', unsafe_allow_html=True)
        if st.button("→", key="cal_next", use_container_width=True):
            if cal_month == 12:
                st.session_state["prev_cal_year"] += 1
                st.session_state["prev_cal_month"] = 1
            else:
                st.session_state["prev_cal_month"] += 1
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # Días de la semana
    dias_sem = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
    cols_dn = st.columns(7, gap="small")
    for i, d in enumerate(dias_sem):
        with cols_dn[i]:
            st.markdown(f'<div class="cal-day-name">{d}</div>', unsafe_allow_html=True)

    # Cuadrícula
    _cal.setfirstweekday(_cal.MONDAY)
    semanas = _cal.monthcalendar(cal_year, cal_month)
    sel = st.session_state.get("prev_rutina_seleccionada")

    for w_idx, semana in enumerate(semanas):
        cols = st.columns(7, gap="small")
        for i, dia_num in enumerate(semana):
            with cols[i]:
                if dia_num == 0:
                    st.markdown('<div class="cal-cell-empty"></div>', unsafe_allow_html=True)
                    continue

                fecha_celda = date(cal_year, cal_month, dia_num)
                fecha_iso = fecha_celda.isoformat()
                es_hoy = (fecha_celda == today)
                es_pasado = (fecha_celda < today)
                es_dia_detalle = (st.session_state.get("prev_dia_detalle") == fecha_iso)

                eventos_borr = borr_por_dia.get(fecha_celda, [])
                eventos_otp  = otp_por_dia.get(fecha_celda, [])

                # ── Construir texto del botón ──
                lines = [str(dia_num)]
                count_shown = 0

                # Borradores: mostrar VEH·RUT individual (no agrupado)
                for (veh, rid) in eventos_borr:
                    if count_shown >= 3:
                        break
                    # Acortar el ID de rutina (RUT-001 → R001)
                    rid_corto = rid.replace("RUT-", "R")
                    lines.append(f"📝{veh}·{rid_corto}")
                    count_shown += 1

                # OT-P generadas
                for ev in eventos_otp:
                    if count_shown >= 3:
                        break
                    pref = "🔴" if (es_pasado and not es_hoy) else "✓"
                    lines.append(f"{pref}{ev['veh']}")
                    count_shown += 1

                total_eventos = len(eventos_borr) + len(eventos_otp)
                if total_eventos > count_shown:
                    lines.append(f"+{total_eventos - count_shown}")

                btn_label = "\n".join(lines)

                btn_class = "btn-day"
                if es_hoy: btn_class += " btn-day-today"
                if es_pasado and not es_hoy: btn_class += " btn-day-past"
                if total_eventos > 0: btn_class += " btn-day-busy"
                if es_dia_detalle: btn_class += " btn-day-active"

                # Tooltip dinámico
                if sel:
                    tooltip = f"Programar la rutina seleccionada el día {dia_num}"
                elif total_eventos > 0:
                    tooltip = f"Día {dia_num} — click para ver y editar las {total_eventos} programación(es)"
                else:
                    tooltip = f"Día {dia_num} — primero seleccione una rutina del panel"

                st.markdown(f'<div class="{btn_class}">', unsafe_allow_html=True)
                btn_key = f"day_{cal_year}_{cal_month}_{dia_num}_{w_idx}_{i}"
                if st.button(btn_label, key=btn_key, use_container_width=True, help=tooltip):
                    if sel:
                        # Hay rutina seleccionada → programarla en este día
                        veh_sel, rid_sel = sel
                        key_borr = (veh_sel, fecha_iso)
                        if key_borr not in st.session_state["prev_borradores"]:
                            st.session_state["prev_borradores"][key_borr] = []
                        if rid_sel not in st.session_state["prev_borradores"][key_borr]:
                            st.session_state["prev_borradores"][key_borr].append(rid_sel)
                        # Hora por defecto (08:00) si no existe
                        if key_borr not in st.session_state["prev_horas_borrador"]:
                            st.session_state["prev_horas_borrador"][key_borr] = "08:00"
                        st.session_state["prev_rutina_seleccionada"] = None
                        st.rerun()
                    elif total_eventos > 0:
                        # Toggle del panel de detalle
                        if es_dia_detalle:
                            st.session_state["prev_dia_detalle"] = None
                        else:
                            st.session_state["prev_dia_detalle"] = fecha_iso
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    # ── PANEL DETALLE DEL DÍA SELECCIONADO ──
    dia_det = st.session_state.get("prev_dia_detalle")
    if dia_det:
        try:
            d_obj = datetime.strptime(dia_det, "%Y-%m-%d").date()
            _render_detalle_dia(d_obj, catalogo, borr_por_dia, otp_por_dia)
        except Exception:
            pass

    st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  RENDER: PANEL DE DETALLE DEL DÍA SELECCIONADO
# ═══════════════════════════════════════════════════════════════════
def _render_detalle_dia(fecha, catalogo, borr_por_dia, otp_por_dia):
    """
    Muestra detalle de programaciones del día: lista de rutinas individuales,
    selector de hora, opción de quitar cada rutina del borrador.
    """
    eventos_borr = borr_por_dia.get(fecha, [])
    eventos_otp  = otp_por_dia.get(fecha, [])

    if not eventos_borr and not eventos_otp:
        return

    fecha_iso = fecha.isoformat()
    cat_by_id = {r["id"]: r for r in catalogo}

    fecha_str_human = fecha.strftime("%A, %d de %B de %Y").capitalize()
    n_total = len(eventos_borr) + len(eventos_otp)

    st.markdown(f"""<div class="day-detail-panel">
      <div class="day-detail-header">
        <div>
          <div class="day-detail-title">📅 {fecha_str_human}</div>
          <div class="day-detail-sub">{n_total} programación{'es' if n_total != 1 else ''} en este día</div>
        </div>
      </div>
    """, unsafe_allow_html=True)

    # ══ BORRADORES (editables) ═══════════════════
    if eventos_borr:
        # Agrupar por vehículo para mostrar consolidación
        borr_por_veh = defaultdict(list)
        for (veh, rid) in eventos_borr:
            borr_por_veh[veh].append(rid)

        for veh, rids in borr_por_veh.items():
            key_borr = (veh, fecha_iso)
            hora_actual = st.session_state["prev_horas_borrador"].get(key_borr, "08:00")

            # Calcular costos consolidados de este vehículo+día
            rutinas_obj = [cat_by_id[r] for r in rids if r in cat_by_id]
            costo_total = sum(_calcular_costo_rutina(r)["total"] for r in rutinas_obj)
            duracion = sum(r["duracion_horas"] for r in rutinas_obj)

            st.markdown(f"""<div class="day-detail-veh">
              <div class="day-detail-veh-header">
                <span class="day-detail-veh-name">📝 Vehículo {veh}</span>
                <span class="day-detail-veh-meta">
                  {len(rids)} rutina{'s' if len(rids) != 1 else ''} ·
                  {duracion:.1f}h estimada · {_fmt_moneda(costo_total)}
                </span>
              </div>""", unsafe_allow_html=True)

            # Lista de rutinas con botón de quitar
            for rid in rids:
                rut_obj = cat_by_id.get(rid)
                if not rut_obj:
                    continue
                col_r, col_b = st.columns([5, 1])
                with col_r:
                    costo_r = _calcular_costo_rutina(rut_obj)["total"]
                    st.markdown(f"""<div class="day-detail-rutina">
                      <span style="color:var(--primary);font-weight:700;font-family:'Exo 2',sans-serif">{rid}</span>
                      <span style="color:var(--text);margin:0 .4rem">·</span>
                      {rut_obj['nombre']}
                      <span style="color:var(--muted);font-size:.72rem;margin-left:.4rem">
                        ({rut_obj['sistema']} · {_fmt_moneda(costo_r)})
                      </span>
                    </div>""", unsafe_allow_html=True)
                with col_b:
                    st.markdown('<div class="btn-quitar">', unsafe_allow_html=True)
                    if st.button("✕", key=f"del_{veh}_{rid}_{fecha_iso}",
                                 help="Quitar esta rutina del día",
                                 use_container_width=True):
                        st.session_state["prev_borradores"][key_borr].remove(rid)
                        if not st.session_state["prev_borradores"][key_borr]:
                            del st.session_state["prev_borradores"][key_borr]
                            st.session_state["prev_horas_borrador"].pop(key_borr, None)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

            # Selector de hora para este vehículo+día
            col_h_lbl, col_h_inp, _ = st.columns([1.2, 1, 4])
            with col_h_lbl:
                st.markdown('<div style="padding-top:.4rem;font-size:.78rem;color:var(--muted)">⏰ Hora ingreso a taller:</div>',
                            unsafe_allow_html=True)
            with col_h_inp:
                horas_opciones = [f"{h:02d}:00" for h in range(6, 20)]  # 06:00 a 19:00
                if hora_actual not in horas_opciones:
                    horas_opciones.insert(0, hora_actual)
                hora_sel = st.selectbox("Hora", options=horas_opciones,
                                          index=horas_opciones.index(hora_actual),
                                          key=f"hora_{veh}_{fecha_iso}",
                                          label_visibility="collapsed")
                if hora_sel != hora_actual:
                    st.session_state["prev_horas_borrador"][key_borr] = hora_sel
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    # ══ OT-P YA GENERADAS (solo lectura) ═════════
    if eventos_otp:
        st.markdown('<div style="margin-top:.8rem"></div>', unsafe_allow_html=True)
        for ev in eventos_otp:
            st.markdown(f"""<div class="day-detail-veh-otp">
              <div class="day-detail-veh-header">
                <span class="day-detail-veh-name">✅ Vehículo {ev['veh']} — OT generada</span>
                <span class="day-detail-veh-meta">{ev['ot']}</span>
              </div>
              <div style="font-size:.76rem;color:var(--muted);margin-top:.3rem">
                Sistema: {ev['sistema']} · Para editar/cerrar esta OT use el módulo <strong style="color:var(--text)">Cierre de OT</strong>
              </div>
            </div>""", unsafe_allow_html=True)

    # Botón cerrar panel
    col_close, _ = st.columns([1, 4])
    with col_close:
        st.markdown('<div class="btn-cerrar-detalle">', unsafe_allow_html=True)
        if st.button("Cerrar detalle", key=f"close_det_{fecha_iso}"):
            st.session_state["prev_dia_detalle"] = None
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  RENDER: PANEL LATERAL DE RUTINAS PRIORIZADAS
# ═══════════════════════════════════════════════════════════════════
def _render_panel_rutinas(flota, catalogo):
    rutinas = _rutinas_priorizadas(flota, catalogo)
    n_vencidas = sum(1 for r in rutinas if r["estado"] == "vencida")
    n_criticas = sum(1 for r in rutinas if r["estado"] == "critico")
    n_total = len(rutinas)

    st.markdown('<div class="routine-panel">', unsafe_allow_html=True)
    st.markdown(f"""<div class="routine-panel-title">
      🚨 Estado Crítico de Cumplimiento
    </div>
    <div class="routine-panel-sub">
      {n_total} rutina{'s' if n_total != 1 else ''} requieren atención · Click para seleccionar y programar
    </div>""", unsafe_allow_html=True)

    if n_vencidas + n_criticas > 0:
        st.markdown(f"""<div style="display:flex;justify-content:space-around;background:var(--surface2);border-radius:8px;padding:.5rem;margin-bottom:.8rem">
          <div style="text-align:center">
            <div style="color:var(--red);font-family:'Exo 2',sans-serif;font-size:1.4rem;font-weight:800;line-height:1">{n_vencidas}</div>
            <div style="color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.05em;margin-top:.2rem">Vencidas</div>
          </div>
          <div style="text-align:center">
            <div style="color:var(--orange);font-family:'Exo 2',sans-serif;font-size:1.4rem;font-weight:800;line-height:1">{n_criticas}</div>
            <div style="color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.05em;margin-top:.2rem">Críticas</div>
          </div>
        </div>""", unsafe_allow_html=True)

    if not rutinas:
        st.markdown("""<div class="empty-msg" style="padding:1.5rem .5rem">
          ✅ <strong>Todo al día</strong>
          No hay rutinas pendientes.
        </div></div>""", unsafe_allow_html=True)
        return

    # Filtro por vehículo
    vehiculos = sorted(set(r["vehiculo"] for r in rutinas))
    if len(vehiculos) > 1:
        veh_filtro = st.selectbox("Filtrar:",
                                    options=["Todos"] + vehiculos,
                                    key="filtro_veh_panel",
                                    label_visibility="collapsed")
        if veh_filtro != "Todos":
            rutinas = [r for r in rutinas if r["vehiculo"] == veh_filtro]

    sel = st.session_state.get("prev_rutina_seleccionada")
    sel_key = sel if sel else (None, None)

    chip_map = {
        "vencida":          ("VENCIDA",  "chip-vencida",  "vencida",  "🟥"),
        "critico":          ("CRÍTICA",  "chip-critico",  "critico",  "🟧"),
        "proxima":          ("PRÓXIMA",  "chip-proxima",  "proxima",  "🟨"),
        "nunca_ejecutada":  ("SIN REG.", "chip-nunca",    "nunca",    "🟦"),
    }

    # CSS por estado de rutina - se inyecta UNA vez al inicio del panel
    # Truco: cada st.markdown/st.button queda envuelto en su propio stElementContainer.
    # Usamos :has() para detectar el container que contiene el marker, y luego + para
    # alcanzar el siguiente stElementContainer hermano (que contiene el botón).
    st.markdown("""<style>
    /* Marcador invisible — solo sirve para que el CSS detecte qué color aplicar al botón siguiente */
    .routine-marker { display: none; }

    /* El container con marker es hermano del container con botón. Lo detectamos con :has() */
    [data-testid="stElementContainer"]:has(> div > .routine-marker.mk-vencida) + [data-testid="stElementContainer"] button,
    [data-testid="stElementContainer"]:has(.routine-marker.mk-vencida) + [data-testid="stElementContainer"] button {
        background: rgba(248,81,73,.22) !important;
        border: 1px solid rgba(248,81,73,.6) !important;
        border-left: 5px solid #F85149 !important;
        color: #FFCFCB !important;
        font-weight: 600 !important;
    }
    [data-testid="stElementContainer"]:has(> div > .routine-marker.mk-critico) + [data-testid="stElementContainer"] button,
    [data-testid="stElementContainer"]:has(.routine-marker.mk-critico) + [data-testid="stElementContainer"] button {
        background: rgba(255,107,0,.22) !important;
        border: 1px solid rgba(255,107,0,.6) !important;
        border-left: 5px solid #FF6B00 !important;
        color: #FFD8B8 !important;
        font-weight: 600 !important;
    }
    [data-testid="stElementContainer"]:has(> div > .routine-marker.mk-proxima) + [data-testid="stElementContainer"] button,
    [data-testid="stElementContainer"]:has(.routine-marker.mk-proxima) + [data-testid="stElementContainer"] button {
        background: rgba(210,153,34,.20) !important;
        border: 1px solid rgba(210,153,34,.6) !important;
        border-left: 5px solid #D29922 !important;
        color: #F0DBA0 !important;
        font-weight: 600 !important;
    }
    [data-testid="stElementContainer"]:has(> div > .routine-marker.mk-nunca) + [data-testid="stElementContainer"] button,
    [data-testid="stElementContainer"]:has(.routine-marker.mk-nunca) + [data-testid="stElementContainer"] button {
        background: rgba(10,132,255,.20) !important;
        border: 1px solid rgba(10,132,255,.6) !important;
        border-left: 5px solid #0A84FF !important;
        color: #B8D9FF !important;
        font-weight: 600 !important;
    }
    [data-testid="stElementContainer"]:has(> div > .routine-marker.mk-selected) + [data-testid="stElementContainer"] button,
    [data-testid="stElementContainer"]:has(.routine-marker.mk-selected) + [data-testid="stElementContainer"] button {
        background: rgba(124,77,255,.32) !important;
        border: 2px solid #7C4DFF !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        box-shadow: 0 0 18px rgba(124,77,255,.5) !important;
    }
    /* Hover */
    [data-testid="stElementContainer"]:has(.routine-marker.mk-vencida) + [data-testid="stElementContainer"] button:hover {
        background: rgba(248,81,73,.32) !important; transform: translateY(-1px);
    }
    [data-testid="stElementContainer"]:has(.routine-marker.mk-critico) + [data-testid="stElementContainer"] button:hover {
        background: rgba(255,107,0,.32) !important; transform: translateY(-1px);
    }
    [data-testid="stElementContainer"]:has(.routine-marker.mk-proxima) + [data-testid="stElementContainer"] button:hover {
        background: rgba(210,153,34,.30) !important; transform: translateY(-1px);
    }
    [data-testid="stElementContainer"]:has(.routine-marker.mk-nunca) + [data-testid="stElementContainer"] button:hover {
        background: rgba(10,132,255,.30) !important; transform: translateY(-1px);
    }
    </style>""", unsafe_allow_html=True)

    for r in rutinas[:25]:
        chip_txt, chip_cls, btn_color_cls, _ = chip_map[r["estado"]]
        is_selected = (r["vehiculo"], r["rutina_id"]) == sel_key

        line1 = f"Veh {r['vehiculo']} · {r['rutina_id']}"
        nombre_corto = r['rutina_nombre'][:38] + ("..." if len(r['rutina_nombre']) > 38 else "")
        btn_label = f"{line1}\n{nombre_corto}"

        # Mostrar chip + info arriba del botón
        pct = r.get("pct_consumido", 0) * 100
        if r["estado"] == "vencida" and r["km_restantes"] < 0:
            extra = f"❗ {abs(r['km_restantes']):,} km exc."
        elif r["estado"] == "nunca_ejecutada":
            extra = "Sin histórico"
        else:
            extra = f"{pct:.0f}% · {max(0,r['km_restantes']):,} km rest"
        extra = extra.replace(",", ".")

        st.markdown(f"""<div style="display:flex;justify-content:space-between;align-items:center;font-size:.65rem;margin-bottom:-.15rem;margin-top:.4rem">
          <span class="routine-chip {chip_cls}">{chip_txt}</span>
          <span style="color:var(--muted);font-size:.68rem">{extra}</span>
        </div>""", unsafe_allow_html=True)

        # Marcador con clase de estado — el siguiente botón se pinta automáticamente
        marker_class = "mk-selected" if is_selected else f"mk-{btn_color_cls}"
        st.markdown(f'<span class="routine-marker {marker_class}"></span>',
                    unsafe_allow_html=True)

        btn_key = f"rut_{r['vehiculo']}_{r['rutina_id']}"
        if st.button(btn_label, key=btn_key, use_container_width=True):
            if is_selected:
                st.session_state["prev_rutina_seleccionada"] = None
            else:
                st.session_state["prev_rutina_seleccionada"] = (r["vehiculo"], r["rutina_id"])
            st.rerun()

    if len(rutinas) > 25:
        st.markdown(f'<div style="font-size:.72rem;color:var(--muted);text-align:center;margin-top:.5rem">+ {len(rutinas) - 25} rutinas adicionales</div>',
                    unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  PESTAÑA 2 — FLOTA & CATÁLOGO
# ═══════════════════════════════════════════════════════════════════
def _tab_flota_catalogo(flota, catalogo):
    sub_flota, sub_catalogo = st.tabs(["🚛 Flota", "📚 Catálogo de Rutinas"])

    with sub_flota:
        _subtab_flota(flota, catalogo)
    with sub_catalogo:
        _subtab_catalogo(catalogo)


def _subtab_flota(flota, catalogo):
    """
    Visor simplificado de la flota.
    El registro/edición/baja de vehículos se hace ahora en el módulo
    'Gestión de Flota' del Hub principal — esta sub-pestaña solo muestra
    el resumen para que el operador del módulo Preventivo verifique
    el inventario al programar rutinas.
    """
    st.markdown('<div class="section-title">🚛 Flota Registrada</div>',
                unsafe_allow_html=True)

    if not flota:
        st.markdown("""<div style="background:rgba(255,107,0,.08);border:1px solid rgba(255,107,0,.3);
          border-radius:10px;padding:1rem 1.2rem;margin:1rem 0;font-size:.88rem;color:#FF9A40">
          <strong>⚠️ Aún no hay vehículos registrados</strong><br>
          Para empezar a usar el módulo de mantenimiento preventivo primero debe registrar
          la flota en el módulo <strong>"Gestión de Flota"</strong> desde el Hub principal.
        </div>""", unsafe_allow_html=True)
        return

    # Resumen rápido
    n_total = len(flota)
    sistemas_count = {}
    for v in flota.values():
        marca = v.get("marca", "—")
        sistemas_count[marca] = sistemas_count.get(marca, 0) + 1

    st.markdown(f"""<div style="background:rgba(124,77,255,.06);border:1px solid rgba(124,77,255,.25);
      border-radius:10px;padding:.9rem 1.1rem;margin:.5rem 0 1rem 0;font-size:.85rem">
      <strong style="color:var(--text)">{n_total}</strong> vehículo{'s' if n_total != 1 else ''} en flota ·
      <span style="color:var(--muted)">distribución por marca:
      {' · '.join(f'<strong>{n}</strong> {m}' for m, n in sorted(sistemas_count.items(), key=lambda x: -x[1]))}</span>
    </div>""", unsafe_allow_html=True)

    # Tabla de vehículos (solo lectura)
    rows = []
    for veh_id in sorted(flota.keys()):
        v = flota[veh_id]
        rows.append({
            "Núm. Interno": veh_id,
            "Placa":         v.get("placa", "—"),
            "Marca":         v.get("marca", "—"),
            "Referencia":    v.get("referencia", v.get("modelo", "—")),
            "Modelo":        v.get("modelo", "—"),
            "Km Actual":     f"{v.get('km_actual', 0):,}".replace(",", "."),
            "Última Insp.":  v.get("km_actualizado_en", "—"),
        })
    import pandas as pd
    df_resumen = pd.DataFrame(rows)
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    # Mensaje de redirección al módulo de Gestión de Flota
    st.markdown("""<div style="background:rgba(10,132,255,.08);border:1px solid rgba(10,132,255,.3);
      border-radius:10px;padding:.9rem 1.1rem;margin-top:1rem;font-size:.85rem;color:#7EC4FF">
      ℹ️ Para <strong>registrar nuevos vehículos</strong>, <strong>editar datos</strong>,
      <strong>inactivar</strong> o <strong>importar de forma masiva</strong> desde Excel,
      vaya al módulo <strong>"Gestión de Flota"</strong> en el Hub principal
      (botón superior derecho 🚛).
    </div>""", unsafe_allow_html=True)



def _subtab_catalogo(catalogo):
    st.markdown('<div class="section-title">📚 Catálogo de Rutinas Preventivas</div>',
                unsafe_allow_html=True)
    st.caption(f"{len(catalogo)} rutinas parametrizadas con periodicidad, repuestos y costos estándar.")

    cat_data = []
    for r in catalogo:
        c = _calcular_costo_rutina(r)
        cat_data.append({
            "ID":               r["id"],
            "Nombre":           r["nombre"],
            "Sistema":          r["sistema"],
            "Periodicidad km":  f"{r['periodicidad_km']:,}".replace(",", "."),
            "Periodicidad días": r["periodicidad_dias"],
            "Duración (h)":     r["duracion_horas"],
            "Repuestos":        len(r["repuestos"]),
            "Mano obra":        _fmt_moneda(r["mano_obra"]),
            "Costo total est.": _fmt_moneda(c["total"]),
        })
    st.dataframe(pd.DataFrame(cat_data), use_container_width=True, hide_index=True)
    st.caption("💡 El catálogo se edita en el archivo `catalogo_rutinas.json` (edición visual en próxima versión).")


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

    tab_plan, tab_admin = st.tabs([
        "📅 Planificación",
        "🛠 Flota & Catálogo",
    ])

    with tab_plan:
        _tab_planificacion(flota, catalogo)
    with tab_admin:
        _tab_flota_catalogo(flota, catalogo)

    # ── JavaScript fallback: aplica estilos directamente al botón siguiente
    # del marcador, garantizando compatibilidad con cualquier versión de Streamlit
    st.markdown("""
    <script>
    (function() {
      const colorMap = {
        'marker-vencida':  {bg: 'rgba(248,81,73,.22)',  border: 'rgba(248,81,73,.6)',  left: '#F85149', color: '#FFCFCB'},
        'marker-critico':  {bg: 'rgba(255,107,0,.22)',  border: 'rgba(255,107,0,.6)',  left: '#FF6B00', color: '#FFD8B8'},
        'marker-proxima':  {bg: 'rgba(210,153,34,.20)', border: 'rgba(210,153,34,.6)', left: '#D29922', color: '#F0DBA0'},
        'marker-nunca':    {bg: 'rgba(10,132,255,.20)', border: 'rgba(10,132,255,.6)', left: '#0A84FF', color: '#B8D9FF'},
        'marker-selected': {bg: 'rgba(124,77,255,.32)', border: '#7C4DFF',             left: '#7C4DFF', color: '#FFFFFF', special: true},
      };

      function styleButtons() {
        document.querySelectorAll('.routine-marker').forEach(marker => {
          // Determinar la clase de color
          let cls = null;
          for (const k of Object.keys(colorMap)) {
            if (marker.classList.contains(k)) { cls = k; break; }
          }
          if (!cls) return;

          // Buscar el botón siguiente subiendo al contenedor padre y luego buscando el siguiente hermano
          let container = marker.closest('[data-testid="stElementContainer"]')
                       || marker.closest('.element-container')
                       || marker.parentElement;
          if (!container) return;

          let next = container.nextElementSibling;
          if (!next) return;

          const btn = next.querySelector('button');
          if (!btn) return;

          const c = colorMap[cls];
          btn.style.background = c.bg;
          btn.style.color = c.color;
          if (cls === 'marker-selected') {
            btn.style.border = '2px solid ' + c.border;
            btn.style.boxShadow = '0 0 18px rgba(124,77,255,.5)';
            btn.style.fontWeight = '700';
          } else {
            btn.style.border = '1px solid ' + c.border;
            btn.style.borderLeft = '5px solid ' + c.left;
            btn.style.fontWeight = '600';
          }
        });
      }

      // Ejecutar al cargar y luego periódicamente para capturar reruns de Streamlit
      styleButtons();
      const observer = new MutationObserver(() => { styleButtons(); });
      observer.observe(document.body, {childList: true, subtree: true});
      setInterval(styleButtons, 500);  // Fallback de seguridad
    })();
    </script>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        st.set_page_config(page_title="Mantenimiento Preventivo",
                           page_icon="📅", layout="wide",
                           initial_sidebar_state="collapsed")
    except Exception:
        pass
    run()
