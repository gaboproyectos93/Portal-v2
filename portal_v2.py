import streamlit as st
import pandas as pd
import io
import os
import time 
from fpdf import FPDF
from datetime import datetime
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
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DE MATRICES DESDE SUPABASE
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

@st.cache_data(ttl=60)
def cargar_matriz_precios_maestra():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table("precios_trabajos").select("*").execute()
        if res.data: return pd.DataFrame(res.data)
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_directorio_correos():
    if not supabase: return {"Christian Herrera": "c.h.servicioautomotriz@gmail.com"}
    try:
        res = supabase.table("directorio_correos").select("*").execute()
        if res.data: return {row['nombre']: row['email'] for row in res.data}
    except: pass
    return {"Christian Herrera": "c.h.servicioautomotriz@gmail.com"}

CATALOGO = cargar_catalogo_vehiculos()
DF_PRECIOS = cargar_matriz_precios_maestra()

# Mapeo a las columnas en minúsculas de tu nuevo CSV
MAPEO_TARIFAS = {
    "SSAS (Servicio Salud)": "costo_ssas",
    "SAMU": "costo_ssas",
    "Hospital Temuco": "costo_hosp_temuco",
    "Hospital Villarrica": "costo_hosp_villarrica",
    "Hospital Lautaro": "costo_hosp_lautaro",
    "Hospital Pitrufquen": "costo_hosp_pitrufquen",
    "Gendarmería de Chile": "costo_gend",
    "Cliente Particular": "costo_ssas"
}

# ==========================================
# 3. GENERADOR DE PDF Y CORREOS
# ==========================================
def format_clp(v): 
    try: return f"${float(v):,.0f}".replace(",", ".")
    except: return "$0"

def enviar_correo(destinatario, asunto, mensaje_texto, pdf_bytes, nombre_archivo, email_reply):
    try:
        remitente_sistema = st.secrets["email"]["user"]
        password = st.secrets["email"]["password"]
        msg = MIMEMultipart()
        msg['From'] = f"Sistema Cotizaciones C.H. Automotriz <{remitente_sistema}>"
        msg['To'] = destinatario
        msg['Subject'] = asunto
        msg.add_header('reply-to', email_reply) 
        msg.attach(MIMEText(mensaje_texto, 'plain'))
        adjunto = MIMEApplication(pdf_bytes, _subtype="pdf")
        adjunto.add_header('Content-Disposition', 'attachment', filename=nombre_archivo)
        msg.attach(adjunto)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente_sistema, password)
        server.send_message(msg)
        server.quit()
        return True, "Correo enviado exitosamente."
    except Exception as e: 
        return False, str(e)

class PDF(FPDF):
    def __init__(self, correlativo="", official=False): 
        super().__init__()
        self.correlativo = correlativo
        self.is_official = official
    def header(self):
        logo = None
        for ext in ['.jpg', '.png', '.jpeg']:
            if os.path.exists("logo_christian" + ext): logo = "logo_christian" + ext
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

def generar_pdf_oficial(patente, marca, modelo, cliente_nombre, cliente_rut, items, total_neto, is_official, estado_trabajo, usuario_final_txt, observaciones, correlativo):
    pdf = PDF(correlativo=correlativo, official=is_official)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=30) 
    
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
    pdf.cell(190, 6, "  DATOS DEL CLIENTE / FACTURACIÓN", 1, 1, 'L', 1)
    pdf.set_text_color(0, 0, 0)
    
    fila_dinamica(" Señor(es)", str(cliente_nombre).upper(), " Fecha Emisión", datetime.now().strftime('%d/%m/%Y'))
    fila_dinamica(" RUT", str(cliente_rut).upper(), " Usuario Final", str(usuario_final_txt).upper(), is_last=True)
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(10, 37, 64)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(190, 6, "  DATOS DEL VEHÍCULO / OPERACIÓN", 1, 1, 'L', 1)
    pdf.set_text_color(0, 0, 0)
    
    pat_str = str(patente).upper() if patente else "SIN PATENTE"
    marca_str = str(marca).upper() if marca and marca != "--- Seleccione Marca ---" else "N/A"
    modelo_str = str(modelo).upper() if modelo and modelo != "---" else "N/A"
    
    fila_dinamica(" Marca", marca_str, " Patente", pat_str)
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
    return pdf.output(dest='S').encode('latin-1') if isinstance(pdf.output(dest='S'), str) else bytes(pdf.output(dest='S'))

