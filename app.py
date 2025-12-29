# ==============================================================================
# SERVIDOR MAESTRO DE GESTIÓN: LA TRIBU DE LOS LIBRES (VERSIÓN 2026 - ULTRA)
# ==============================================================================
# Este archivo centraliza la lógica de negocio, el sistema de fidelidad "Brutal"
# y la gestión logística integral. Está diseñado para una trazabilidad total
# mediante el uso de cronogramas transaccionales (PointLog).
# VERSIÓN: 6.0 INTEGRACIÓN TOTAL (650+ LÍNEAS)
# ==============================================================================

import os
import csv
import calendar
import random
import logging
import io
from datetime import datetime, date

# --- FRAMEWORK Y EXTENSIONES DE SISTEMA ---
from flask import (
    Flask, render_template, redirect, url_for, request, 
    flash, Blueprint, jsonify, Response, make_response, abort
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user
)
from werkzeug.utils import secure_filename
from sqlalchemy import extract, desc, func

# --- IMPORTACIÓN DE MODELOS E INFRAESTRUCTURA DE DATOS ---
# Importamos la arquitectura desde db.py para evitar ciclos de importación.
# Los modelos requeridos son: User, Member, Event, Booking y PointLog.
from db import db, bcrypt, User, Member, Event, Booking, PointLog

app = Flask(__name__)

# --- CONFIGURACIÓN MAESTRA DEL ENTORNO ---
# Clave maestra para seguridad de sesiones, cookies y protección CSRF.
app.config['SECRET_KEY'] = 'la_tribu_master_key_2026_full_integration_v6_final_ultimate_pro'

# Definición del motor de persistencia SQLite y optimización de transacciones.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración del motor de almacenamiento para Flyers (Imágenes).
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'flyers')

# Protocolo de arranque: Verificación de infraestructura de carpetas físicas.
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        print("Infraestructura de archivos inicializada correctamente.")
    except Exception as e:
        print(f"ALERTA CRÍTICA: Fallo al crear carpetas de sistema: {e}")

# Configuración de Logging para auditoría técnica y depuración profesional.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Mapeo universal de meses para la capa de presentación en español.
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

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
        return User.query.get(int(user_id))
    except (TypeError, ValueError, Exception):
        return None

# --- UTILIDADES DE PROCESAMIENTO Y LÓGICA DE NEGOCIO ---

def calculate_age(born):
    """
    Algoritmo de precisión para determinar la edad de los aventureros.
    Crucial para logística de seguros y personalización de rutas.
    """
    if not born:
        return "N/A"
    today = date.today()
    try:
        # Se descuenta un año si la fecha actual es anterior al día/mes de nacimiento.
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception as e:
        logger.error(f"Fallo en algoritmo de cálculo de edad: {e}")
        return "N/A"

def to_date(date_str):
    """
    Transformador robusto de cadenas de texto ISO a objetos Date de Python.
    Maneja inputs de formularios HTML y asegura la integridad en la base de datos.
    """
    if not date_str:
        return None
    try:
        # Formato ISO estándar: YYYY-MM-DD
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        # En caso de error, retorna None para evitar caídas del servidor.
        return None

# --- CONTEXT PROCESSOR (SISTEMA DE FIDELIZACIÓN 'BRUTAL' AUTOMÁTICO) ---

