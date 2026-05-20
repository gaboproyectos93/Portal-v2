import streamlit as st
import pandas as pd
import io
import os
from fpdf import FPDF
from datetime import datetime
import re
import json
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# ==========================================
st.set_page_config(page_title="Portal C.H. Automotriz V2", layout="wide")

COLOR_PRIMARIO = "#0A2540"
RUT_EMPRESA = "13.961.700-2" 
DIRECCION = "Francisco Pizarro 495, Padre las Casas"

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

# Estilos personalizados para el ecosistema profesional
st.markdown(f"""
<style>
    .stTabs [aria-selected='true'] {{ background-color: {COLOR_PRIMARIO} !important; color: white !important; font-weight: bold; border-radius: 4px; }}
    .stButton > button[kind='primary'] {{ background-color: {COLOR_PRIMARIO} !important; color: white !important; font-weight: bold; width: 100%; }}
    .card-requerido {{ background-color: #ffe6e6; padding: 15px; border-left: 5px solid #ff4d4d; border-radius: 4px; margin-bottom: 10px; }}
    .card-generado {{ background-color: #fff9e6; padding: 15px; border-left: 5px solid #ffcc00; border-radius: 4px; margin-bottom: 10px; }}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. GENERADOR DE PDF Y UTILS
# ==========================================
class PDF(FPDF):
    def __init__(self, correlativo=""): 
        super().__init__()
        self.correlativo = correlativo
    def header(self):
        self.set_xy(10, 10)
        self.set_font('Arial', 'B', 14)
        self.cell(100, 10, "C.H. SERVICIO AUTOMOTRIZ", 0, 0, 'L')
        self.set_xy(140, 10)
        self.set_text_color(220, 0, 0)
        self.cell(60, 10, f"PRESUPUESTO N° {self.correlativo}", 1, 1, 'C')
        self.set_text_color(0, 0, 0)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f"RUT: {RUT_EMPRESA} | {DIRECCION}", 0, 0, 'C')

def generar_pdf_v2(correlativo, patente, cliente, items, total):
    pdf = PDF(correlativo=correlativo)
    pdf.add_page()
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
    pdf.cell(0, 6, f"Vehículo/Identificación: {patente if patente else 'SIN PATENTE'}", 0, 1)
    pdf.cell(0, 6, f"Cliente: {cliente.upper()}", 0, 1)
    pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(130, 7, "Descripción", 1, 0, 'C')
    pdf.cell(20, 7, "Cant.", 1, 0, 'C')
    pdf.cell(40, 7, "Total", 1, 1, 'C')
    
    pdf.set_font('Arial', '', 10)
    for i in items:
        pdf.cell(130, 6, i['Descripción'].upper(), 1, 0, 'L')
        pdf.cell(20, 6, str(i['Cantidad']), 1, 0, 'C')
        pdf.cell(40, 6, f"${i['Total_Costo']:,.0f}", 1, 1, 'R')
        
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(150, 7, "TOTAL FINAL (CON IVA):", 0, 0, 'R')
    pdf.cell(40, 7, f"${total:,.0f}", 1, 1, 'R')
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. INTERACCIÓN CON CONECTORES (SUPABASE)
# ==========================================
def subir_pdf_a_storage(nombre_archivo, pdf_bytes):
    try:
        # Sube el archivo de forma directa al nuevo Bucket que creaste
        supabase.storage.from_("pdf_cotizaciones").upload(
            path=nombre_archivo,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf"}
        )
        # Rescata el link público permanente
        url = supabase.storage.from_("pdf_cotizaciones").get_public_url(nombre_archivo)
        return url
    except:
        return None

def registrar_solicitud_gabo(patente, cliente, origen, descripcion):
    try:
        # Deja la tarea guardada en el historial en estado 'Requerido'
        supabase.table("historial_trabajos").insert({
            "patente": patente if patente else None,
            "nombre_cliente_manual": cliente,
            "origen_trabajo": origen,
            "descripcion_requerimiento": descripcion,
            "estado": "Requerido",
            "creado_por": "Gabo"
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al registrar requerimiento: {e}")
        return False

def extraer_historial_completo():
    try:
        res = supabase.table("historial_trabajos").select("*").order("id_cotizacion", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except:
        return pd.DataFrame()

# ==========================================
# 4. SISTEMA DE LOGIN / CONTROL DE ACCESO
# ==========================================
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

if st.session_state.usuario is None:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write("")
        st.write("")
        st.title("🔐 Acceso al Sistema V2")
        user_type = st.selectbox("Selecciona tu Perfil", ["--- Seleccione ---", "Gabriel Poblete (Planificación)", "Christian Herrera (Taller)"])
        password = st.text_input("Contraseña de Acceso", type="password")
        
        if st.button("Ingresar al Portal", type="primary"):
            if user_type == "Gabriel Poblete (Planificación)" and password == "gabo2026":
                st.session_state.usuario = "Gabo"
                st.rerun()
            elif user_type == "Christian Herrera (Taller)" and password == "cristian2026":
                st.session_state.usuario = "Cristian"
                st.rerun()
            else:
                st.error("Credenciales Incorrectas. Inténtalo nuevamente.")
    st.stop()

# Botón para cerrar sesión en la barra lateral
with st.sidebar:
    st.markdown(f"**Usuario Conectado:** {st.session_state.usuario}")
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state.usuario = None
        st.rerun()

# ==========================================
# 5. DESARROLLO DE VISTAS SEGMENTADAS
# ==========================================

# ------------------------------------------
# A. PANTALLA EXCLUSIVA DE GABO (PLANIFICADOR)
# ------------------------------------------
if st.session_state.usuario == "Gabo":
    st.title("🎛️ Centro de Operaciones y Planificación (Gabo)")
    
    with st.expander("➕ Solicitar Nueva Cotización a Cristian", expanded=True):
        c1, c2, c3 = st.columns([1.5, 2, 1.5])
        pat = c1.text_input("Patente del Vehículo (Opcional)").upper()
        cli = c2.text_input("Nombre de la Institución o Cliente Particular")
        origen = c3.selectbox("Canal / Procedencia", ["Kaufmann", "Propio Cristian"])
        desc = st.text_area("¿Qué operaciones específicas debe evaluar Cristian? (Instrucciones)")
        
        if st.button("Enviar Orden de Cotización al Taller", type="primary"):
            if cli and desc:
                if registrar_solicitud_gabo(pat, cli, origen, desc):
                    st.success(f"🚀 Solicitud enviada exitosamente. Cristian la verá en su bandeja como 'Por Generar'.")
                    time.sleep(1.5)
                    st.rerun()
            else:
                st.warning("Por favor rellena el nombre del cliente y las instrucciones del trabajo.")

    st.markdown("---")
    st.subheader("📊 Monitoreo Global de Trabajos")
    df_global = extraer_historial_completo()
    
    if not df_global.empty:
        # Buscador General estilo Lupa
        busqueda = st.text_input("🔍 Buscar por Patente o Cliente...").upper()
        if busqueda:
            df_global = df_global[
                df_global['patente'].str.contains(busqueda, na=False) | 
                df_global['nombre_cliente_manual'].str.contains(busqueda, na=False, case=False)
            ]
        st.dataframe(df_global[['id_cotizacion', 'patente', 'nombre_cliente_manual', 'origen_trabajo', 'estado', 'total_clp', 'pdf_url']], use_container_width=True)
    else:
        st.info("No hay registros en el historial todavía.")

# ------------------------------------------
# B. PANTALLA EXCLUSIVA DE CRISTIAN (EJECUTOR)
# ------------------------------------------
elif st.session_state.usuario == "Cristian":
    st.title("🔧 Panel de Control del Taller (Cristian)")
    
    tab_pendientes, tab_historial = st.tabs(["📥 Órdenes por Generar", "🗂️ Historial y Descarga de PDFs"])
    
    # PESTAÑA 1: SOLICITUDES DE GABO
    with tab_pendientes:
        st.subheader("Requerimientos asignados por Gabo")
        df_todo = extraer_historial_completo()
        
        if not df_todo.empty and 'estado' in df_todo.columns:
            df_req = df_todo[df_todo['estado'] == 'Requerido']
            if not df_req.empty:
                for idx, fila in df_req.iterrows():
                    st.markdown(f"""
                    <div class="card-requerido">
                        <h4>🚗 Vehículo: {fila['patente'] if fila['patente'] else 'PROYECTO SIN PATENTE'} | Cliente: {fila['nombre_cliente_manual']}</h4>
                        <p><strong>Instrucciones de Gabo:</strong> {fila['descripcion_requerimiento']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Activar mini-cotizador para responder a Gabo
                    with st.expander(f"⚙️ Cotizar Solicitud N° {fila['id_cotizacion']}"):
                        precio = st.number_input("Monto Total Neto Evaluado ($)", min_value=0, step=10000, key=f"p_{fila['id_cotizacion']}")
                        desc_trabajo = st.text_input("Detalle breve del trabajo realizado", key=f"d_{fila['id_cotizacion']}")
                        
                        if st.button("Finalizar y Guardar PDF en la Nube", key=f"b_{fila['id_cotizacion']}"):
                            total_con_iva = int(precio * 1.19)
                            items_mock = [{"Descripción": desc_trabajo, "Cantidad": 1, "Total_Costo": total_con_iva}]
                            
                            # Genera el PDF binario
                            pdf_data = generar_pdf_exacto = generar_pdf_v2(str(fila['id_cotizacion']), fila['patente'], fila['nombre_cliente_manual'], items_mock, total_con_iva)
                            
                            # Guarda el PDF en el bucket de Storage
                            nombre_archivo = f"Cotizacion_{fila['id_cotizacion']}.pdf"
                            url_publica = subir_pdf_a_storage(nombre_archivo, pdf_data)
                            
                            # Actualiza el registro convirtiéndolo en 'Generado'
                            if url_publica:
                                supabase.table("historial_trabajos").update({
                                    "estado": "Generado",
                                    "total_clp": total_con_iva,
                                    "pdf_url": url_publica
                                }).eq("id_cotizacion", fila['id_cotizacion']).execute()
                                st.success("✅ ¡Cotización procesada, guardada en la base de datos y PDF almacenado en la nube!")
                                time.sleep(1.5)
                                st.rerun()
            else:
                st.info("¡Al día! No tienes solicitudes pendientes de cotizar.")
        else:
            st.info("Sin solicitudes pendientes.")

    # PESTAÑA 2: EL CONTROL HISTÓRICO CON BUSCADOR Y SECCIONES
    with tab_historial:
        st.subheader("🗃️ Registro General de Presupuestos")
        
        if not df_todo.empty:
            # Lupa de búsqueda
            lupa = st.text_input("🔍 Digita una Patente o Cliente para buscar en el historial...").upper()
            df_filtrado = df_todo.copy()
            if lupa:
                df_filtrado = df_filtrado[
                    df_filtrado['patente'].str.contains(lupa, na=False) | 
                    df_filtrado['nombre_cliente_manual'].str.contains(lupa, na=False, case=False)
                ]
            
            # Segmentación por secciones solicitadas
            sec_generadas, sec_enviadas, sec_terminadas = st.tabs(["🟡 Solo Generadas", "🔵 Enviadas al Cliente", "🟢/⚫ Aprobadas y Terminadas"])
            
            with sec_generadas:
                df_gen = df_filtrado[df_filtrado['estado'] == 'Generado']
                if not df_gen.empty:
                    for idx, r in df_gen.iterrows():
                        c_a, c_b, c_c = st.columns([3, 1.5, 1])
                        c_a.write(f"📄 **N° {r['id_cotizacion']}** | Patente: {r['patente'] if r['patente'] else 'S/P'} | Cliente: {r['nombre_cliente_manual']} | **Total: ${r['total_clp']:,.0f}**")
                        if r['pdf_url']:
                            c_b.markdown(f"[👁️ Ver PDF en Nube]({r['pdf_url']})")
                        if c_c.button("✉️ Marcar Enviado", key=f"env_{r['id_cotizacion']}"):
                            supabase.table("historial_trabajos").update({"estado": "Enviado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                            st.rerun()
                else:
                    st.write("No hay cotizaciones retenidas en este estado.")
                    
            with sec_enviadas:
                df_env = df_filtrado[df_filtrado['estado'] == 'Enviado']
                if not df_env.empty:
                    for idx, r in df_env.iterrows():
                        c_a, c_b, c_c = st.columns([3, 1.5, 1])
                        c_a.write(f"🔵 **N° {r['id_cotizacion']}** | Patente: {r['patente'] if r['patente'] else 'S/P'} | Cliente: {r['nombre_cliente_manual']} | **Total: ${r['total_clp']:,.0f}**")
                        if r['pdf_url']:
                            c_b.markdown(f"[📥 Descargar PDF]({r['pdf_url']})")
                        if c_c.button("🟢 Aprobar", key=f"apr_{r['id_cotizacion']}"):
                            supabase.table("historial_trabajos").update({"estado": "Aprobado"}).eq("id_cotizacion", r['id_cotizacion']).execute()
                            st.rerun()
                else:
                    st.write("No hay cotizaciones marcadas como enviadas.")
                    
            with sec_terminadas:
                df_term = df_filtrado[df_filtrado['estado'].isin(['Aprobado', 'Terminado'])]
                if not df_term.empty:
                    st.dataframe(df_term[['id_cotizacion', 'patente', 'nombre_cliente_manual', 'estado', 'total_clp', 'pdf_url']], use_container_width=True)
                else:
                    st.write("No hay trabajos aprobados o terminados aún.")
        else:
            st.info("El historial financiero está vacío.")
