# app.py
# ==============================================================================
# SERVIDOR MAESTRO DE GESTIÓN: LA TRIBU DE LOS LIBRES (VERSIÓN 2026 - ULTRA)
# ==============================================================================
# Este archivo centraliza la configuración del entorno, la inicialización de
# extensiones y el motor de fidelización automática por cumpleaños.
# ==============================================================================

import os
import logging
from datetime import datetime, timedelta, timezone

# --- FRAMEWORK Y EXTENSIONES DE SISTEMA ---
from flask import Flask, redirect, request
from flask_login import LoginManager, current_user
from sqlalchemy import extract

# --- IMPORTACIÓN DE INFRAESTRUCTURA DE DATOS ---
from db import db, bcrypt, User, Member, Event, Booking, PointLog, AdminNotification, SystemConfig

app = Flask(__name__)

# --- CONFIGURACIÓN MAESTRA DEL ENTORNO ---
# Clave maestra para seguridad de sesiones, cookies y protección CSRF.
app.config['SECRET_KEY'] = 'la_tribu_master_key_2026_full_integration_v6_final_ultimate_pro'

# Definición del motor de persistencia SQLite y optimización de transacciones.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- CONFIGURACIÓN DE RUTA DE IMÁGENES ---
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads', 'flyers')

# Protocolo de arranque: Verificación de infraestructura de carpetas físicas.
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        print(f"Infraestructura de archivos inicializada en: {app.config['UPLOAD_FOLDER']}")
    except Exception as e:
        print(f"ALERTA CRÍTICA: Fallo al crear carpetas de sistema: {e}")

# Configuración de Logging para auditoría técnica y depuración profesional.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- INICIALIZACIÓN DE COMPONENTES CORE ---
db.init_app(app)
bcrypt.init_app(app)

# Gestión de Seguridad y Sesiones (Flask-Login).
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
login_manager.login_message = "Acceso restringido. Por favor, identifíquese con su PIN administrativo."

@login_manager.user_loader
def load_user(user_id):
    """
    Función de recuperación de identidad para mantener sesiones activas.
    Busca el usuario en la base de datos basándose en el ID de sesión.
    """
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError, Exception):
        return None

# --- SEGURIDAD: FORZAR HTTPS (REDIRECCIÓN AUTOMÁTICA) ---
@app.before_request
def force_https():
    """Redirige todo el tráfico HTTP a HTTPS automáticamente."""
    if request.headers.get('X-Forwarded-Proto') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

# --- CONTEXT PROCESSOR (SISTEMA DE FIDELIZACIÓN 'BRUTAL' AUTOMÁTICO) ---
@app.context_processor
def inject_global_vars():
    """
    Inyecta datos cruciales en todas las plantillas y ejecuta el proceso 
    automático de bonos de 500 pts por cumpleaños con registro en PointLog.
    """
    from rutas import get_config, calculate_age, MESES_ES

    # --- CORRECCIÓN DE ZONA HORARIA (COSTA RICA UTC-6) ---
    ahora_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cr_now = ahora_utc - timedelta(hours=6)
    today = cr_now.date()
    
    sinpe_number = get_config('sinpe_number', '86529837')
    sinpe_name = get_config('sinpe_name', 'Jenny Ceciliano Cordoba')
    
    # Optimizamos: La lógica de cumpleaños solo se procesa en páginas clave para no saturar el servidor
    birthdays_today = []
    if request.endpoint in ['main.home', 'main.dashboard', 'perfil.ver_perfil']:
        birthdays_today = Member.query.filter(
            extract('month', Member.birth_date) == today.month,
            extract('day', Member.birth_date) == today.day
        ).all()

        commit_needed = False
        for member in birthdays_today:
            if member.ultimo_regalo_bday != today.year:
                monto_bono = 500
                member.puntos_totales = (member.puntos_totales or 0) + monto_bono
                member.ultimo_regalo_bday = today.year
                
                db.session.add(PointLog(
                    member_id=member.id,
                    transaction_type='Bono Cumpleaños',
                    description=f'Regalo de La Tribu: Cumpleaños {today.year}',
                    amount=monto_bono
                ))
                
                db.session.add(AdminNotification(
                    category='info',
                    title='Cumpleaños Automático',
                    message=f'El sistema regaló {monto_bono} pts a {member.nombre}.',
                    action_link=f'/admin/puntos/miembro/{member.id}'
                ))
                commit_needed = True
        
        if commit_needed:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Fallo en transacción automática de fidelización: {e}")

    # Lógica de notificaciones global para el Navbar
    admin_unread_count = 0
    admin_recent_notifications = []
    
    if current_user.is_authenticated and current_user.is_superuser:
        admin_unread_count = AdminNotification.query.filter_by(is_read=False).count()
        admin_recent_notifications = AdminNotification.query.order_by(AdminNotification.created_at.desc()).limit(5).all()

    return dict(
        meses_lista=MESES_ES, 
        calculate_age=calculate_age, 
        now=cr_now,
        birthdays_today=birthdays_today,
        admin_unread_count=admin_unread_count,
        admin_recent_notifications=admin_recent_notifications,
        sinpe_number=sinpe_number,
        sinpe_name=sinpe_name
    )

# --- ARQUITECTURA MODULAR DE BLUEPRINTS ---
from rutas import auth_bp, main_bp
from logistica import calendar_bp

# Registro seguro de Blueprints opcionales
try:
    from puntos import puntos_bp
    app.register_blueprint(puntos_bp)
except ImportError:
    logger.warning("Blueprint 'puntos' no encontrado. Continuando sin este módulo.")

try:
    from perfil import perfil_bp
    app.register_blueprint(perfil_bp)
except ImportError:
    logger.warning("Blueprint 'perfil' no encontrado. Continuando sin este módulo.")

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)

# --- INICIALIZACIÓN DE LA INFRAESTRUCTURA DE DATOS ---
with app.app_context():
    # 1. Creación de tablas según modelos maestros
    db.create_all()
    
    # 2. Inicialización de configuración SINPE base
    if not SystemConfig.query.filter_by(key='sinpe_number').first():
        db.session.add(SystemConfig(key='sinpe_number', value='86529837'))
        db.session.add(SystemConfig(key='sinpe_name', value='Jenny Ceciliano Cordoba'))

    # 3. Lista de Administradores Líderes (Garantía de acceso inicial)
    masters = [
        {"email": "kenth1977@gmail.com", "pass": "CR129x7848n"},
        {"email": "lthikingcr@gmail.com", "pass": "CR129x7848n"}
    ]
    for m in masters:
        if not User.query.filter_by(email=m['email']).first():
            hashed_pw = bcrypt.generate_password_hash(m['pass']).decode('utf-8')
            user = User(email=m['email'], password=hashed_pw, is_superuser=True)
            db.session.add(user)
    
    db.session.commit()
    logger.info("Infraestructura de datos y administradores verificada con éxito.")

if __name__ == '__main__':
    app.run(debug=True)