# ==========================================
# 4. FUNCIONES DE BASE DE DATOS Y STORAGE
# ==========================================
def subir_pdf_a_storage(nombre_archivo, pdf_bytes):
    try:
        supabase.storage.from_("pdf_cotizaciones").upload(path=nombre_archivo, file=pdf_bytes, file_options={"content-type": "application/pdf"})
        return supabase.storage.from_("pdf_cotizaciones").get_public_url(nombre_archivo)
    except: return None

def registrar_solicitud_gabo(patente, contacto, telefono, correo, origen, destino_institucion, descripcion):
    try:
        if patente:
            supabase.table("directorio_vehiculos").upsert({
                "patente": patente, "nombre_contacto": contacto, 
                "telefono": telefono, "correo": correo, 
                "origen_cliente": origen, "tipo_cliente": destino_institucion
            }).execute()
        
        supabase.table("historial_trabajos").insert({
            "patente": patente if patente else None,
            "nombre_cliente_manual": contacto, 
            "origen_trabajo": origen,
            "descripcion_requerimiento": descripcion,
            "estado": "Requerido",
            "creado_por": "Gabo"
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error registrando en Supabase: {e}")
        return False

def extraer_historial_completo():
    try:
        res = supabase.table("historial_trabajos").select("*").order("id_cotizacion", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: return pd.DataFrame()

# ==========================================
# 5. CONTROL DE PERFILES DE ACCESO (GLOBAL)
# ==========================================
if 'usuario' not in st.session_state: st.session_state.usuario = None

if st.session_state.usuario is None:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.title("🔐 Ecosistema C.H. Automotriz")
        p_sel = st.selectbox("Identificación de Usuario", ["--- Seleccione ---", "Gabriel Poblete (Planificador)", "Christian Herrera (Taller)"])
        pass_in = st.text_input("Contraseña", type="password")
        if st.button("Ingresar al Sistema", type="primary"):
            if p_sel == "Gabriel Poblete (Planificador)" and pass_in == "gabo2026":
                st.session_state.usuario = "Gabo"
                st.rerun()
            elif p_sel == "Christian Herrera (Taller)" and pass_in == "cristian2026":
                st.session_state.usuario = "Cristian"
                st.session_state.vista_taller = "Bandeja"
                st.session_state.paso_actual = 1
                st.rerun()
            else: st.error("Credenciales Inválidas.")
    st.stop()

# --- BARRA LATERAL GLOBAL Y BOTÓN DE CERRAR SESIÓN ---
with st.sidebar:
    st.markdown(f"👤 Conectado: **{st.session_state.usuario}**")
    st.markdown("---")
    
    if st.session_state.usuario == "Cristian":
        if st.button("📥 Bandeja de Órdenes"): st.session_state.vista_taller = "Bandeja"; st.rerun()
        if st.button("🚀 Cotización Libre"): 
            st.session_state.vista_taller = "Cotizador"
            st.session_state.paso_actual = 1
            st.session_state.sol_activa = None
            st.session_state.patente_confirmada = ""
            st.rerun()
        if st.button("🗂️ Historial General"): st.session_state.vista_taller = "Historial"; st.rerun()
        st.markdown("---")
        
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# ==========================================
# 6. VISTA DE PLANIFICACIÓN (GABO)
# ==========================================
if st.session_state.usuario == "Gabo":
    st.title("🎛️ Consola de Planificación Operativa (Gabo)")
    
    with st.expander("➕ Levantar Requerimiento para Taller", expanded=True):
        f1, f2, f3 = st.columns(3)
        pat = f1.text_input("Patente Vehículo (Opcional)").upper()
        origen = f2.selectbox("Canal Comercial (Quién Factura)", ["Kaufmann", "Propio Cristian"])
        dest_inst = f3.selectbox("Usuario Final / Destino Operativo", ["SSAS (Servicio Salud)", "SAMU", "Hospital Temuco", "Hospital Villarrica", "Gendarmería de Chile", "Cliente Particular"])
        
        st.markdown("**📋 Datos de Contacto de quien gestiona la orden:**")
        c1, c2, c3 = st.columns(3)
        cont_nom = c1.text_input("Nombre de Contacto", value="Gabriel Poblete" if origen == "Kaufmann" else "")
        cont_tel = c2.text_input("Teléfono de Contacto")
        cont_cor = c3.text_input("Correo de Contacto")
        
        desc = st.text_area("Instrucciones Específicas / Diagnóstico")
        
        if st.button("Enviar Requerimiento al Taller", type="primary"):
            if cont_nom and desc:
                if registrar_solicitud_gabo(pat, cont_nom, cont_tel, cont_cor, origen, dest_inst, desc):
                    st.success("🚀 Requerimiento asignado exitosamente en la bandeja de Cristian.")
                    time.sleep(1.2)
                    st.rerun()
            else: st.warning("Rellena el nombre del contacto y la descripción.")

    st.markdown("---")
    st.subheader("📊 Panel de Trazabilidad Global")
    df_global = extraer_historial_completo()
    if not df_global.empty:
        df_global = df_global.reindex(columns=['id_cotizacion', 'patente', 'nombre_cliente_manual', 'origen_trabajo', 'estado', 'total_clp', 'pdf_url'])
        st.dataframe(df_global, use_container_width=True)

# ==========================================
# 7. VISTA OPERATIVA INTEGRADA (CRISTIAN)
# ==========================================
elif st.session_state.usuario == "Cristian":
    
    if st.session_state.vista_taller == "Bandeja":
        st.title("📥 Requerimientos Asignados")
        df_todo = extraer_historial_completo()
        if not df_todo.empty and 'estado' in df_todo.columns:
            df_req = df_todo[df_todo['estado'] == 'Requerido']
            if not df_req.empty:
                for idx, fila in df_req.iterrows():
                    st.markdown(f"""
                    <div class="card-requerido">
                        <h4>📋 Orden N° {fila['id_cotizacion']} | Origen: {fila['origen_trabajo']} | Identificación: {fila['patente'] if pd.notna(fila['patente']) and fila['patente'] else 'S/P'}</h4>
                        <p><strong>Instrucciones de Planificación:</strong> {fila['descripcion_requerimiento']}</p>
                        <p><small>Contacto de Gestión: {fila['nombre_cliente_manual']}</small></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"⚙️ Atender e Iniciar Cotización N° {fila['id_cotizacion']}", key=f"at_{fila['id_cotizacion']}", type="primary"):
                        st.session_state.sol_activa = fila['id_cotizacion']
                        st.session_state.patente_confirmada = fila['patente'] if pd.notna(fila['patente']) else ""
                        st.session_state.origen_inyectado = fila['origen_trabajo']
                        st.session_state.vista_taller = "Cotizador"
                        st.session_state.paso_actual = 2
                        st.rerun()
            else: st.success("¡Excelente! No tienes solicitudes pendientes.")

    elif st.session_state.vista_taller == "Cotizador":
        if st.session_state.paso_actual == 1:
            st.title("Nueva Cotización Express")
            pat_texto = st.text_input("Ingresa la Patente (Opcional)").upper()
            if st.button("Abrir Formulario", type="primary"):
                st.session_state.patente_confirmada = pat_texto
                st.session_state.origen_inyectado = "Propio Cristian"
                st.session_state.paso_actual = 2
                st.rerun()

        elif st.session_state.paso_actual == 2:
            p_in = st.session_state.patente_confirmada
            sol_id = st.session_state.get('sol_activa')
            
            st.title("📝 Configuración de Precios y Formulario")
            
            origen_sel = st.selectbox("Canal / Origen del Trabajo", ["Kaufmann", "Propio Cristian"], index=0 if st.session_state.get('origen_inyectado') == "Kaufmann" else 1)
            
            cf1, cf2 = st.columns(2)
            cliente_default = "KAUFMANN S.A." if origen_sel == "Kaufmann" else ""
            cli_fac = cf1.text_input("Señor(es) (Facturación / Cliente Principal)", value=cliente_default)
            rut_fac = cf2.text_input("RUT de Facturación")
            
            ops_inst = ["SSAS (Servicio Salud)", "SAMU", "Hospital Temuco", "Hospital Villarrica", "Hospital Lautaro", "Hospital Pitrufquen", "Gendarmería de Chile", "Cliente Particular"]
            us_final = st.selectbox("Usuario Final (Institución Destino del Vehículo)", ops_inst)
            
            cv1, cv2 = st.columns(2)
            marca_sel = cv1.selectbox("Marca", list(CATALOGO.keys()))
            mod_disp = CATALOGO[marca_sel] if marca_sel and marca_sel != "--- Seleccione Marca ---" else ["---"]
            modelo_sel = cv2.selectbox("Modelo", mod_disp)
            
            st.markdown("---")
            
            st.subheader("🛠️ Selección de Trabajos con Tarifa Base Inteligente")
            
            # MATRIZ DINÁMICA CONECTADA A SUPABASE
            col_tarifa_a_buscar = MAPEO_TARIFAS.get(us_final, "costo_ssas")
            
            if not DF_PRECIOS.empty and 'categoria' in DF_PRECIOS.columns:
                cat_disponibles = sorted(DF_PRECIOS['categoria'].dropna().unique().tolist())
                cat_sel = st.selectbox("1. Selecciona la Categoría de Trabajo", ["---"] + cat_disponibles)
                
                if cat_sel != "---":
                    trabajos_filtrados = DF_PRECIOS[DF_PRECIOS['categoria'] == cat_sel]
                    trabajo_sel = st.selectbox("2. Selecciona el Trabajo Específico", ["---"] + trabajos_filtrados['trabajo'].tolist())
                    
                    if trabajo_sel != "---":
                        fila_precio = trabajos_filtrados[trabajos_filtrados['trabajo'] == trabajo_sel].iloc[0]
                        precio_base_sugerido = int(fila_precio[col_tarifa_a_buscar])
                        
                        st.success(f"💰 Precio base indexado para {us_final}: **{format_clp(precio_base_sugerido)}**")
                        
                        if st.button("➕ Cargar este Trabajo al Presupuesto"):
                            if 'lista_particular' not in st.session_state: st.session_state.lista_particular = []
                            st.session_state.lista_particular.append({
                                "Descripción": trabajo_sel, "Cantidad": 1, 
                                "Unitario_Costo": precio_base_sugerido, "Total_Costo": precio_base_sugerido
                            })
                            st.rerun()

            st.markdown("---")
            sel_final = []
            tab_manual, tab_repuestos = st.tabs(["📝 Operaciones Manuales", "🛒 Repuestos"])
            
            with tab_manual:
                cc1, cc2 = st.columns([6, 2], vertical_alignment="center")
                dm = cc1.text_input("Trabajo Extra / Operación Manual")
                pm = cc2.number_input("Costo Neto ($)", min_value=0, step=5000)
                if st.button("Añadir Operación"):
                    if dm and pm > 0:
                        if 'lista_particular' not in st.session_state: st.session_state.lista_particular = []
                        st.session_state.lista_particular.append({"Descripción": dm, "Cantidad": 1, "Unitario_Costo": pm, "Total_Costo": pm})
                        st.rerun()
                        
                if 'lista_particular' in st.session_state:
                    for idx, i in enumerate(st.session_state.lista_particular):
                        ca, cb = st.columns([6, 1], vertical_alignment="center")
                        ca.markdown(f"• {i['Descripción']} - **{format_clp(i['Total_Costo'])}**")
                        if cb.button("🗑️", key=f"dm_{idx}"): st.session_state.lista_particular.pop(idx); st.rerun()
                    sel_final = st.session_state.lista_particular

            with tab_repuestos:
                cx1, cx2 = st.columns([3, 1])
                d_rep = cx1.text_input("Descripción Repuesto")
                q_rep = cx2.number_input("Cant", 1)
                cx3, cx4, cx5 = st.columns(3)
                c_rep = cx3.number_input("Costo ($)", 0, step=1000)
                c_env = cx4.number_input("Envío ($)", 0, step=1000)
                m_pct = cx5.number_input("Margen %", 0, 100, 30)
                p_final = int((c_rep + c_env) * (1 + m_pct / 100.0))
                st.markdown(f"#### Precio de Venta: **{format_clp(p_final)}**")
                
                if st.button("Añadir Repuesto"):
                    if d_rep and p_final > 0:
                        if 'lista_repuestos' not in st.session_state: st.session_state.lista_repuestos = []
                        st.session_state.lista_repuestos.append({"Descripción": d_rep, "Cantidad": q_rep, "Unitario_Costo": float(p_final), "Total_Costo": float(p_final * q_rep)})
                        st.rerun()
                        
                if 'lista_repuestos' in st.session_state:
                    for idx, i in enumerate(st.session_state.lista_repuestos):
                        ca, cb = st.columns([6, 1], vertical_alignment="center")
                        ca.text(f"• {i['Cantidad']}x {i['Descripción']} - {format_clp(i['Total_Costo'])}")
                        if cb.button("🗑️", key=f"dr_{idx}"): st.session_state.lista_repuestos.pop(idx); st.rerun()
                    sel_final.extend(st.session_state.lista_repuestos)

            if sel_final:
                st.markdown("---")
                tn = sum(x['Total_Costo'] for x in sel_final)
                iv = tn * 0.19
                tf = tn + iv
                
                k1, k2, k3 = st.columns(3)
                k1.metric("SUB TOTAL NETO", format_clp(tn))
                k2.metric("I.V.A. (19%)", format_clp(iv))
                k3.metric("TOTAL PRESUPUESTO", format_clp(tf))
                
                obs = st.text_area("Observaciones del Taller:")
                est = st.radio("Fase del Trabajo:", ("En Espera de Aprobación", "Trabajo Realizado"))
                
                if 'presupuesto_generado' not in st.session_state:
                    if st.button("💾 GUARDAR ORDEN Y GENERAR DOCUMENTO", type="primary", use_container_width=True):
                        try:
                            if sol_id:
                                corr_id = str(sol_id)
                                pdf_b = generar_pdf_oficial(p_in, marca_sel, modelo_sel, cli_fac, rut_fac, sel_final, tn, False, est, us_final, obs, corr_id)
                                n_pdf = f"Presupuesto_{corr_id}.pdf"
                                url_doc = subir_pdf_a_storage(n_pdf, pdf_b)
                                supabase.table("historial_trabajos").update({"estado": "Generado", "total_clp": tf, "pdf_url": url_doc, "origen_trabajo": origen_sel, "nombre_cliente_manual": cli_fac}).eq("id_cotizacion", sol_id).execute()
                            else:
                                res = supabase.table("historial_trabajos").insert({"patente": p_in if p_in else None, "nombre_cliente_manual": cli_fac, "origen_trabajo": origen_sel, "estado": "Generado", "total_clp": tf, "creado_por": "Cristian"}).execute()
                                corr_id = str(res.data[0]['id_cotizacion'])
                                pdf_b = generar_pdf_oficial(p_in, marca_sel, modelo_sel, cli_fac, rut_fac, sel_final, tn, False, est, us_final, obs, corr_id)
                                n_pdf = f"Presupuesto_{corr_id}.pdf"
                                url_doc = subir_pdf_a_storage(n_pdf, pdf_b)
                                supabase.table("historial_trabajos").update({"pdf_url": url_doc}).eq("id_cotizacion", corr_id).execute()
                                
                            st.session_state['presupuesto_generado'] = {'pdf': pdf_b, 'nombre': n_pdf, 'url': url_doc}
                            st.rerun()
                        except Exception as e_gen: st.error(f"Error: {e_gen}")
                else:
                    d = st.session_state['presupuesto_generado']
                    st.success("✅ Documento Oficial guardado en la nube.")
                    st.download_button("📥 DESCARGAR PDF", d['pdf'], d['nombre'], "application/pdf")
                    
                    st.markdown("---")
                    st.subheader("📧 Enviar Correo al Cliente")
                    dir_c = cargar_directorio_correos()
                    d_sel = st.multiselect("Contactos Frecuentes:", options=list(dir_c.keys()), default=[])
                    e_ad = st.text_input("Correos Adicionales (separados por coma):")
                    e_as = st.text_input("Asunto:", value=f"{d['nombre'].replace('.pdf', '')} - C.H. Servicio Automotriz")
                    e_ms = st.text_area("Mensaje:", value=f"Estimado(a),\n\nAdjunto enviamos el presupuesto solicitado para la patente {p_in}.\n\nSaludos cordiales.")
                    
                    if st.button("📤 Enviar Correo", type="primary"):
                        lc = [dir_c[n] for n in d_sel]
                        if e_ad: lc.extend([e.strip() for e in e_ad.split(',') if e.strip()])
                        dfinal = ", ".join(lc)
                        if dfinal:
                            with st.spinner("Enviando..."):
                                ex, m = enviar_correo(dfinal, e_as, e_ms, d['pdf'], d['nombre'], EMAIL_SISTEMA)
                            if ex:
                                supabase.table("historial_trabajos").update({"estado": "Enviado"}).eq("id_cotizacion", sol_id if sol_id else d['nombre'].split('_')[1].replace('.pdf','')).execute()
                                st.success("✅ Enviado exitosamente.")
                            else: st.error(f"❌ {m}")
                        else: st.warning("Ingresa un destinatario.")
                    
                    if st.button("🔄 Finalizar y Cerrar Ciclo"):
                        for k in ['lista_particular', 'lista_repuestos', 'presupuesto_generado', 'sol_activa']:
                            if k in st.session_state: del st.session_state[k]
                        st.session_state.vista_taller = "Bandeja"
                        st.rerun()

    elif st.session_state.vista_taller == "Historial":
        st.title("🗃️ Registro y Correos")
        df_todo = extraer_historial_completo()
        if not df_todo.empty:
            lupa = st.text_input("🔍 Buscar por Patente o Cliente...").upper()
            if lupa: df_todo = df_todo[df_todo['patente'].str.contains(lupa, na=False) | df_todo['nombre_cliente_manual'].str.contains(lupa, na=False, case=False)]
            
            t1, t2, t3 = st.tabs(["🟡 Por Enviar", "🔵 Enviados", "🟢 Realizados / Cerrados"])
            with t1:
                for idx, r in df_todo[df_todo['estado'] == 'Generado'].iterrows():
                    ca, cb, cc = st.columns([4, 1.5, 1])
                    ca.write(f"📄 N° {r['id_cotizacion']} | Patente: {r['patente']} | Cuenta: {r['nombre_cliente_manual']} | Total: ${r['total_clp']:,.0f}")
                    if pd.notna(r.get('pdf_url')): cb.markdown(f"[👁️ Ver Documento]({r['pdf_url']})")
                    if cc.button("✉️ Marcar Enviado", key=f"e_{r['id_cotizacion']}"):
                        supabase.table("historial_trabajos").update({"estado": "Enviado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                        st.rerun()
            with t2:
                for idx, r in df_todo[df_todo['estado'] == 'Enviado'].iterrows():
                    ca, cb, cc = st.columns([4, 1.5, 1])
                    ca.write(f"🔵 N° {r['id_cotizacion']} | Patente: {r['patente']} | Cuenta: {r['nombre_cliente_manual']} | Total: ${r['total_clp']:,.0f}")
                    if pd.notna(r.get('pdf_url')): cb.markdown(f"[📥 Descargar]({r['pdf_url']})")
                    if cc.button("🟢 Aprobar", key=f"a_{r['id_cotizacion']}"):
                        supabase.table("historial_trabajos").update({"estado": "Aprobado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                        st.rerun()
            with t3:
                df_fin = df_todo[df_todo['estado'].isin(['Aprobado', 'Terminado'])]
                if not df_fin.empty: st.dataframe(df_fin[['id_cotizacion', 'patente', 'nombre_cliente_manual', 'estado', 'total_clp', 'pdf_url']], use_container_width=True)