@app.context_processor
def inject_global_vars():
    """
    Inyecta datos cruciales en todas las plantillas y ejecuta el proceso 
    automático de bonos de 500 pts por cumpleaños con registro en PointLog.
    Esto ocurre cada vez que un usuario interactúa con la plataforma.
    """
    today = date.today()
    
    # Identificación de miembros que celebran su día hoy.
    birthdays_today = Member.query.filter(
        extract('month', Member.birth_date) == today.month,
        extract('day', Member.birth_date) == today.day
    ).all()

    # Lógica de asignación automática de puntos: Blindada para una vez por año.
    commit_needed = False
    for member in birthdays_today:
        if member.ultimo_regalo_bday != today.year:
            monto_bono = 500
            member.puntos_totales += monto_bono
            member.ultimo_regalo_bday = today.year
            
            # CRÍTICO: Se crea la línea de auditoría en el libro mayor de puntos.
            db.session.add(PointLog(
                member_id=member.id,
                transaction_type='Bono Cumpleaños',
                description=f'Regalo de La Tribu: Cumpleaños {today.year}',
                amount=monto_bono
            ))
            commit_needed = True
            logger.info(f"Bono de 500 pts acreditado a {member.nombre} ({member.pin})")
    
    if commit_needed:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Fallo en transacción automática de fidelización: {e}")

    # Cálculo dinámico del contador para el buscador de meses en la Home.
    search_month_idx = request.args.get('search_month', type=int)
    target_month = search_month_idx if search_month_idx is not None else today.month
    count = Event.query.filter(extract('month', Event.event_date) == target_month).count()
    
    return dict(
        month_activity_count=count, 
        meses_lista=MESES_ES, 
        calculate_age=calculate_age, 
        now=datetime.now(),
        birthdays_today=birthdays_today
    )

# --- ARQUITECTURA MODULAR DE BLUEPRINTS ---
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
calendar_bp = Blueprint('calendar_view', __name__)

