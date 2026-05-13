"""
reporte_fallas.py — v1.0
==========================
Módulo de reporte de fallas detectadas en operación.
Standalone : streamlit run reporte_fallas.py
Desde hub  : import reporte_fallas; reporte_fallas.run()

Alcance (según arquitectura consensuada):
-----------------------------------------
• SOLO mantenimientos correctivos (Correctivo Operación y Mayor)
• NO cubre preventivos — esos van en modulo_preventivo.py
• Flujo simplificado: el conductor reporta la falla → se genera OT-CO o OT-M
• Nuevo campo: criticidad de la intervención (Alta / Media / Baja)
• La hoja de vida es un reporte derivado en Analítica, no se edita aquí
"""
import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTES
# ═══════════════════════════════════════════════════════════════════
TIPOS_CORRECTIVO = {
    "C": "Correctivo Operación",
}

CRITICIDADES = {
    "Alta":  {"color": "#F85149", "desc": "Vehículo fuera de servicio inmediato · prioridad máxima"},
    "Media": {"color": "#D29922", "desc": "Puede terminar operación del día · reparar en turno"},
    "Baja":  {"color": "#3FB950", "desc": "Programar en próxima ventana de mantenimiento"},
}

SISTEMAS = [
    "Motor", "Frenos", "Direccion", "Suspension", "Llantas",
    "Refrigeracion", "Electrico", "Carroceria Externa", "Habitaculo",
    "Transmision",
]

FALLAS = {
    "Motor": [
        "Fuga de aceite visible (manchas en piso o bajo capo)",
        "Ruido anormal (golpeteo, traqueteo o zumbido)",
        "Sobrecalentamiento",
        "Humo excesivo por el escape (negro, azul o blanco)",
        "Pérdida de potencia al acelerar",
        "Consumo excesivo de aceite (nivel bajo frecuente)",
        "Motor no enciende o arranca con dificultad",
        "Ralentí inestable (vibra o se apaga en marcha mínima)",
        "Vehículo se apaga o deja de funcionar en marcha",
        "Correas rotas o con alto desgaste visible",
        "Mangueras rotas o con fugas (motor)",
        "Soportes de motor sueltos o con daño visible",
    ],
    "Frenos": [
        "Ruido al frenar (chirrido, raspado o golpe metálico)",
        "Pedal esponjoso, blando o con recorrido excesivo",
        "Vibración al frenar",
        "Desviación lateral al frenar",
        "Freno de parqueo no retiene el vehículo",
        "Fuga visible de líquido de frenos",
        "Pastillas o zapatas con desgaste visible",
        "Fuga de freno de aire (escape de aire audible)",
    ],
    "Direccion": [
        "Juego u holgura excesiva en el volante",
        "Dirección dura o muy pesada al maniobrar",
        "Ruido al girar el volante (crujido, chirrido o golpe)",
        "Vibración perceptible en el volante en movimiento",
        "Desviación o jalonamiento del vehículo hacia un lado",
        "Fuga visible de fluido de dirección",
    ],
    "Suspension": [
        "Ruido en suspensión al pasar por irregularidades",
        "Rebote excesivo de la carrocería tras obstáculos",
        "Inclinación visible del vehículo hacia un lado",
        "Resorte roto o deformado (visible sin desmontaje)",
        "Holgura o movimiento en ruedas al sacudirlas manualmente",
        "Desgaste desigual de llantas (visible en inspección)",
    ],
    "Llantas": [
        "Llanta pinchada o desinflada",
        "Desgaste irregular visible (liso en zonas específicas)",
        "Labrado por debajo del indicador de desgaste mínimo",
        "Daño visible en flanco (corte, deformación)",
        "Protuberancia (hernia) visible en llanta",
        "Vibración o desbalanceo perceptible al conducir",
    ],
    "Refrigeracion": [
        "Indicador de temperatura en zona roja / sobrecalentamiento",
        "Fuga visible de refrigerante (manchas líquido verde o rosado)",
        "Vapor o humo blanco desde el compartimento del motor",
        "Olor dulce a refrigerante al abrir capo o en cabina",
        "Nivel de refrigerante bajo al revisar depósito",
        "Daño visible en radiador (golpe, fuga o aletas aplastadas)",
        "Mangueras de refrigeración con rajaduras o fugas visibles",
    ],
    "Electrico": [
        "Sistema de arranque defectuoso o lento",
        "Batería descargada o sulfatada",
        "Testigo de batería o carga encendido en el tablero",
        "Olor a quemado o humo desde el sistema eléctrico",
        "Luces delanteras o traseras apagadas o con parpadeo",
        "Luces direccionales no funcionan o parpadeo anormal",
        "Testigo de alarma activo en tablero de instrumentos",
        "Bocina / pito sin funcionamiento",
    ],
    "Carroceria Externa": [
        "Golpe o abolladura visible",
        "Fisura o rotura en parabrisas o vidrios",
        "Espejo retrovisor roto, suelto o desajustado",
        "Plumillas deterioradas (rayaduras o no limpian bien)",
        "Óxido o corrosión visible en estructura o paneles",
        "Plataforma de movilidad reducida inoperante o dañada",
        "Puertas no abren o no cierran correctamente",
    ],
    "Habitaculo": [
        "Cinturón de seguridad no engancha, no retrae o está dañado",
        "Silletería rota, rasgada o con soporte deteriorado",
        "Pasamanos suelto, roto o con fijación débil",
        "Pito / bocina sin funcionamiento",
        "Equipo de carretera incompleto",
        "Aire acondicionado no enfría o no enciende",
        "Testigo o alarma activa visible en tablero de instrumentos",
    ],
    "Transmision": [
        "Fuga visible de aceite de transmisión",
        "Ruido anormal al cambiar marcha (crujido o chirrido)",
        "Embrague patina (motor acelera pero velocidad no aumenta)",
        "Dificultad notoria para ingresar o cambiar marchas",
        "Cambios de marcha bruscos o con golpe perceptible",
        "Vibración perceptible al conducir en marcha constante",
        "Imposibilidad de ingresar una o varias marchas",
    ],
}

