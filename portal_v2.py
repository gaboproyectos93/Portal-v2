import streamlit as st
import pandas as pd
import io
import os
import time 
from fpdf import FPDF
from datetime import datetime
import re
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# ==========================================
st.set_page_config(page_title="ERP C.H. Automotriz", layout="wide")

COLOR_PRIMARIO = "#0A2540"
RUT_EMPRESA = "13.961.700-2" 
DIRECCION = "Francisco Pizarro 495, Padre las Casas"
EMAIL_SISTEMA = "c.h.servicioautomotriz@gmail.com"

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Error en enlace Supabase: {e}")
    supabase = None

st.markdown(f"""
<style>
    .stTabs [aria-selected='true'] {{ background-color: {COLOR_PRIMARIO} !important; color: white !important; font-weight: bold; border-radius: 4px; }}
    .stButton > button[kind='primary'] {{ background-color: {COLOR_PRIMARIO} !important; color: white !important; font-weight: bold; width: 100%; }}
    .card-requerido {{ background-color: #ffe6e6; padding: 15px; border-left: 5px solid #ff4d4d; border-radius: 4px; margin-bottom: 10px; }}
    .card-generado {{ background-color: #fff9e6; padding: 15px; border-left: 5px solid #ffcc00; border-radius: 4px; margin-bottom: 10px; }}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. GENERADOR DE PDF OFICIAL (C.H. AUTOMOTRIZ)
# ==========================================
def encontrar_imagen(n):
    for ext in ['.jpg', '.png', '.jpeg']:
        if os.path.exists(n + ext): return n + ext
    return None

def format_clp(v): 
    try: return f"${float(v):,.0f}".replace(",", ".")
    except: return "$0"

class PDF(FPDF):
    def __init__(self, correlativo="", official=False): 
        super().__init__()
        self.correlativo = correlativo
        self.is_official = official
        
    def header(self):
        logo = encontrar_imagen("logo_christian")
        if logo: self.image(logo, x=10, y=10, w=70) 
        self.set_xy(130, 10)
        self.set_text_color(220, 0, 0)
        self.set_draw_color(220, 0, 0)
        self.set_line_width(0.4)
        self.set_font('Arial', 'B', 16)
        self.cell(70, 10, "COTIZACIÓN" if self.is_official else "PRESUPUESTO", 'LTR', 1, 'C') 
        self.set_x(130)
        self.set_font('Arial', 'B', 14)
        self.cell(70, 10, f"N° {self.correlativo}", 'LBR', 1, 'C')
        self.set_text_color(0, 0, 0)
        self.ln(15)
        
    def footer(self):
        self.set_y(-20)
        self.set_font('Arial', 'I', 8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        self.cell(0, 4, f"Christian Alejandro Herrera Mardones | RUT: {RUT_EMPRESA} | {DIRECCION}", 0, 1, 'C')

def generar_pdf_exacto(patente, marca, modelo, cliente_nombre, cliente_rut, items, total_neto, is_official, estado_trabajo, usuario_final_txt, observaciones, correlativo):
    pdf = PDF(correlativo=correlativo, official=is_official)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=30) 
    
    patente_str = str(patente).upper() if patente else "SIN PATENTE"
    marca_str = str(marca).upper() if marca and marca != "--- Seleccione Marca ---" else "N/A"
    modelo_str = str(modelo).upper() if modelo and modelo != "---" else "N/A"

    def fila_dinamica(lbl1, val1, lbl2, val2, is_last=False):
        start_y = pdf.get_y()
        pdf.set_font('Arial', 'B', 9)
        pdf.set_xy(10, start_y)
        pdf.cell(25, 6, lbl1, 0, 0, 'L')
        pdf.set_font('Arial', '', 9)
        pdf.set_xy(35, start_y)
        pdf.multi_cell(70, 6, f": {val1}", 0, 'L')
        y_left = pdf.get_y()
        
        if lbl2: 
            pdf.set_font('Arial', 'B', 9)
            pdf.set_xy(105, start_y)
            pdf.cell(30, 6, lbl2, 0, 0, 'L')
            pdf.set_font('Arial', '', 9)
            pdf.set_xy(135, start_y)
            pdf.multi_cell(65, 6, f": {val2}", 0, 'L')
            y_right = pdf.get_y()
            
        my = max(y_left, pdf.get_y(), start_y + 6)
        pdf.line(10, start_y, 10, my)
        pdf.line(200, start_y, 200, my)
        if is_last: pdf.line(10, my, 200, my)
        pdf.set_xy(10, my)
        
    pdf.set_y(45)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(10, 37, 64)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(190, 6, "  DATOS DEL CLIENTE", 1, 1, 'L', 1)
    pdf.set_text_color(0, 0, 0)
    
    fila_dinamica(" Señor(es)", str(cliente_nombre).upper(), " Fecha Emisión", datetime.now().strftime('%d/%m/%Y'))
    fila_dinamica(" RUT", str(cliente_rut).upper(), " Usuario Final", str(usuario_final_txt).upper(), is_last=True)
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(10, 37, 64)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(190, 6, "  DATOS DEL VEHÍCULO / TRABAJO", 1, 1, 'L', 1)
    pdf.set_text_color(0, 0, 0)
    
    fila_dinamica(" Marca", marca_str, " Patente", patente_str)
    fila_dinamica(" Modelo", modelo_str, " Estado", str(estado_trabajo).upper(), is_last=True)
    pdf.ln(6)
    
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(10, 37, 64)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(115, 7, "Descripción", 1, 0, 'C', 1)
    pdf.cell(15, 7, "Cant.", 1, 0, 'C', 1)
    pdf.cell(30, 7, "Unitario", 1, 0, 'C', 1)
    pdf.cell(30, 7, "Total", 1, 1, 'C', 1)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 9)
    
    for i in items:
        x, y = pdf.get_x(), pdf.get_y()
        pdf.multi_cell(115, 6, str(i['Descripción']).upper(), 1, 'L')
        h = pdf.get_y() - y
        pdf.set_xy(x + 115, y)
        pdf.cell(15, h, str(i['Cantidad']), 1, 0, 'C')
        pdf.cell(30, h, format_clp(i['Unitario_Costo']), 1, 0, 'R')
        pdf.cell(30, h, format_clp(i['Total_Costo']), 1, 1, 'R')
        pdf.set_xy(x, y + h)
        
    pdf.ln(5)
    iv = total_neto * 0.19
    br = total_neto + iv
    
    pdf.set_x(140)
    pdf.cell(30, 6, "SUB TOTAL", 1, 0, 'L')
    pdf.cell(30, 6, format_clp(total_neto), 1, 1, 'R')
    pdf.set_x(140)
    pdf.cell(30, 6, "I.V.A. (19%)", 1, 0, 'L')
    pdf.cell(30, 6, format_clp(iv), 1, 1, 'R')
    
    pdf.set_x(140)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(10, 37, 64)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(30, 8, "TOTAL", 1, 0, 'L', 1)
    pdf.cell(30, 8, format_clp(br), 1, 1, 'R', 1)
    
    if observaciones: 
        pdf.ln(8)
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(0, 6, "OBSERVACIONES:", 0, 1)
        pdf.set_font('Arial', '', 9)
        pdf.multi_cell(0, 5, str(observaciones), 0, 'L')
        
    pdf.ln(15)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, f"Padre las Casas, {datetime.now().strftime('%d-%m-%Y')}", 0, 1, 'C')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 5, "Christian Alejandro Herrera Mardones", 0, 1, 'C')
    
    res = pdf.output(dest='S')
    return res.encode('latin-1') if isinstance(res, str) else bytes(res)

# ==========================================
# 3. INTERACCIÓN CON CONECTORES (SUPABASE)
# ==========================================
@st.cache_data(ttl=86400)
def cargar_catalogo_vehiculos():
    base_def = {"--- Seleccione Marca ---": ["---"]}
    if not supabase: return base_def
    try:
        res = supabase.table("base_vehiculos").select("marca, modelo").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            catalogo = {"--- Seleccione Marca ---": ["---"]}
            for marca, grupo in df.groupby("marca"):
                catalogo[str(marca)] = sorted(grupo["modelo"].dropna().unique().tolist())
            return catalogo
    except: pass
    return base_def

CATALOGO = cargar_catalogo_vehiculos()

def subir_pdf_a_storage(nombre_archivo, pdf_bytes):
    try:
        supabase.storage.from_("pdf_cotizaciones").upload(path=nombre_archivo, file=pdf_bytes, file_options={"content-type": "application/pdf"})
        return supabase.storage.from_("pdf_cotizaciones").get_public_url(nombre_archivo)
    except: return None

def registrar_solicitud_gabo(patente, cliente, origen, descripcion):
    try:
        if patente:
            supabase.table("directorio_vehiculos").upsert({"patente": patente, "nombre_contacto": cliente, "origen_cliente": origen}).execute()
        supabase.table("historial_trabajos").insert({
            "patente": patente if patente else None, "nombre_cliente_manual": cliente,
            "origen_trabajo": origen, "descripcion_requerimiento": descripcion,
            "estado": "Requerido", "creado_por": "Gabo"
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error DB: {e}")
        return False

def extraer_historial_completo():
    try:
        res = supabase.table("historial_trabajos").select("*").order("id_cotizacion", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: return pd.DataFrame()

# ==========================================
# 4. SISTEMA DE LOGIN Y CONTROL
# ==========================================
if 'usuario' not in st.session_state: st.session_state.usuario = None

if st.session_state.usuario is None:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write("")
        st.write("")
        st.title("🔐 ERP C.H. Automotriz")
        user_type = st.selectbox("Selecciona tu Perfil", ["--- Seleccione ---", "Gabriel Poblete (Planificación)", "Christian Herrera (Taller)"])
        password = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar", type="primary"):
            if user_type == "Gabriel Poblete (Planificación)" and password == "gabo2026":
                st.session_state.usuario = "Gabo"
                st.rerun()
            elif user_type == "Christian Herrera (Taller)" and password == "cristian2026":
                st.session_state.usuario = "Cristian"
                st.session_state.vista_taller = "Bandeja"
                st.session_state.paso_actual = 1
                st.rerun()
            else: st.error("Credenciales Incorrectas.")
    st.stop()

with st.sidebar:
    st.markdown(f"👤 **{st.session_state.usuario}**")
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# ==========================================
# 5. VISTA PLANIFICACIÓN (GABO)
# ==========================================
if st.session_state.usuario == "Gabo":
    st.title("🎛️ Planificación de Taller")
    
    with st.expander("➕ Solicitar Nueva Cotización", expanded=True):
        c1, c2, c3 = st.columns([1.5, 2, 1.5])
        pat = c1.text_input("Patente (Opcional)").upper()
        cli = c2.text_input("Cliente / Institución")
        origen = c3.selectbox("Canal", ["Kaufmann", "Propio Cristian"])
        desc = st.text_area("Instrucciones para Cristian")
        
        if st.button("Enviar Orden al Taller", type="primary"):
            if cli and desc:
                if registrar_solicitud_gabo(pat, cli, origen, desc):
                    st.success("🚀 Solicitud enviada exitosamente a la bandeja de Cristian.")
                    time.sleep(1.5)
                    st.rerun()
            else: st.warning("Rellena el cliente y las instrucciones.")

    st.markdown("---")
    st.subheader("📊 Monitoreo Global")
    df_global = extraer_historial_completo()
    if not df_global.empty:
        col_deseadas = ['id_cotizacion', 'patente', 'nombre_cliente_manual', 'origen_trabajo', 'estado', 'total_clp', 'pdf_url']
        df_global = df_global.reindex(columns=col_deseadas)
        st.dataframe(df_global, use_container_width=True)

# ==========================================
# 6. VISTA TALLER (CRISTIAN) - INTEGRACIÓN MAESTRA
# ==========================================
elif st.session_state.usuario == "Cristian":
    
    # Navegación Lateral Exclusiva para Cristian
    with st.sidebar:
        st.markdown("---")
        if st.button("📥 Bandeja de Requerimientos"):
            st.session_state.vista_taller = "Bandeja"
            st.rerun()
        if st.button("🚀 Nueva Cotización Libre"):
            st.session_state.vista_taller = "Cotizador"
            st.session_state.paso_actual = 1
            st.session_state.solicitud_activa = None # Limpiamos cualquier rastro de Gabo
            st.session_state.patente_confirmada = ""
            st.rerun()
        if st.button("🗂️ Historial General"):
            st.session_state.vista_taller = "Historial"
            st.rerun()

    # ----------------------------------------
    # MÓDULO A: BANDEJA DE ENTRADA (KANBAN)
    # ----------------------------------------
    if st.session_state.vista_taller == "Bandeja":
        st.title("📥 Requerimientos Pendientes")
        df_todo = extraer_historial_completo()
        if not df_todo.empty and 'estado' in df_todo.columns:
            df_req = df_todo[df_todo['estado'] == 'Requerido']
            if not df_req.empty:
                for idx, fila in df_req.iterrows():
                    st.markdown(f"""
                    <div class="card-requerido">
                        <h4>🚗 Vehículo: {fila['patente'] if pd.notna(fila['patente']) and fila['patente'] else 'S/P'} | Cliente: {fila['nombre_cliente_manual']}</h4>
                        <p><strong>Instrucciones:</strong> {fila['descripcion_requerimiento']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"⚙️ Atender Solicitud N° {fila['id_cotizacion']}", key=f"btn_{fila['id_cotizacion']}", type="primary"):
                        # Se inyectan los datos de Gabo en la memoria del cotizador y se salta al Paso 2
                        st.session_state.solicitud_activa = fila['id_cotizacion']
                        st.session_state.patente_confirmada = fila['patente'] if pd.notna(fila['patente']) else ""
                        st.session_state.cliente_predefinido = fila['nombre_cliente_manual']
                        st.session_state.origen_predefinido = fila['origen_trabajo']
                        st.session_state.vista_taller = "Cotizador"
                        st.session_state.paso_actual = 2
                        st.rerun()
            else: st.success("¡Al día! No hay requerimientos pendientes.")
        else: st.info("Historial vacío.")

    # ----------------------------------------
    # MÓDULO B: EL COTIZADOR ROBUSTO (FASE 1)
    # ----------------------------------------
    elif st.session_state.vista_taller == "Cotizador":
        
        # PANTALLA 1: Búsqueda (Solo aparece si Cristian hace una cotización libre)
        if st.session_state.paso_actual == 1:
            st.title("Cotizador Automotriz Libre")
            pat_texto = st.text_input("Ingresa Patente (Opcional)").upper()
            if st.button("🚀 INICIAR", type="primary", use_container_width=True):
                st.session_state.patente_confirmada = pat_texto
                st.session_state.cliente_predefinido = ""
                st.session_state.paso_actual = 2
                st.rerun()

        # PANTALLA 2: Formularios, Calculadora y PDF
        elif st.session_state.paso_actual == 2:
            p_in = st.session_state.get('patente_confirmada', '')
            sol_id = st.session_state.get('solicitud_activa')
            
            st.markdown(f"### 📋 Cotización en curso: **{p_in if p_in else 'SIN PATENTE'}**")
            if sol_id: st.info(f"Asociado al requerimiento N° {sol_id} de Gabo")
            
            # Formulario de Cliente
            cf1, cf2, cf3 = st.columns([2, 1, 2])
            cli_fac = cf1.text_input("Nombre Cliente / Institución", value=st.session_state.get('cliente_predefinido', ''))
            rut_fac = cf2.text_input("RUT (Opcional)")
            us_final = cf3.text_input("Usuario Final", value=cli_fac)
            
            # Vehículo y Origen
            cv1, cv2, cv3 = st.columns([1.5, 1.5, 1])
            marcas_disp = list(CATALOGO.keys())
            marca_sel = cv1.selectbox("Marca", marcas_disp)
            modelos_disp = CATALOGO[marca_sel] if marca_sel and marca_sel != "--- Seleccione Marca ---" else ["---"]
            modelo_sel = cv2.selectbox("Modelo", modelos_disp)
            
            opciones_origen = ["Kaufmann", "Propio Cristian"]
            idx_origen = opciones_origen.index(st.session_state.get('origen_predefinido', 'Propio Cristian')) if 'origen_predefinido' in st.session_state else 1
            origen_sel = cv3.selectbox("Canal", opciones_origen, index=idx_origen)
            
            st.markdown("---")
            
            # Calculadora robusta
            sel_final = []
            tabs = st.tabs(["➕ Ingreso Manual", "🛒 Repuestos"])
            with tabs[0]:
                cc1, cc2, cc3 = st.columns([5.5, 1.5, 2], vertical_alignment="center")
                dm = cc1.text_input("Descripción del Trabajo")
                qm = cc2.number_input("Cnt", min_value=1, value=1)
                pm = cc3.number_input("Precio Unitario ($)", min_value=0, step=5000)
                if st.button("Agregar Ítem"): 
                    if dm and pm > 0:
                        if 'lista_particular' not in st.session_state: st.session_state.lista_particular = []
                        st.session_state.lista_particular.append({"Descripción": dm, "Cantidad": qm, "Unitario_Costo": pm, "Total_Costo": pm * qm})
                        st.rerun()
                        
                if 'lista_particular' in st.session_state:
                    for idx, i in enumerate(st.session_state.lista_particular):
                        ca, cb = st.columns([5, 1], vertical_alignment="center")
                        ca.markdown(f"• {i['Cantidad']}x {i['Descripción']} - **{format_clp(i['Total_Costo'])}**")
                        if cb.button("🗑️", key=f"dp_{idx}"): 
                            st.session_state.lista_particular.pop(idx)
                            st.rerun()
                    sel_final = st.session_state.lista_particular
                    
            with tabs[1]: 
                st.subheader("🛒 Calculadora de Repuestos")
                cx1, cx2 = st.columns([3, 1])
                d_rep = cx1.text_input("Descripción Repuesto", key="r_desc")
                q_rep = cx2.number_input("Cant", 1, key="r_cant")
                cx3, cx4, cx5 = st.columns(3)
                c_rep = cx3.number_input("Costo Repuesto ($)", 0, step=1000, key="r_crep")
                c_env = cx4.number_input("Costo Envío ($)", 0, step=1000, key="r_cenv")
                m_pct = cx5.number_input("Margen (%)", 0, 100, 30, key="r_marg")
                p_final = int((c_rep + c_env) * (1 + m_pct / 100.0))
                st.markdown(f"#### Precio Final: **{format_clp(p_final)}**")
                
                if st.button("➕ Añadir Repuesto"):
                    if d_rep and p_final > 0:
                        if 'lista_repuestos' not in st.session_state: st.session_state.lista_repuestos = []
                        st.session_state.lista_repuestos.append({"Descripción": d_rep, "Cantidad": q_rep, "Unitario_Costo": float(p_final), "Total_Costo": float(p_final * q_rep)})
                        st.rerun()
                        
                if 'lista_repuestos' in st.session_state:
                    for idx, i in enumerate(st.session_state.lista_repuestos):
                        ca, cb = st.columns([5, 1], vertical_alignment="center")
                        ca.text(f"• {i['Cantidad']}x {i['Descripción']} - {format_clp(i['Total_Costo'])}")
                        if cb.button("🗑️", key=f"dr_{idx}"): 
                            st.session_state.lista_repuestos.pop(idx)
                            st.rerun()
                            
            if 'lista_repuestos' in st.session_state: sel_final.extend(st.session_state.lista_repuestos)
                
            if sel_final:
                st.markdown("---")
                tn = sum(x['Total_Costo'] for x in sel_final)
                iv = tn * 0.19
                tf = tn + iv
                
                k1, k2, k3 = st.columns(3)
                k1.metric("SUB TOTAL", format_clp(tn))
                k2.metric("I.V.A.", format_clp(iv))
                k3.metric("TOTAL A PAGAR", format_clp(tf))
                
                obs = st.text_area("Observaciones:")
                est = st.radio("Estado:", ("En Espera de Aprobación", "Trabajo Realizado"))
                
                if 'presupuesto_generado' not in st.session_state:
                    if st.button("💾 GENERAR PDF Y GUARDAR", type="primary", use_container_width=True):
                        with st.spinner("Conectando con Servidor..."):
                            try:
                                # Lógica Maestra: ¿Actualizar Requerimiento o Crear Nuevo?
                                if sol_id:
                                    corr_id = str(sol_id)
                                    pdf_b = generar_pdf_exacto(p_in, marca_sel, modelo_sel, cli_fac, rut_fac, sel_final, tn, False, est, us_final, obs, corr_id)
                                    n_pdf = f"Presupuesto_{corr_id}.pdf"
                                    url_doc = subir_pdf_a_storage(n_pdf, pdf_b)
                                    
                                    supabase.table("historial_trabajos").update({"estado": "Generado", "total_clp": tf, "pdf_url": url_doc, "origen_trabajo": origen_sel}).eq("id_cotizacion", sol_id).execute()
                                else:
                                    # Insertar primero para obtener el correlativo automático
                                    res = supabase.table("historial_trabajos").insert({"patente": p_in if p_in else None, "nombre_cliente_manual": cli_fac, "origen_trabajo": origen_sel, "estado": "Generado", "total_clp": tf, "creado_por": "Cristian"}).execute()
                                    corr_id = str(res.data[0]['id_cotizacion'])
                                    
                                    pdf_b = generar_pdf_exacto(p_in, marca_sel, modelo_sel, cli_fac, rut_fac, sel_final, tn, False, est, us_final, obs, corr_id)
                                    n_pdf = f"Presupuesto_{corr_id}.pdf"
                                    url_doc = subir_pdf_a_storage(n_pdf, pdf_b)
                                    
                                    supabase.table("historial_trabajos").update({"pdf_url": url_doc}).eq("id_cotizacion", corr_id).execute()
                                
                                st.session_state['presupuesto_generado'] = {'pdf': pdf_b, 'nombre': n_pdf, 'url': url_doc}
                                st.rerun()
                            except Exception as e_gen:
                                st.error(f"Error al generar: {e_gen}")
                else:
                    d = st.session_state['presupuesto_generado']
                    st.success("✅ Documento Oficial C.H. Automotriz guardado en la nube.")
                    st.download_button("📥 DESCARGAR PDF", d['pdf'], d['nombre'], "application/pdf", type="primary")
                    
                    if st.button("🔄 Volver al Inicio / Limpiar"):
                        for k in ['lista_particular', 'lista_repuestos', 'presupuesto_generado', 'solicitud_activa']:
                            if k in st.session_state: del st.session_state[k]
                        st.session_state.paso_actual = 1
                        st.session_state.vista_taller = "Bandeja"
                        st.rerun()

    # ----------------------------------------
    # MÓDULO C: HISTORIAL HISTÓRICO
    # ----------------------------------------
    elif st.session_state.vista_taller == "Historial":
        st.title("🗃️ Registro General")
        df_todo = extraer_historial_completo()
        if not df_todo.empty:
            lupa = st.text_input("🔍 Digita una Patente o Cliente...").upper()
            if lupa: df_todo = df_todo[df_todo['patente'].str.contains(lupa, na=False) | df_todo['nombre_cliente_manual'].str.contains(lupa, na=False, case=False)]
            
            sec_generadas, sec_enviadas, sec_terminadas = st.tabs(["🟡 Solo Generadas", "🔵 Enviadas al Cliente", "🟢/⚫ Aprobadas/Terminadas"])
            
            with sec_generadas:
                for idx, r in df_todo[df_todo['estado'] == 'Generado'].iterrows():
                    ca, cb, cc = st.columns([3, 1.5, 1])
                    ca.write(f"📄 N° {r['id_cotizacion']} | Patente: {r['patente']} | Cliente: {r['nombre_cliente_manual']} | Total: ${r['total_clp']:,.0f}")
                    if pd.notna(r.get('pdf_url')): cb.markdown(f"[👁️ Ver PDF]({r['pdf_url']})")
                    if cc.button("✉️ Marcar Enviado", key=f"e_{r['id_cotizacion']}"):
                        supabase.table("historial_trabajos").update({"estado": "Enviado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                        st.rerun()
            with sec_enviadas:
                for idx, r in df_todo[df_todo['estado'] == 'Enviado'].iterrows():
                    ca, cb, cc = st.columns([3, 1.5, 1])
                    ca.write(f"🔵 N° {r['id_cotizacion']} | Patente: {r['patente']} | Cliente: {r['nombre_cliente_manual']} | Total: ${r['total_clp']:,.0f}")
                    if pd.notna(r.get('pdf_url')): cb.markdown(f"[📥 Descargar PDF]({r['pdf_url']})")
                    if cc.button("🟢 Aprobar", key=f"a_{r['id_cotizacion']}"):
                        supabase.table("historial_trabajos").update({"estado": "Aprobado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                        st.rerun()
            with sec_terminadas:
                st.dataframe(df_todo[df_todo['estado'].isin(['Aprobado', 'Terminado'])][['id_cotizacion', 'patente', 'nombre_cliente_manual', 'estado', 'total_clp']], use_container_width=True)
