import streamlit as st
import pandas as pd
import io
import os
import time 
from fpdf import FPDF
from datetime import datetime
import smtplib
import json
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

# Emojis para categorías
EMOJIS_CAT = {
    "Climatización y Aire": "❄️", "Carrocería y Vidrios": "🚐", 
    "Interior Sanitario": "🏥", "Asientos y Tapiz": "💺", 
    "Equipamiento y Radio": "📻", "Cabina y Tablero": "📟", 
    "Camilla": "🚑", "Seguridad y Calabozos": "🔒",
    "Electricidad": "⚡", "Mecánica": "🔧", "Accesorios": "🛠️"
}

st.markdown(f"""
<style>
    .stTabs [aria-selected='true'] {{ background-color: {COLOR_PRIMARIO} !important; color: white !important; font-weight: bold; border-radius: 4px; }}
    .stButton > button[kind='primary'] {{ background-color: {COLOR_PRIMARIO} !important; color: white !important; font-weight: bold; width: 100%; }}
    .card-requerido {{ background-color: #ffe6e6; padding: 15px; border-left: 5px solid #ff4d4d; border-radius: 4px; margin-bottom: 10px; color: #111827 !important; }}
    .card-requerido h4, .card-requerido p, .card-requerido small {{ color: #111827 !important; }}
    .card-borrador {{ background-color: #e6f2ff; padding: 15px; border-left: 5px solid #0066cc; border-radius: 4px; margin-bottom: 15px; color: #000; }}
    div[data-testid="stNumberInput"] input {{ max-width: 100px; text-align: center; }}
    .carrito-container {{ border: 1px solid #ddd; padding: 15px; border-radius: 8px; background-color: #f8f9fa; color: #000; }}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CARGA DINÁMICA DESDE SUPABASE
# ==========================================
@st.cache_data(ttl=60)
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

def cargar_trabajos_manuales_historicos():
    if not supabase: return []
    try:
        res = supabase.table("trabajos_manuales").select("*").order("fecha", desc=True).limit(15).execute()
        if res.data: 
            return list({v['descripcion']:v for v in res.data}.values()) # Eliminar duplicados
    except: pass
    return []

CATALOGO = cargar_catalogo_vehiculos()
DF_PRECIOS = cargar_matriz_precios_maestra()

MAPEO_TARIFAS = {
    "SSAS (Servicio Salud)": "costo_ssas", "SAMU": "costo_ssas",
    "Hospital Temuco": "costo_hosp_temuco", "Hospital Villarrica": "costo_hosp_villarrica",
    "Hospital Lautaro": "costo_hosp_lautaro", "Hospital Pitrufquen": "costo_hosp_pitrufquen",
    "Gendarmería de Chile": "costo_gend", "Cliente Particular": "costo_ssas"
}

# ==========================================
# 3. GENERADOR DE PDF Y UTILS
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

def generar_pdf_oficial(patente, marca, modelo, cliente_nombre, cliente_rut, items, total_neto, is_official, estado_trabajo, usuario_final_txt, observaciones, correlativo, n_sap_txt=""):
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
    if n_sap_txt:
        fila_dinamica(" RUT", str(cliente_rut).upper(), " N° OT / SAP", str(n_sap_txt).upper())
        fila_dinamica(" ", "", " Usuario Final", str(usuario_final_txt).upper(), is_last=True)
    else:
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
# 4. FUNCIONES DE BASE DE DATOS Y BORRADOR
# ==========================================
def buscar_vehiculo_en_directorio(patente):
    try:
        res = supabase.table("directorio_vehiculos").select("*").ilike("patente", patente).execute()
        if res.data: return res.data[0]
    except: pass
    return None

def subir_pdf_a_storage(nombre_archivo, pdf_bytes):
    try:
        supabase.storage.from_("pdf_cotizaciones").upload(path=nombre_archivo, file=pdf_bytes, file_options={"content-type": "application/pdf"})
        return supabase.storage.from_("pdf_cotizaciones").get_public_url(nombre_archivo)
    except: return None

def registrar_solicitud_gabo(patente, contacto, telefono, correo, origen, destino_txt, tarifa_math, descripcion, n_sap):
    try:
        if patente:
            supabase.table("directorio_vehiculos").upsert({
                "patente": patente, "nombre_contacto": contacto, 
                "telefono": telefono, "correo": correo, 
                "origen_cliente": origen, "cliente_final": destino_txt, "tipo_cliente": tarifa_math
            }).execute()
        
        supabase.table("historial_trabajos").insert({
            "patente": patente if patente else None,
            "origen_trabajo": origen, "usuario_final": destino_txt, "tarifa_aplicada": tarifa_math,
            "contacto_gestion": contacto, "descripcion_requerimiento": descripcion,
            "estado": "Requerido", "creado_por": "Gabo", "n_sap": n_sap
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error registrando: {e}")
        return False

def guardar_trabajo_manual_db(descripcion, costo):
    if not supabase: return
    try: supabase.table("trabajos_manuales").insert({"descripcion": descripcion, "costo": costo}).execute()
    except: pass

def extraer_historial_completo():
    try:
        res = supabase.table("historial_trabajos").select("*").order("id_cotizacion", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: return pd.DataFrame()

def guardar_borrador():
    if not supabase or st.session_state.usuario != "Cristian": return
    datos = {
        'sol_activa': st.session_state.get('sol_activa'),
        'sub_paso': st.session_state.get('sub_paso', 1),
        'c_patente': st.session_state.get('c_patente'),
        'c_origen': st.session_state.get('c_origen'),
        'c_cli_fac': st.session_state.get('c_cli_fac'),
        'c_rut_fac': st.session_state.get('c_rut_fac'),
        'c_us_final': st.session_state.get('c_us_final'),
        'c_marca': st.session_state.get('c_marca'),
        'c_modelo': st.session_state.get('c_modelo'),
        'c_tarifa': st.session_state.get('c_tarifa'),
        'c_nsap': st.session_state.get('c_nsap', ''),
        'lista_particular': st.session_state.get('lista_particular', []),
        'lista_repuestos': st.session_state.get('lista_repuestos', [])
    }
    try: supabase.table("borradores_cotizacion").upsert({'id_usuario': 'Cristian', 'datos': datos}).execute()
    except: pass

def cargar_borrador():
    if not supabase: return None
    try:
        res = supabase.table("borradores_cotizacion").select("datos").eq("id_usuario", "Cristian").execute()
        if res.data: return res.data[0]['datos']
    except: pass
    return None

def eliminar_borrador():
    if not supabase: return
    try: supabase.table("borradores_cotizacion").delete().eq("id_usuario", "Cristian").execute()
    except: pass

def limpiar_sesion_cristian():
    claves_a_borrar = ['sol_activa', 'sub_paso', 'c_patente', 'c_origen', 'c_cli_fac', 'c_rut_fac', 'c_us_final', 'c_marca', 'c_modelo', 'c_tarifa', 'c_nsap', 'lista_particular', 'lista_repuestos', 'presupuesto_generado', 'sel_final_cache']
    for k in claves_a_borrar:
        if k in st.session_state: del st.session_state[k]
    eliminar_borrador()

# ==========================================
# 5. CONTROL DE PERFILES Y SESIÓN
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
                st.rerun()
            else: st.error("Credenciales Inválidas.")
    st.stop()

with st.sidebar:
    st.markdown(f"👤 Conectado: **{st.session_state.usuario}**")
    st.markdown("---")
    
    if st.session_state.usuario == "Cristian":
        if st.button("🏠 Inicio / Limpiar Todo", type="primary"): 
            limpiar_sesion_cristian()
            st.session_state.vista_taller = "Bandeja"
            st.rerun()
        if st.button("📥 Bandeja de Órdenes"): 
            st.session_state.vista_taller = "Bandeja"
            st.rerun()
        if st.button("🚀 Nueva Cotización Libre"): 
            limpiar_sesion_cristian()
            st.session_state.vista_taller = "Cotizador"
            st.session_state.sub_paso = 0 
            st.rerun()
        if st.button("🗂️ Historial General"): 
            st.session_state.vista_taller = "Historial"
            st.rerun()
        st.markdown("---")
        
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# ==========================================
# 6. VISTA DE PLANIFICACIÓN (GABO) 
# ==========================================
if st.session_state.usuario == "Gabo":
    st.title("🎛️ Consola de Planificación (Gabo)")
    
    if 'g_origen' not in st.session_state: st.session_state.g_origen = "Kaufmann"
    if 'g_dest_txt' not in st.session_state: st.session_state.g_dest_txt = ""
    if 'g_tarifa' not in st.session_state: st.session_state.g_tarifa = "SSAS (Servicio Salud)"
    if 'g_nom' not in st.session_state: st.session_state.g_nom = "Gabriel Poblete"
    if 'g_tel' not in st.session_state: st.session_state.g_tel = ""
    if 'g_cor' not in st.session_state: st.session_state.g_cor = ""

    with st.expander("➕ Levantar Requerimiento para Taller", expanded=True):
        f1, f2 = st.columns([1, 1])
        c_pat_a, c_pat_b = f1.columns([4, 1])
        pat = c_pat_a.text_input("Patente Vehículo").upper()
        
        if c_pat_b.button("🔍 Buscar"):
            datos_v = buscar_vehiculo_en_directorio(pat)
            if datos_v:
                st.session_state.g_origen = datos_v.get('origen_cliente', 'Kaufmann')
                st.session_state.g_dest_txt = datos_v.get('cliente_final', '')
                st.session_state.g_tarifa = datos_v.get('tipo_cliente', 'SSAS (Servicio Salud)')
                nom_bd = datos_v.get('nombre_contacto')
                if not nom_bd or "hospital" in nom_bd.lower() or "samu" in nom_bd.lower() or "gendarmeria" in nom_bd.lower():
                    st.session_state.g_nom = 'Gabriel Poblete'
                else: st.session_state.g_nom = nom_bd
                st.session_state.g_tel = datos_v.get('telefono', '')
                st.session_state.g_cor = datos_v.get('correo', '')
                st.toast("✅ Vehículo encontrado.")
            else: st.toast("⚠️ Vehículo nuevo.", icon="🆕")
            st.rerun()

        ops_origen = ["Kaufmann", "Propio Cristian"]
        idx_origen = ops_origen.index(st.session_state.g_origen) if st.session_state.g_origen in ops_origen else 0
        origen = f2.selectbox("Cliente / Quién Factura", ops_origen, index=idx_origen)
        
        st.markdown("---")
        d1, d2 = st.columns(2)
        dest_inst = d1.text_input("Destino Operativo / Usuario Final (Texto impreso en PDF)", value=st.session_state.g_dest_txt)
        ops_tarifas = ["SSAS (Servicio Salud)", "SAMU", "Hospital Temuco", "Hospital Villarrica", "Hospital Lautaro", "Hospital Pitrufquen", "Gendarmería de Chile", "Cliente Particular"]
        idx_tarifa = ops_tarifas.index(st.session_state.g_tarifa) if st.session_state.g_tarifa in ops_tarifas else 0
        tarifa_aplicada = d2.selectbox("Tarifa Base a Aplicar (Fórmula de Precios)", ops_tarifas, index=idx_tarifa)
        
        # CAMPO EXCLUSIVO PARA GABO (N° OT SAP)
        n_sap_input = st.text_input("N° Cotización o N° OT (SAP Kaufmann) - Opcional", help="Dato interno para rastreo. Cristian no necesita editarlo, pero saldrá impreso en el PDF.")
        
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        cont_nom = c1.text_input("Nombre de Contacto", value=st.session_state.g_nom)
        cont_tel = c2.text_input("Teléfono", value=st.session_state.g_tel)
        correo_sug = st.session_state.g_cor
        if not correo_sug:
            dir_c = cargar_directorio_correos()
            if cont_nom in dir_c: correo_sug = dir_c[cont_nom]
        cont_cor = c3.text_input("Correo", value=correo_sug)
        
        desc = st.text_area("Instrucciones Específicas para Cristian")
        if st.button("Enviar Requerimiento al Taller", type="primary"):
            if cont_nom and desc:
                if registrar_solicitud_gabo(pat, cont_nom, cont_tel, cont_cor, origen, dest_inst, tarifa_aplicada, desc, n_sap_input):
                    st.success("🚀 Asignado exitosamente.")
                    time.sleep(1.2); st.rerun()
            else: st.warning("Faltan datos.")

    st.markdown("---")
    st.subheader("✅ Autorización de Cotizaciones (Revisión Final)")
    df_global = extraer_historial_completo()
    if not df_global.empty:
        df_enviadas = df_global[df_global['estado'] == 'Enviado']
        if not df_enviadas.empty:
            for idx, r in df_enviadas.iterrows():
                ca, cb, cc = st.columns([5, 1.5, 1.5])
                ca.write(f"📄 N° {r['id_cotizacion']} | Patente: {r['patente']} | Total: {format_clp(r['total_clp'])}")
                cb.markdown(f"[👁️ Ver Documento]({r['pdf_url']})")
                if cc.button("✅ Aprobar Trabajo", key=f"apr_gb_{r['id_cotizacion']}", type="primary"):
                    supabase.table("historial_trabajos").update({"estado": "Aprobado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                    st.success("Trabajo Aprobado."); time.sleep(1); st.rerun()
        else: st.info("No hay cotizaciones pendientes de tu aprobación.")
        
        st.markdown("---")
        st.subheader("📊 Trazabilidad Global")
        col_list = ['id_cotizacion', 'patente', 'usuario_final', 'tarifa_aplicada', 'estado', 'total_clp']
        
        # Formatear el CLP en la vista de dataframe
        df_view = df_global[[c for c in col_list if c in df_global.columns]].copy()
        if 'total_clp' in df_view.columns:
            df_view['total_clp'] = df_view['total_clp'].apply(lambda x: format_clp(x))
        st.dataframe(df_view, use_container_width=True)

# ==========================================
# 7. VISTA OPERATIVA INTEGRADA (CRISTIAN) - FLUJO WIZARD
# ==========================================
elif st.session_state.usuario == "Cristian":
    
    # Sistema de recuperación de Borrador
    if 'borrador_check' not in st.session_state:
        st.session_state.borrador_check = True
        datos_recuperados = cargar_borrador()
        if datos_recuperados and st.session_state.vista_taller == "Bandeja":
            st.session_state.hay_borrador = datos_recuperados
            
    if st.session_state.get('hay_borrador'):
        st.markdown(f"""<div class="card-borrador"><h4>⚠️ Tienes una cotización en pausa (Patente: {st.session_state.hay_borrador.get('c_patente', 'S/P')})</h4></div>""", unsafe_allow_html=True)
        c_a, c_b = st.columns(2)
        if c_a.button("✅ Recuperar Trabajo", use_container_width=True):
            b = st.session_state.hay_borrador
            for k, v in b.items(): st.session_state[k] = v
            st.session_state.vista_taller = "Cotizador"
            del st.session_state['hay_borrador']
            st.rerun()
        if c_b.button("🗑️ Descartar y Empezar de Cero", use_container_width=True):
            eliminar_borrador()
            del st.session_state['hay_borrador']
            st.rerun()
        st.markdown("---")

    if st.session_state.vista_taller == "Bandeja":
        st.title("📥 Bandeja de Entrada")
        df_todo = extraer_historial_completo()
        
        # Descargar el directorio para enriquecer la tarjeta visualmente
        df_dir = pd.DataFrame()
        if supabase:
            res_dir = supabase.table("directorio_vehiculos").select("patente, marca, modelo").execute()
            if res_dir.data: df_dir = pd.DataFrame(res_dir.data)
            
        if not df_todo.empty and 'estado' in df_todo.columns:
            df_req = df_todo[df_todo['estado'] == 'Requerido']
            if not df_req.empty:
                for idx, fila in df_req.iterrows():
                    pat = fila['patente'] if pd.notna(fila['patente']) else 'S/P'
                    
                    # Buscar Marca y Modelo
                    m_txt = ""
                    if pat != 'S/P' and not df_dir.empty:
                        match = df_dir[df_dir['patente'] == pat]
                        if not match.empty:
                            marca = match.iloc[0].get('marca', '')
                            mod = match.iloc[0].get('modelo', '')
                            m_txt = f" | {marca} {mod}"
                    
                    st.markdown(f"""
                    <div class="card-requerido">
                        <h4>📋 Orden N° {fila['id_cotizacion']} | Patente: {pat}{m_txt}</h4>
                        <p><strong>Destino:</strong> {fila.get('usuario_final', '')}</p>
                        <p><strong>Instrucciones:</strong> {fila['descripcion_requerimiento']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    b1, b2 = st.columns([1, 4])
                    if b1.button("🗑️ Descartar", key=f"desc_{fila['id_cotizacion']}"):
                        supabase.table("historial_trabajos").update({"estado": "Descartado"}).eq("id_cotizacion", fila['id_cotizacion']).execute()
                        st.toast("Solicitud descartada."); time.sleep(1); st.rerun()
                        
                    if b2.button(f"⚙️ Atender e Iniciar Cotización", key=f"at_{fila['id_cotizacion']}", type="primary"):
                        limpiar_sesion_cristian()
                        st.session_state.sol_activa = fila['id_cotizacion']
                        st.session_state.c_patente = fila['patente'] if pd.notna(fila['patente']) else ""
                        st.session_state.c_origen = fila['origen_trabajo']
                        st.session_state.c_us_final = fila.get('usuario_final', '')
                        st.session_state.c_tarifa = fila.get('tarifa_aplicada', 'SSAS (Servicio Salud)')
                        st.session_state.c_nsap = fila.get('n_sap', '')
                        st.session_state.vista_taller = "Cotizador"
                        st.session_state.sub_paso = 1 
                        guardar_borrador()
                        st.rerun()
            else: st.success("¡Excelente! No tienes solicitudes pendientes.")

    elif st.session_state.vista_taller == "Cotizador":
        if 'sub_paso' not in st.session_state: st.session_state.sub_paso = 0
        
        # PANTALLA 0: Pedir Patente
        if st.session_state.sub_paso == 0:
            st.title("Nueva Cotización Libre")
            pat_in = st.text_input("Ingresa la Patente (Opcional)").upper()
            if st.button("Iniciar Flujo ➡️", type="primary"):
                st.session_state.c_patente = pat_in
                st.session_state.c_origen = "Propio Cristian"
                st.session_state.sub_paso = 1
                guardar_borrador()
                st.rerun()

        else:
            # BARRA DE PROGRESO WIZARD
            st.progress(st.session_state.sub_paso / 3.0)
            
            p_in = st.session_state.get('c_patente', '')
            datos_v = buscar_vehiculo_en_directorio(p_in) if p_in else None

            # PASO 1: DATOS CLIENTE Y VEHÍCULO
            if st.session_state.sub_paso == 1:
                st.header("Paso 1: Datos Administrativos y del Vehículo")
                
                # Autocompletado Base Inteligente para Kaufmann
                idx_cli = 0 if st.session_state.get('c_origen')=="Kaufmann" else 1
                origen_sel = st.selectbox("Cliente", ["Kaufmann", "Propio Cristian"], index=idx_cli)
                st.session_state.c_origen = origen_sel
                
                # Forzar datos de Kaufmann en vivo si lo selecciona
                if origen_sel == "Kaufmann":
                    st.session_state.c_cli_fac = "KAUFMANN S.A."
                    st.session_state.c_rut_fac = "92.475.000-6"
                else:
                    if 'c_cli_fac' not in st.session_state:
                        st.session_state.c_cli_fac = datos_v.get('nombre_contacto', '') if datos_v else ""
                    if 'c_rut_fac' not in st.session_state:
                        st.session_state.c_rut_fac = datos_v.get('rut_facturacion', '') if datos_v else ""

                if 'c_us_final' not in st.session_state:
                    st.session_state.c_us_final = datos_v.get('cliente_final', '') if datos_v else ''

                cf1, cf2 = st.columns(2)
                st.session_state.c_cli_fac = cf1.text_input("Señor(es) (Facturación)", value=st.session_state.c_cli_fac)
                st.session_state.c_rut_fac = cf2.text_input("RUT de Facturación", value=st.session_state.c_rut_fac)
                st.session_state.c_us_final = st.text_input("Usuario Final / Destino (Texto para el PDF)", value=st.session_state.c_us_final)
                
                cv1, cv2 = st.columns(2)
                marca_db = st.session_state.get('c_marca', datos_v.get('marca') if datos_v else None)
                idx_marca = list(CATALOGO.keys()).index(marca_db) if marca_db in CATALOGO else 0
                st.session_state.c_marca = cv1.selectbox("Marca", list(CATALOGO.keys()), index=idx_marca)
                
                mod_disp = CATALOGO[st.session_state.c_marca] if st.session_state.c_marca != "--- Seleccione Marca ---" else ["---"]
                modelo_db = st.session_state.get('c_modelo', datos_v.get('modelo') if datos_v else None)
                idx_mod = mod_disp.index(modelo_db) if modelo_db in mod_disp else 0
                st.session_state.c_modelo = cv2.selectbox("Modelo", mod_disp, index=idx_mod)
                
                st.markdown("---")
                if st.button("Continuar a Trabajos y Precios ➡️", type="primary"):
                    st.session_state.sub_paso = 2
                    guardar_borrador()
                    st.rerun()

            # PASO 2: COTIZACIÓN (TABS INTELIGENTES Y CARRITO EN VIVO)
            elif st.session_state.sub_paso == 2:
                if st.button("⬅️ Volver a Datos Administrativos"):
                    st.session_state.sub_paso = 1
                    guardar_borrador()
                    st.rerun()
                    
                st.header("Paso 2: Valorización de Trabajos")
                
                ops_tarifas = ["SSAS (Servicio Salud)", "SAMU", "Hospital Temuco", "Hospital Villarrica", "Hospital Lautaro", "Hospital Pitrufquen", "Gendarmería de Chile", "Cliente Particular"]
                tarifa_default = st.session_state.get('c_tarifa') if st.session_state.get('c_tarifa') else datos_v.get('tipo_cliente') if datos_v else "SSAS (Servicio Salud)"
                idx_t = ops_tarifas.index(tarifa_default) if tarifa_default in ops_tarifas else 0
                
                # Bloqueo Inteligente de la Tarifa si la patente está en el directorio
                is_disabled = True if (datos_v and datos_v.get('tipo_cliente')) else False
                st.session_state.c_tarifa = st.selectbox("Tarifa Base Aplicada (Fórmula Interna)", ops_tarifas, index=idx_t, disabled=is_disabled)
                col_tarifa_a_buscar = MAPEO_TARIFAS.get(st.session_state.c_tarifa, "costo_ssas")
                
                # Iniciar la recolección del carrito en vivo
                sel_final = []
                
                if not DF_PRECIOS.empty and 'categoria' in DF_PRECIOS.columns:
                    cat_disp = sorted(DF_PRECIOS['categoria'].dropna().unique().tolist())
                    nombres_tabs = [f"{EMOJIS_CAT.get(c, '🔧')} {c}" for c in cat_disp]
                    tabs_cat = st.tabs(nombres_tabs + ["📝 Manual", "🛒 Repuestos"])
                    
                    # TABS DE LA MATRIZ DE PRECIOS
                    for i, cat in enumerate(cat_disp):
                        with tabs_cat[i]:
                            df_cat = DF_PRECIOS[DF_PRECIOS['categoria'] == cat].copy()
                            df_cat.loc[:, col_tarifa_a_buscar] = pd.to_numeric(df_cat[col_tarifa_a_buscar], errors='coerce').fillna(0)
                            items_v = df_cat[df_cat[col_tarifa_a_buscar] > 0]
                            
                            if items_v.empty: st.info("Sin precios configurados aquí.")
                            else:
                                for idx, row in items_v.iterrows():
                                    cc1, cc2, cc3 = st.columns([5.5, 1.5, 2], vertical_alignment="center")
                                    cc1.markdown(f"**{row['trabajo']}**")
                                    k = f"q_{row['trabajo']}_{idx}"
                                    qty = cc2.number_input("", 0, 20, value=st.session_state.get(k, 0), key=k, label_visibility="collapsed")
                                    p = float(row[col_tarifa_a_buscar])
                                    cc3.markdown(f"**{format_clp(p)}**")
                                    if qty > 0: 
                                        sel_final.append({"Tipo": "matriz", "Descripción": row['trabajo'], "Cantidad": qty, "Unitario_Costo": p, "Total_Costo": p * qty, "Llave": k})
                    
                    # TAB MANUAL
                    with tabs_cat[-2]:
                        cm1, cm2 = st.columns([6, 2], vertical_alignment="center")
                        dm = cm1.text_input("Operación Manual Nueva")
                        pm = cm2.number_input("Costo Neto ($)", min_value=0, step=5000)
                        if st.button("Añadir Trabajo Manual"):
                            if dm and pm > 0:
                                if 'lista_particular' not in st.session_state: st.session_state.lista_particular = []
                                st.session_state.lista_particular.append({"Tipo": "manual", "Descripción": dm, "Cantidad": 1, "Unitario_Costo": pm, "Total_Costo": pm})
                                guardar_trabajo_manual_db(dm, pm) # Guardamos en el historial
                                guardar_borrador()
                                st.rerun()
                                
                        # Historial Rápido de Manuales
                        h_manuales = cargar_trabajos_manuales_historicos()
                        if h_manuales:
                            with st.expander("⏱️ Cargar trabajos manuales anteriores"):
                                for hm in h_manuales:
                                    ca, cb = st.columns([6, 1])
                                    ca.text(f"• {hm['descripcion']} - {format_clp(hm['costo'])}")
                                    if cb.button("➕", key=f"add_hm_{hm['id']}"):
                                        if 'lista_particular' not in st.session_state: st.session_state.lista_particular = []
                                        st.session_state.lista_particular.append({"Tipo": "manual", "Descripción": hm['descripcion'], "Cantidad": 1, "Unitario_Costo": hm['costo'], "Total_Costo": hm['costo']})
                                        guardar_borrador(); st.rerun()

                    # TAB REPUESTOS
                    with tabs_cat[-1]:
                        cr1, cr2 = st.columns([3, 1])
                        d_rep = cr1.text_input("Repuesto")
                        q_rep = cr2.number_input("Cant", 1)
                        cr3, cr4, cr5 = st.columns(3)
                        c_rep = cr3.number_input("Costo ($)", 0, step=1000)
                        c_env = cr4.number_input("Envío ($)", 0, step=1000)
                        m_pct = cr5.number_input("Margen %", 0, 100, 30)
                        p_final = int((c_rep + c_env) * (1 + m_pct / 100.0))
                        st.markdown(f"**A Cobrar:** {format_clp(p_final)}")
                        if st.button("Añadir Repuesto"):
                            if d_rep and p_final > 0:
                                if 'lista_repuestos' not in st.session_state: st.session_state.lista_repuestos = []
                                st.session_state.lista_repuestos.append({"Tipo": "repuesto", "Descripción": d_rep, "Cantidad": q_rep, "Unitario_Costo": float(p_final), "Total_Costo": float(p_final * q_rep)})
                                guardar_borrador()
                                st.rerun()
                                
                # UNIFICAMOS EL CARRITO
                if 'lista_particular' in st.session_state: sel_final.extend(st.session_state.lista_particular)
                if 'lista_repuestos' in st.session_state: sel_final.extend(st.session_state.lista_repuestos)
                
                # --- VISOR DEL CARRITO EN VIVO ---
                if sel_final:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("<div class='carrito-container'>", unsafe_allow_html=True)
                    st.markdown("### 🛒 Resumen del Carrito en Vivo")
                    
                    tn = sum(x['Total_Costo'] for x in sel_final)
                    iv = tn * 0.19
                    tf = tn + iv
                    
                    for idx, item in enumerate(sel_final):
                        c_desc, c_cant, c_tot, c_del = st.columns([5, 1, 2, 1], vertical_alignment="center")
                        c_desc.markdown(f"{item['Descripción']}")
                        c_cant.markdown(f"x{item['Cantidad']}")
                        c_tot.markdown(f"**{format_clp(item['Total_Costo'])}**")
                        
                        # Botones de eliminación inteligente
                        if item['Tipo'] == "matriz":
                            c_del.info("Editar Pestaña")
                        elif item['Tipo'] == "manual":
                            if c_del.button("🗑️", key=f"del_man_{idx}"):
                                st.session_state.lista_particular = [i for i in st.session_state.lista_particular if i != item]
                                guardar_borrador(); st.rerun()
                        elif item['Tipo'] == "repuesto":
                            if c_del.button("🗑️", key=f"del_rep_{idx}"):
                                st.session_state.lista_repuestos = [i for i in st.session_state.lista_repuestos if i != item]
                                guardar_borrador(); st.rerun()
                                
                    st.markdown("---")
                    c_s1, c_s2, c_s3 = st.columns(3)
                    c_s1.metric("SUB TOTAL", format_clp(tn))
                    c_s2.metric("I.V.A.", format_clp(iv))
                    c_s3.metric("TOTAL A COBRAR", format_clp(tf))
                    st.markdown("</div><br>", unsafe_allow_html=True)
                    
                    st.session_state.sel_final_cache = sel_final # Guardamos para el paso 3
                    
                    if st.button("Ir al Resumen Final y Generar PDF ➡️", type="primary", use_container_width=True):
                        st.session_state.sub_paso = 3
                        guardar_borrador()
                        st.rerun()

            # PASO 3: RESUMEN Y EMISIÓN
            elif st.session_state.sub_paso == 3:
                st.header("Paso 3: Emisión de Documento")
                if st.button("⬅️ Volver al Carrito de Trabajos"):
                    st.session_state.sub_paso = 2
                    guardar_borrador()
                    st.rerun()
                    
                sel_final = st.session_state.get('sel_final_cache', [])
                tn = sum(x['Total_Costo'] for x in sel_final)
                iv = tn * 0.19
                tf = tn + iv
                
                obs = st.text_area("Observaciones para el Taller/Cliente:")
                est = st.radio("Fase del Trabajo:", ("En Espera de Aprobación", "Trabajo Realizado"))
                
                st.markdown("---")
                
                if 'presupuesto_generado' not in st.session_state:
                    if st.button("💾 GUARDAR ORDEN Y GENERAR DOCUMENTO", type="primary", use_container_width=True):
                        with st.spinner("Conectando con Supabase..."):
                            try:
                                if p_in:
                                    supabase.table("directorio_vehiculos").upsert({"patente": p_in, "rut_facturacion": st.session_state.c_rut_fac, "marca": st.session_state.c_marca, "modelo": st.session_state.c_modelo}).execute()

                                sol_id = st.session_state.get('sol_activa')
                                if sol_id:
                                    corr_id = str(sol_id)
                                    pdf_b = generar_pdf_oficial(p_in, st.session_state.c_marca, st.session_state.c_modelo, st.session_state.c_cli_fac, st.session_state.c_rut_fac, sel_final, tn, False, est, st.session_state.c_us_final, obs, corr_id, st.session_state.get('c_nsap', ''))
                                    n_pdf = f"Presupuesto_{corr_id}.pdf"
                                    url_doc = subir_pdf_a_storage(n_pdf, pdf_b)
                                    supabase.table("historial_trabajos").update({
                                        "estado": "Generado", "total_clp": tf, "pdf_url": url_doc, 
                                        "origen_trabajo": st.session_state.c_origen, "usuario_final": st.session_state.c_us_final, "tarifa_aplicada": st.session_state.c_tarifa, "nombre_cliente_manual": st.session_state.c_cli_fac
                                    }).eq("id_cotizacion", sol_id).execute()
                                else:
                                    res = supabase.table("historial_trabajos").insert({
                                        "patente": p_in if p_in else None, "origen_trabajo": st.session_state.c_origen, "nombre_cliente_manual": st.session_state.c_cli_fac,
                                        "usuario_final": st.session_state.c_us_final, "tarifa_aplicada": st.session_state.c_tarifa,
                                        "estado": "Generado", "total_clp": tf, "creado_por": "Cristian"
                                    }).execute()
                                    corr_id = str(res.data[0]['id_cotizacion'])
                                    pdf_b = generar_pdf_oficial(p_in, st.session_state.c_marca, st.session_state.c_modelo, st.session_state.c_cli_fac, st.session_state.c_rut_fac, sel_final, tn, False, est, st.session_state.c_us_final, obs, corr_id, "")
                                    n_pdf = f"Presupuesto_{corr_id}.pdf"
                                    url_doc = subir_pdf_a_storage(n_pdf, pdf_b)
                                    supabase.table("historial_trabajos").update({"pdf_url": url_doc}).eq("id_cotizacion", corr_id).execute()
                                    
                                st.session_state['presupuesto_generado'] = {'pdf': pdf_b, 'nombre': n_pdf, 'url': url_doc}
                                eliminar_borrador() # Borrador cumplió su función
                                st.rerun()
                            except Exception as e_gen: st.error(f"Error: {e_gen}")
                else:
                    d = st.session_state['presupuesto_generado']
                    st.success("✅ Documento Oficial guardado en Supabase.")
                    st.download_button("📥 DESCARGAR PDF", d['pdf'], d['nombre'], "application/pdf")
                    if st.button("🏠 Finalizar y Volver al Inicio", type="primary"):
                        limpiar_sesion_cristian()
                        st.session_state.vista_taller = "Bandeja"
                        st.rerun()

    elif st.session_state.vista_taller == "Historial":
        st.title("🗃️ Registro General")
        df_todo = extraer_historial_completo()
        if not df_todo.empty:
            lupa = st.text_input("🔍 Buscar por Patente...").upper()
            if lupa: df_todo = df_todo[df_todo['patente'].str.contains(lupa, na=False)]
            
            t1, t2, t3 = st.tabs(["🟡 Por Enviar", "🔵 Enviados", "🟢 Aprobados (Marcar Realizado)"])
            with t1:
                for idx, r in df_todo[df_todo['estado'] == 'Generado'].iterrows():
                    ca, cb, cc = st.columns([4, 1.5, 1])
                    ca.write(f"📄 N° {r['id_cotizacion']} | Patente: {r['patente']} | Total: {format_clp(r['total_clp'])}")
                    if pd.notna(r.get('pdf_url')): cb.markdown(f"[👁️ Ver Documento]({r['pdf_url']})")
                    if cc.button("✉️ Marcar Enviado", key=f"e_{r['id_cotizacion']}"):
                        supabase.table("historial_trabajos").update({"estado": "Enviado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                        st.rerun()
            with t2:
                for idx, r in df_todo[df_todo['estado'] == 'Enviado'].iterrows():
                    ca, cb, cc = st.columns([4, 1.5, 1])
                    ca.write(f"🔵 N° {r['id_cotizacion']} | Patente: {r['patente']} | Total: {format_clp(r['total_clp'])}")
                    if pd.notna(r.get('pdf_url')): cb.markdown(f"[📥 Descargar]({r['pdf_url']})")
                    cc.info("Esperando Aprobación de Gabo")
            with t3:
                df_apr = df_todo[df_todo['estado'] == 'Aprobado']
                if not df_apr.empty:
                    for idx, r in df_apr.iterrows():
                        ca, cb, cc = st.columns([4, 1.5, 2])
                        ca.write(f"🟢 N° {r['id_cotizacion']} | Patente: {r['patente']} | Total: {format_clp(r['total_clp'])}")
                        if pd.notna(r.get('pdf_url')): cb.markdown(f"[📥 Descargar]({r['pdf_url']})")
                        if cc.button("🛠️ Marcar Realizado/Terminado", key=f"term_{r['id_cotizacion']}", type="primary"):
                            supabase.table("historial_trabajos").update({"estado": "Terminado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                            st.success("¡Trabajo finalizado en Taller!"); time.sleep(1); st.rerun()
                
                st.markdown("---")
                st.markdown("### Trabajos Históricos (Terminados)")
                df_fin = df_todo[df_todo['estado'] == 'Terminado'].copy()
                if not df_fin.empty:
                    df_fin['total_clp'] = df_fin['total_clp'].apply(lambda x: format_clp(x))
                    st.dataframe(df_fin[['id_cotizacion', 'patente', 'usuario_final', 'estado', 'total_clp']], use_container_width=True)