PENDIENTES_DB = "ots_pendientes.json"

# Abreviaturas de sistemas para radicado OT
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
}


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
def _generar_ot(tipo, vehiculo, sistema):
    """
    Genera radicado con abreviatura de sistema para trazabilidad:
    • OT-CO-<SIST>-<VEH>-<YYMMDD>-<HHMM>  → Correctivo Operación
    """
    now = datetime.now()
    veh = vehiculo.strip().upper().replace(" ", "")[:6]
    sist = SIST_ABREV.get(sistema, "GEN")
    return f"OT-CO-{sist}-{veh}-{now.strftime('%y%m%d')}-{now.strftime('%H%M')}"


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


def _volver_al_hub():
    for k in ["fase_rf", "ot_actual_rf", "f1_data_rf"]:
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
:root{--primary:#FF6B00;--primary-dk:#CC5500;--bg:#0D1117;--surface:#161B22;--surface2:#21262D;
      --border:#30363D;--text:#E6EDF3;--muted:#8B949E;--green:#3FB950;--yellow:#D29922;
      --red:#F85149;--blue:#0A84FF;--radius:12px;}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;font-family:'Inter',sans-serif}
.app-header{background:linear-gradient(135deg,#0D1117,#1A0000,#0D1117);border-bottom:1px solid #3D0000;padding:1.3rem 2rem;margin:0 -1rem 2rem -1rem;display:flex;align-items:center;gap:1rem}
.app-header h1{font-family:'Exo 2',sans-serif;font-weight:800;font-size:1.5rem;color:var(--text);margin:0}
.app-header .sub{font-size:.78rem;color:var(--muted);margin:0}
.fase-badge{background:rgba(248,81,73,.15);color:#F85149;border:1px solid #F85149;padding:.25rem .9rem;border-radius:20px;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem;margin-bottom:1.2rem}
.card-title{font-family:'Exo 2',sans-serif;font-size:.95rem;font-weight:700;color:var(--primary);margin-bottom:1rem;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--border);padding-bottom:.6rem}
.ot-box{background:linear-gradient(135deg,#1A0D00,#21150A);border:1.5px solid var(--primary);border-radius:var(--radius);padding:1rem 1.5rem;margin:1rem 0;display:flex;align-items:center;gap:1rem}
.ot-label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em}
.ot-value{font-family:'Exo 2',sans-serif;font-size:1.3rem;font-weight:800;color:var(--primary)}
.ot-generated-big{background:linear-gradient(135deg,#1A1000,#0D1117);border:2px solid var(--primary);border-radius:14px;padding:1.4rem 1.8rem;margin:1.2rem 0;box-shadow:0 0 24px rgba(255,107,0,.25);text-align:center}
.ot-generated-label{font-size:.78rem;color:#8B949E;text-transform:uppercase;letter-spacing:.12em;font-weight:600}
.ot-generated-number{font-family:'Exo 2',sans-serif;font-size:1.8rem;font-weight:800;color:var(--primary);margin:.4rem 0;letter-spacing:.02em}
.success-screen{text-align:center;padding:2.5rem 2rem;background:linear-gradient(135deg,#1A0D00,#0D1117);border:1px solid var(--primary);border-radius:var(--radius);margin:1.5rem 0}
.success-screen h2{font-family:'Exo 2',sans-serif;font-size:1.8rem;color:var(--primary);margin:.4rem 0}
.crit-option{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.6rem 1rem;margin-bottom:.4rem;font-size:.85rem;color:var(--muted)}
.crit-high   {border-left:4px solid #F85149}
.crit-medium {border-left:4px solid #D29922}
.crit-low    {border-left:4px solid #3FB950}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input{background:var(--surface2)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:8px!important;font-family:'Inter',sans-serif!important}
[data-testid="stSelectbox"]>div>div{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:8px!important}
[data-testid="stRadio"]>div{gap:.4rem!important}
[data-testid="stRadio"] label{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.35rem .9rem!important;cursor:pointer;font-size:.85rem!important}
[data-testid="stRadio"] label:has(input:checked){border-color:var(--primary)!important;background:rgba(255,107,0,.1)!important}
[data-testid="stButton"] button{background:var(--primary)!important;color:white!important;border:none!important;border-radius:8px!important;font-family:'Exo 2',sans-serif!important;font-weight:700!important;font-size:.9rem!important;padding:.55rem 1.2rem!important;text-transform:uppercase!important;letter-spacing:.05em!important}
[data-testid="stButton"] button:hover{background:var(--primary-dk)!important;transform:translateY(-1px);box-shadow:0 4px 16px rgba(255,107,0,.3)!important}
[data-testid="stButton"] button:disabled{background:var(--surface2)!important;color:var(--muted)!important;transform:none!important;box-shadow:none!important}
.btn-green button{background:#2EA043!important}.btn-green button:hover{background:#3FB950!important}
.btn-blue button{background:#005FCC!important}.btn-blue button:hover{background:#0A84FF!important}
.btn-gray button{background:var(--surface2)!important;color:var(--muted)!important;border:1px solid var(--border)!important}
.btn-back button{background:var(--surface2)!important;color:var(--muted)!important;border:1px solid var(--border)!important;text-transform:none!important;font-size:.82rem!important;font-weight:500!important;padding:.4rem 1rem!important;letter-spacing:normal!important}
.btn-back button:hover{background:var(--border)!important;color:var(--text)!important;transform:none!important;box-shadow:none!important}
.info-banner{background:rgba(10,132,255,.05);border-left:3px solid #0A84FF;border-radius:6px;padding:.6rem 1rem;margin:0 0 1rem 0;font-size:.8rem;color:#8B949E}
#MainMenu,footer,header{visibility:hidden}.block-container{padding-top:0!important}
</style>"""


# ═══════════════════════════════════════════════════════════════════
#  ESTADO
# ═══════════════════════════════════════════════════════════════════
def _init_state():
    defaults = {
        "fase_rf":      "form",
        "ot_actual_rf": None,
        "f1_data_rf":   None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in ["fase_rf", "ot_actual_rf", "f1_data_rf"]:
        st.session_state.pop(k, None)
    st.session_state["fase_rf"] = "form"


def _render_back_button(key_suffix):
    if st.session_state.get("modulo") == "reporte_fallas":
        st.markdown('<div class="btn-back">', unsafe_allow_html=True)
        if st.button("← Volver al Hub", key=f"btn_back_rf_{key_suffix}"):
            _volver_al_hub()
        st.markdown('</div>', unsafe_allow_html=True)


def _header():
    st.markdown("""
    <div class="app-header">
      <div style="font-size:2rem">🚨</div>
      <div>
        <h1>Reporte de Fallas</h1>
        <p class="sub">Registro de fallas detectadas en operación — Mantenimiento Correctivo</p>
      </div>
      <div style="margin-left:auto"><span class="fase-badge">Correctivo</span></div>
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  run()
# ═══════════════════════════════════════════════════════════════════
def run():
    _init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    fase = st.session_state.get("fase_rf", "form")

    # ══════════════════════════════════════════════
    #  PANTALLA: CONFIRMACIÓN
    # ══════════════════════════════════════════════
    if fase == "confirmacion":
        _render_back_button("conf")
        _header()
        ot   = st.session_state.get("ot_actual_rf", "")
        f1d  = st.session_state.get("f1_data_rf", {}) or {}
        crit = f1d.get("Criticidad", "Media")
        crit_color = CRITICIDADES[crit]["color"]

        st.markdown(f"""<div class="ot-generated-big">
          <div class="ot-generated-label">✅ Se ha generado la OT</div>
          <div class="ot-generated-number">{ot}</div>
          <div style="color:#8B949E;font-size:.85rem">Guarde este radicado — será necesario para el cierre técnico.</div>
        </div>""", unsafe_allow_html=True)

        st.markdown(f"""<div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:1rem 1.2rem;margin-bottom:1.5rem">
          <div style="font-size:.78rem;color:#8B949E;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.4rem">Resumen del Reporte</div>
          <div style="font-size:.9rem;line-height:1.7">
            <strong>Vehículo:</strong> {f1d.get('Numero_Interno', '')} &nbsp;·&nbsp;
            <strong>Conductor:</strong> {f1d.get('Conductor', '')}<br>
            <strong>Tipo:</strong> {TIPOS_CORRECTIVO.get(f1d.get('Tipo_Mantenimiento', 'C'), '')} &nbsp;·&nbsp;
            <strong>Criticidad:</strong> <span style="color:{crit_color};font-weight:600">{crit}</span><br>
            <strong>Sistema:</strong> {f1d.get('Sistema', '')}<br>
            <strong>Falla:</strong> <span style="color:#F85149">{f1d.get('Modo_Falla', '')}</span>
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("### ¿Qué desea hacer ahora?")
        st.markdown("<br>", unsafe_allow_html=True)
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown('<div class="btn-blue">', unsafe_allow_html=True)
            if st.button("1  Ir al cierre de\nesta OT", use_container_width=True, key="rf_go_close"):
                st.session_state["modulo"] = "cierre_ot"
                st.session_state["fase"] = "2"
                st.session_state["ot_actual"] = ot
                st.session_state["intervenciones"] = [{"desc": "", "cantidad": 1, "costo": 0.0}]
                try:
                    st.query_params["mod"] = "cierre_ot"
                except Exception:
                    pass
                _reset()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption("Para el mecánico que va a intervenir.")

        with col_b:
            st.markdown('<div class="btn-green">', unsafe_allow_html=True)
            if st.button("2  Reportar otra\nfalla", use_container_width=True, key="rf_nuevo"):
                _reset()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption("Registrar la falla de otro vehículo.")

        with col_c:
            st.markdown('<div class="btn-gray">', unsafe_allow_html=True)
            if st.button("3  Volver al Hub", use_container_width=True, key="rf_hub"):
                _volver_al_hub()
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption("Regresar al panel principal.")
        return

    # ══════════════════════════════════════════════
    #  FORMULARIO — REPORTE DE FALLA
    # ══════════════════════════════════════════════
    _render_back_button("form")
    _header()
    st.markdown(f"<p style='color:#8B949E;font-size:.8rem;margin-bottom:1.2rem'>📅 {datetime.now().strftime('%A, %d de %B de %Y — %H:%M')}</p>",
                unsafe_allow_html=True)

    st.markdown("""<div class="info-banner">
      ℹ️ Este módulo es exclusivo para reportar fallas <strong style="color:#E6EDF3">detectadas en operación</strong>
      (mantenimientos correctivos). Los mantenimientos preventivos se gestionan en el módulo <strong style="color:#E6EDF3">Mantenimiento Preventivo</strong>.
    </div>""", unsafe_allow_html=True)

    # ── Identificación ──
    st.markdown('<div class="card"><div class="card-title">🚛 Identificación del Vehículo</div>',
                unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        num_interno = st.text_input("Número interno *", placeholder="Ej: 0042", key="rf_num")
    with col2:
        conductor = st.text_input("Nombre del conductor *",
                                   placeholder="Ej: Pedro Gómez", key="rf_cond")
    with col3:
        km_f1 = st.number_input("Kilometraje al reportar *",
                                  min_value=0, step=100, value=0, key="rf_km", format="%d")
        if km_f1 > 0:
            st.markdown(f"<div style='font-size:.85rem;color:var(--primary);font-weight:600;margin-top:-.4rem'>"
                        f"{km_f1:,} km".replace(",", ".") + "</div>", unsafe_allow_html=True)

    col4, col5 = st.columns(2)
    with col4:
        fecha_inac = st.date_input("Fecha inicio inactividad *",
                                     value=datetime.now().date(), key="rf_fecha")
    with col5:
        hora_inac = st.time_input("Hora inicio inactividad *",
                                    value=datetime.now().time(), key="rf_hora")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Criticidad ──
    st.markdown('<div class="card"><div class="card-title">⚠️ Clasificación de la Falla</div>',
                unsafe_allow_html=True)
    st.markdown("<div style='font-size:.85rem;font-weight:600;color:#8B949E;margin-bottom:.4rem'>Criticidad *</div>",
                unsafe_allow_html=True)
    crit_sel = st.radio("_crit_rf", options=list(CRITICIDADES.keys()),
                         key="rf_crit", label_visibility="collapsed", horizontal=True)

    # Tipo de correctivo fijo: Operación (los Mayores se gestionan por separado)
    tipo_sel = "C"

    # Descripción de la criticidad elegida
    crit_desc = CRITICIDADES[crit_sel]["desc"]
    crit_color = CRITICIDADES[crit_sel]["color"]
    st.markdown(f"""<div style="background:rgba(0,0,0,.2);border-left:3px solid {crit_color};border-radius:6px;padding:.5rem 1rem;margin-top:.5rem;font-size:.8rem">
      <strong style="color:{crit_color}">{crit_sel}:</strong>
      <span style="color:#8B949E">{crit_desc}</span>
    </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Sistema y modo de falla ──
    st.markdown('<div class="card"><div class="card-title">⚙️ Sistema y Modo de Falla</div>',
                unsafe_allow_html=True)
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        sistema_sel = st.selectbox("Sistema afectado *", options=SISTEMAS, key="rf_sistema")
    with col_s2:
        fallas_disp = FALLAS.get(sistema_sel, ["Otra falla"])
        falla_sel = st.selectbox("Modo de falla observado *", options=fallas_disp, key="rf_falla")

    # Observación libre opcional
    obs_extra = st.text_area("Observaciones adicionales (opcional)",
                              placeholder="Detalles complementarios del evento, condiciones en que ocurrió, etc.",
                              max_chars=300, key="rf_obs")

    # Preview del radicado
    if num_interno.strip() and sistema_sel:
        ot_prev = _generar_ot(tipo_sel, num_interno.strip(), sistema_sel)
        st.markdown(f"""<div class="ot-box">
          <div style="font-size:1.5rem">🔖</div>
          <div><div class="ot-label">Radicado OT (preview — se genera al guardar)</div>
          <div class="ot-value">{ot_prev}</div></div>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Validación ──
    f1_ok = bool(num_interno.strip()) and bool(conductor.strip()) and km_f1 > 0
    falt = []
    if not num_interno.strip(): falt.append("**Número interno**")
    if not conductor.strip():   falt.append("**Conductor**")
    if km_f1 == 0:              falt.append("**Kilometraje**")
    if falt:
        st.warning(f"Campos obligatorios: {' · '.join(falt)}")

    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        guardar = st.button("📋 REGISTRAR FALLA Y GENERAR OT",
                             disabled=not f1_ok, use_container_width=True, key="rf_save")
    with col_b2:
        if st.button("🔄 Limpiar", use_container_width=True, key="rf_clear"):
            _reset()
            st.rerun()

    if guardar and f1_ok:
        ot_num = _generar_ot(tipo_sel, num_interno.strip(), sistema_sel)
        f1_data = {
            "Fecha_Inicio_Inactividad": f"{fecha_inac} {hora_inac}",
            "Fecha_Registro_F1":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "OT":                       ot_num,
            "Numero_Interno":           num_interno.strip().upper(),
            "Conductor":                conductor.strip(),
            "Tipo_Mantenimiento":       tipo_sel,
            "Criticidad":               crit_sel,
            "Kilometraje":              km_f1,
            "Sistema":                  sistema_sel,
            "Modo_Falla":               falla_sel,
            "Observaciones_Reporte":    obs_extra.strip(),
            "Estado_OT":                "P",
            "Origen":                   "Reporte_Falla_Operacion",
        }
        _registrar_ot_pendiente(ot_num, f1_data)
        st.session_state["ot_actual_rf"] = ot_num
        st.session_state["f1_data_rf"]   = f1_data
        st.session_state["fase_rf"]      = "confirmacion"
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        st.set_page_config(page_title="Reporte de Fallas",
                           page_icon="🚨", layout="wide",
                           initial_sidebar_state="collapsed")
    except Exception:
        pass
    run()