# ==============================================================================
# SECCIÓN 1: GESTIÓN DE ACCESO (BLUEPRINT: AUTH)
# ==============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Ruta administrativa para el ingreso de guías líderes."""
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        # Validación con hashing Bcrypt.
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('¡Acceso verificado! Bienvenido líder al panel de control.', 'success')
            return redirect(url_for('main.dashboard'))
        
        flash('Credenciales incorrectas. Verifique su PIN o contraseña.', 'danger')
        
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Finaliza la sesión administrativa de forma segura."""
    logout_user()
    flash('Sesión administrativa cerrada. ¡Nos vemos en la ruta!', 'info')
    return redirect(url_for('main.home'))

# ==============================================================================
# SECCIÓN 2: VISTAS PRINCIPALES Y PANEL DE CONTROL (BLUEPRINT: MAIN)
# ==============================================================================

@main_bp.route('/')
def home():
    """Catálogo público inteligente. Filtra rutas por mes y cercanía cronológica."""
    search_month = request.args.get('search_month', type=int)
    query = Event.query
    
    if search_month:
        query = query.filter(extract('month', Event.event_date) == search_month)
    
    # Mostrar primero las expediciones más próximas a ocurrir.
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    """Panel central con métricas transaccionales, ranking y actividad en vivo."""
    if not current_user.is_superuser:
        flash('Acceso denegado. Se requieren permisos de superusuario.', 'danger')
        return redirect(url_for('main.home'))
    
    # Recopilación de estadísticas dinámicas.
    stats = {
        'total': Event.query.count(),
        'active': Event.query.filter_by(status='Activa').count(),
        'members_count': Member.query.count(),
        'birthdays_count': Member.query.filter(
            extract('month', Member.birth_date) == date.today().month,
            extract('day', Member.birth_date) == date.today().day
        ).count()
    }
    
    # ACTIVIDAD RECIENTE: Obtenemos reservas activas para monitorear ingresos.
    bookings = Booking.query.filter_by(status='Activo').order_by(Booking.created_at.desc()).limit(50).all()
    # TOP 10 Aventureros según su fidelidad acumulada.
    ranking = Member.query.order_by(Member.puntos_totales.desc()).limit(10).all()
    
    return render_template('dashboard.html', stats=stats, bookings=bookings, ranking=ranking)

@main_bp.route('/admin/booking/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """
    SISTEMA DE RETIRO CON TRAZABILIDAD (POINTLOG):
    Esta función es el eje de la transparencia. No borra el registro de la BD.
    Marca el estado como 'Retirado' y genera una línea NEGATIVA en el cronograma.
    Así, el aventurero ve en su historial que se retiró y por qué bajó su saldo.
    """
    booking = Booking.query.get_or_404(booking_id)
    member = booking.member
    event = booking.event
    
    if booking.status == 'Retirado':
        flash('Este registro ya consta como retirado en el historial.', 'info')
        return redirect(request.referrer)
    
    try:
        # Puntos a descontar: lo que el evento valía en el momento de inscripción.
        pts_a_quitar = booking.points_at_registration or event.points_reward or 10
        
        # 1. Actualización del Saldo General (Campo de Caché).
        member.puntos_totales = max(0, member.puntos_totales - pts_a_quitar)
        
        # 2. Generación del Registro en el Cronograma de Puntos (Auditoría).
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Retiro',
            description=f'Deducción por retiro: {event.title}',
            amount=-pts_a_quitar, # IMPACTO NEGATIVO.
            booking_id=booking.id
        ))
        
        # 3. Persistencia del cambio de estado.
        booking.status = 'Retirado'
        # Actualizamos la fecha para reflejar el momento del retiro.
        booking.created_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Participación anulada correctamente para {member.nombre}. Se debitaron {pts_a_quitar} puntos.', 'warning')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo en proceso de retiro ID {booking_id}: {e}")
        flash(f'Error al procesar el retiro contable: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('main.dashboard'))

@main_bp.route('/admin/member/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    """Eliminación irreversible de un miembro y todo su historial de la base de datos."""
    member = Member.query.get_or_404(member_id)
    try:
        nombre_m = member.nombre
        db.session.delete(member)
        db.session.commit()
        flash(f'El miembro {nombre_m} ha sido removido definitivamente del sistema.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo crítico eliminando miembro ID {member_id}: {e}")
        flash(f'No se pudo eliminar al miembro: {str(e)}', 'danger')
        
    return redirect(url_for('puntos.historial_global'))

# ==============================================================================
# SECCIÓN 3: AUDITORÍA Y AJUSTES MANUALES (ULTRA MASTER)
# ==============================================================================

@main_bp.route('/admin/member/adjust_points', methods=['POST'])
@login_required
def adjust_points():
    """
    Permite al administrador premiar o penalizar puntos manualmente.
    Crea obligatoriamente una entrada en el cronograma (PointLog) con el motivo.
    """
    if not current_user.is_superuser: abort(403)
    
    member_id = request.form.get('member_id', type=int)
    amount = request.form.get('amount', type=int)
    reason = request.form.get('reason', 'Ajuste manual administrativo')
    
    member = Member.query.get_or_404(member_id)
    try:
        # Sincronización de Saldo.
        member.puntos_totales += amount
        # Registro Transactional.
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Ajuste Manual',
            description=reason,
            amount=amount
        ))
        db.session.commit()
        flash(f'Estado de cuenta de {member.nombre} ajustado en {amount} puntos.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo en ajuste manual: {e}")
        flash(f'Error al aplicar el ajuste: {str(e)}', 'danger')
    return redirect(request.referrer)

@main_bp.route('/admin/member/integrity_check/<int:member_id>')
@login_required
def integrity_check(member_id):
    """
    AUDITORÍA DE INTEGRIDAD:
    Recalcula el saldo real sumando línea por línea todos los logs.
    Repara el saldo en Member.puntos_totales si existe discrepancia.
    """
    member = Member.query.get_or_404(member_id)
    # Suma transaccional real.
    real_sum = db.session.query(func.sum(PointLog.amount)).filter(PointLog.member_id == member.id).scalar() or 0
    
    if member.puntos_totales != real_sum:
        desfase = real_sum - member.puntos_totales
        member.puntos_totales = real_sum
        db.session.commit()
        flash(f'Integridad corregida. Se encontró un desfase de {desfase} pts.', 'info')
    else:
        flash('El estado de cuenta es 100% íntegro.', 'success')
    return redirect(request.referrer)

@main_bp.route('/admin/event/export/<int:event_id>')
@login_required
def export_participants(event_id):
    """
    HERRAMIENTA LOGÍSTICA PARA GUÍAS:
    Genera un archivo CSV con la lista de participantes activos para uso offline.
    """
    event = Event.query.get_or_404(event_id)
    active_list = Booking.query.filter_by(event_id=event.id, status='Activo').all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['AVENTURERO', 'TELÉFONO', 'PIN', 'EDAD', 'FECHA INSCRIPCIÓN'])
    
    for b in active_list:
        age = calculate_age(b.member.birth_date)
        writer.writerow([
            f"{b.nombre} {b.apellido1}", 
            b.telefono, 
            b.pin, 
            age, 
            b.created_at.strftime('%d/%m/%Y')
        ])
        
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=logistica_tribu_{event.id}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

# ==============================================================================
# SECCIÓN 4: API ENDPOINTS Y REGISTRO INTELIGENTE
# ==============================================================================

@main_bp.route('/api/lookup/<pin>')
def api_lookup(pin):
    """Endpoint AJAX para consulta instantánea de identidad mediante PIN."""
    member = Member.query.filter_by(pin=pin).first()
    if member:
        return jsonify({
            'success': True,
            'id': member.id,
            'nombre': member.nombre,
            'apellido1': member.apellido1,
            'apellido2': member.apellido2,
            'telefono': member.telefono,
            'puntos': member.puntos_totales,
            'birth_date': member.birth_date.strftime('%Y-%m-%d') if member.birth_date else None
        })
    return jsonify({'success': False, 'error': 'El PIN ingresado no está en La Tribu.'})

@main_bp.route('/api/reserve', methods=['POST'])
def api_reserve():
    """
    LÓGICA MAESTRA DE INSCRIPCIÓN:
    Esta función es el cerebro del sistema. Orquesta la creación de miembros,
    la gestión de reactivaciones, suma de puntos y creación de logs de auditoría.
    GARANTIZA la creación de Booking para visibilidad en el Dashboard.
    """
    data = request.json
    try:
        event = Event.query.get_or_404(data['event_id'])
        today = date.today()
        member = None
        
        # Búsqueda por PIN para respetar la identidad y saldo de puntos.
        if data.get('pin'):
            member = Member.query.filter_by(pin=data.get('pin')).first()

        if not member:
            # FLUJO: NUEVO AVENTURERO (Creación e Identidad).
            while True:
                new_pin = str(random.randint(100000, 999999))
                if not Member.query.filter_by(pin=new_pin).first():
                    break
            
            b_date = to_date(data.get('birth_date'))
            
            # --- BONO DE BIENVENIDA (CONFIGURACIÓN) ---
            WELCOME_BONUS = 100  # Puntos regalados por primera inscripción
            event_points = event.points_reward or 10
            
            # Cálculo inicial de puntos: Evento + Bienvenida
            pts_ganados = event_points + WELCOME_BONUS
            reg_year_bono = 0
            
            # Bono sorpresa si el registro inaugural coincide con su cumpleaños.
            if b_date and b_date.month == today.month and b_date.day == today.day:
                pts_ganados += 500
                reg_year_bono = today.year

            member = Member(
                pin=new_pin, 
                nombre=data['nombre'], 
                apellido1=data['apellido1'], 
                apellido2=data.get('apellido2', ''),
                telefono=data['telefono'], 
                birth_date=b_date, 
                puntos_totales=pts_ganados,
                ultimo_regalo_bday=reg_year_bono
            )
            db.session.add(member)
            db.session.flush() # Sincronizar ID para crear el log y el booking.
            
            # REGISTRO TRANSACTIONAL 1: Inscripción al evento.
            db.session.add(PointLog(
                member_id=member.id,
                transaction_type='Inscripción',
                description=f'Registro inicial en: {event.title}',
                amount=event_points
            ))
            
            # REGISTRO TRANSACTIONAL 2: Bono de Bienvenida.
            db.session.add(PointLog(
                member_id=member.id,
                transaction_type='Bono Bienvenida',
                description='Regalo único por unirse a La Tribu',
                amount=WELCOME_BONUS
            ))
            
            # REGISTRO TRANSACTIONAL 3: Bono Cumpleaños (si aplica).
            if reg_year_bono > 0:
                db.session.add(PointLog(
                    member_id=member.id,
                    transaction_type='Bono Cumpleaños',
                    description='¡Bono sorpresa por cumpleaños!',
                    amount=500
                ))
        else:
            # FLUJO: MIEMBRO HISTÓRICO (Actualización de Estado).
            existing_booking = Booking.query.filter_by(member_id=member.id, event_id=event.id).first()
            val_pts = event.points_reward or 10
            
            if existing_booking:
                if existing_booking.status == 'Activo':
                    return jsonify({'success': False, 'error': 'Usted ya posee un cupo activo en esta ruta.'})
                else:
                    # REACTIVACIÓN: El usuario se retiró previamente pero decide volver.
                    existing_booking.status = 'Activo'
                    existing_booking.created_at = datetime.utcnow()
                    member.puntos_totales += val_pts
                    
                    db.session.add(PointLog(
                        member_id=member.id,
                        transaction_type='Inscripción',
                        description=f'Reactivación de cupo: {event.title}',
                        amount=val_pts,
                        booking_id=existing_booking.id
                    ))
                    db.session.commit()
                    return jsonify({'success': True, 'pin': member.pin, 'puntos': member.puntos_totales})

            # Inscribir miembro existente en actividad nueva.
            member.puntos_totales += val_pts
            db.session.add(PointLog(
                member_id=member.id,
                transaction_type='Inscripción',
                description=f'Inscripción: {event.title}',
                amount=val_pts
            ))

        # --- CRÍTICO: CREACIÓN DEL OBJETO BOOKING PARA EL DASHBOARD ---
        # Esto asegura que el usuario aparezca en la tabla de "Actividad Reciente".
        new_booking = Booking(
            member_id=member.id, 
            event_id=event.id, 
            pin=member.pin,
            nombre=member.nombre, 
            apellido1=member.apellido1, 
            telefono=member.telefono,
            points_at_registration=event.points_reward or 10,
            status='Activo'
        )
        db.session.add(new_booking)
        
        # Verificación de bono anual de cumpleaños para miembros existentes.
        if member.birth_date and member.birth_date.month == today.month and member.birth_date.day == today.day:
            if member.ultimo_regalo_bday != today.year:
                member.puntos_totales += 500
                member.ultimo_regalo_bday = today.year
                db.session.add(PointLog(
                    member_id=member.id,
                    transaction_type='Bono Cumpleaños',
                    description=f'Bono anual por natalicio ({today.year})',
                    amount=500
                ))

        db.session.commit()
        return jsonify({'success': True, 'pin': member.pin, 'puntos': member.puntos_totales})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo crítico en api_reserve: {e}")
        return jsonify({'success': False, 'error': f"Fallo en servidor: {str(e)}"})

# ==============================================================================
# SECCIÓN 5: GESTIÓN LOGÍSTICA DE CALENDARIO Y EVENTOS (BLUEPRINT: CALENDAR)
# ==============================================================================

@calendar_bp.route('/admin/calendar')
@login_required
def view():
    """Generador de cuadrícula administrativa mensual con logística detallada."""
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    if month > 12: month = 1; year += 1
    elif month < 1: month = 12; year -= 1

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    
    events = Event.query.all()
    monthly_birthdays = Member.query.filter(extract('month', Member.birth_date) == month).all()
    
    return render_template('calendar.html', 
                           weeks=weeks, year=year, month=month, 
                           month_name=MESES_ES[month],
                           events=events,
                           monthly_birthdays=monthly_birthdays)

@calendar_bp.route('/admin/event/add', methods=['POST'])
@login_required
def add_event():
    """Publica una nueva expedición procesando los 21 campos logísticos del sistema."""
    file = request.files.get('flyer')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    
    if filename:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    try:
        new_ev = Event(
            title=request.form.get('title'),
            flyer=filename,
            currency=request.form.get('currency', '¢'),
            price=float(request.form.get('price') or 0),
            points_reward=int(request.form.get('points_reward') or 10),
            activity_type=request.form.get('activity_type'),
            duration_days=int(request.form.get('duration_days') or 1),
            event_date=to_date(request.form.get('event_date')),
            end_date=to_date(request.form.get('end_date')),
            departure_point=request.form.get('departure_point'),
            departure_time=request.form.get('departure_time'),
            difficulty=request.form.get('difficulty'),
            distance=request.form.get('distance'),
            capacity=int(request.form.get('capacity') or 0),
            reservation_fee=request.form.get('reservation_fee'),
            description=request.form.get('description'),
            pickup_point=request.form.get('pickup_point'),
            status=request.form.get('status') or 'Activa',
            moved_date=to_date(request.form.get('moved_date'))
        )
        db.session.add(new_ev)
        db.session.commit()
        flash('¡Aventura publicada con éxito!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo técnico creando expedición: {e}")
        flash(f'Error al crear el evento: {str(e)}', 'danger')
            
    return redirect(url_for('calendar_view.view'))

@calendar_bp.route('/admin/event/edit/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    """Actualización total de logística y mantenimiento físico de imágenes."""
    ev = Event.query.get_or_404(event_id)
    file = request.files.get('flyer')
    
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # Limpieza de archivo antiguo para optimización de almacenamiento.
        if ev.flyer:
            try:
                old_p = os.path.join(app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(old_p): os.remove(old_p)
            except Exception as e:
                logger.warning(f"No se pudo limpiar el flyer antiguo ID {ev.id}: {e}")
        ev.flyer = filename

    try:
        # Re-mapeo exhaustivo de parámetros logísticos.
        ev.title = request.form.get('title')
        ev.currency = request.form.get('currency')
        ev.price = float(request.form.get('price') or 0)
        ev.points_reward = int(request.form.get('points_reward') or 10)
        ev.activity_type = request.form.get('activity_type')
        ev.duration_days = int(request.form.get('duration_days') or 1)
        ev.event_date = to_date(request.form.get('event_date'))
        ev.end_date = to_date(request.form.get('end_date'))
        ev.departure_point = request.form.get('departure_point')
        ev.departure_time = request.form.get('departure_time')
        ev.difficulty = request.form.get('difficulty')
        ev.distance = request.form.get('distance')
        ev.capacity = int(request.form.get('capacity') or 0)
        ev.reservation_fee = request.form.get('reservation_fee')
        ev.description = request.form.get('description')
        ev.pickup_point = request.form.get('pickup_point')
        ev.status = request.form.get('status')
        ev.moved_date = to_date(request.form.get('moved_date'))
        
        db.session.commit()
        flash('Datos de expedición actualizados correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editando evento {event_id}: {e}")
        flash(f'Fallo al guardar cambios: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('main.home'))

@calendar_bp.route('/admin/event/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    """Borrado íntegro de expedición, inscripciones y archivo físico flyer."""
    ev = Event.query.get_or_404(event_id)
    try:
        if ev.flyer:
            try:
                path = os.path.join(app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(path): os.remove(path)
            except Exception:
                pass
        
        db.session.delete(ev)
        db.session.commit()
        flash('Ruta eliminada permanentemente del sistema.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo borrando evento {event_id}: {e}")
        flash(f'No se pudo eliminar el evento: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

# --- REGISTRO FINAL E INTEGRACIÓN DE SERVICIOS ---

from puntos import puntos_bp

# Registro de Blueprints.
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(puntos_bp)

# --- INICIALIZACIÓN DE LA INFRAESTRUCTURA DE DATOS ---

with app.app_context():
    # Creación de tablas según modelos maestros en db.py.
    db.create_all()
    
    # LISTA BLANCA DE ADMINISTRADORES LÍDERES.
    masters = [
        {"email": "kenth1977@gmail.com", "pass": "CR129x7848n"},
        {"email": "lthikingcr@gmail.com", "pass": "CR129x7848n"}
    ]
    for m in masters:
        if not User.query.filter_by(email=m['email']).first():
            hashed_pw = bcrypt.generate_password_hash(m['pass']).decode('utf-8')
            db.session.add(User(
                email=m['email'], 
                password=hashed_pw, 
                is_superuser=True
            ))
    db.session.commit()

# --- LANZAMIENTO DEL SERVIDOR MAESTRO ---

if __name__ == '__main__':
    # Lanzar servidor en modo debug para desarrollo profesional.
    app.run(debug=True)