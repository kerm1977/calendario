import os
import calendar
import random
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import extract, desc

# --- IMPORTACIÓN DE MODELOS Y CONFIGURACIÓN ---
# Centralizamos los modelos en db.py para romper los ciclos de dependencia (Circular Imports)
# Asegúrate de que db.py contenga: db, bcrypt, User, Member, Event, Booking
from db import db, bcrypt, User, Member, Event, Booking

app = Flask(__name__)

# --- CONFIGURACIÓN DEL SERVIDOR ---
# Secret key para manejo de sesiones y seguridad de formularios
app.config['SECRET_KEY'] = 'dev_key_la_tribu_2026_pro_full_integration'

# Configuración de la base de datos SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de almacenamiento para los flyers de las aventuras
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'flyers')

# Garantizar la existencia de los directorios de carga para evitar errores de E/S
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Listado maestro de meses para traducciones y componentes visuales
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# --- INICIALIZACIÓN DE COMPONENTES ---
db.init_app(app)
bcrypt.init_app(app)

# Gestión de inicios de sesión
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
login_manager.login_message = "Acceso restringido. Por favor, identifíquese para continuar."

@login_manager.user_loader
def load_user(user_id):
    """Carga el usuario desde la base de datos para Flask-Login."""
    return User.query.get(int(user_id))

# --- FUNCIONES DE APOYO LOGÍSTICO Y FORMATEO ---

def calculate_age(born):
    """
    Calcula la edad exacta de un aventurero basándose en su fecha de nacimiento.
    Útil para la segmentación en el Dashboard y felicitaciones.
    """
    if not born:
        return "N/A"
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def to_date(date_str):
    """
    Convierte de forma segura un string proveniente de un input HTML date 
    a un objeto date de Python manejable por SQLAlchemy.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None

# --- CONTEXT PROCESSOR (LÓGICA MAESTRA DE FIDELIDAD) ---

@app.context_processor
def inject_global_vars():
    """
    Inyecta datos cruciales en todas las plantillas y ejecuta la lógica 
    automática de bonos por cumpleaños (500 pts) en tiempo real.
    """
    today = date.today()
    
    # Identificar a los miembros que celebran su cumpleaños en la fecha actual
    birthdays_today = Member.query.filter(
        extract('month', Member.birth_date) == today.month,
        extract('day', Member.birth_date) == today.day
    ).all()

    # LOGICA DE FIDELIZACIÓN: REGALO AUTOMÁTICO DE CUMPLEAÑOS
    # Esta sección garantiza que el miembro reciba sus 500 puntos al interactuar con la app en su día.
    commit_needed = False
    for member in birthdays_today:
        # Validamos que no se le haya otorgado el regalo ya en este año calendario
        if member.ultimo_regalo_bday != today.year:
            member.puntos_totales += 500
            member.ultimo_regalo_bday = today.year
            commit_needed = True
    
    if commit_needed:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error procesando bonos automáticos: {e}")

    # Cálculo dinámico del contador para el buscador de meses en la Home
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

# --- DEFINICIÓN DE BLUEPRINTS (MODULARIDAD) ---
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
calendar_bp = Blueprint('calendar_view', __name__)

# --- RUTAS DE GESTIÓN DE ACCESO (AUTH) ---

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Maneja el acceso administrativo al sistema."""
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('¡Acceso concedido! Bienvenido al centro de control de La Tribu.', 'success')
            return redirect(url_for('main.dashboard'))
        
        flash('Credenciales incorrectas. Verifique su correo y contraseña.', 'danger')
        
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Cierra la sesión administrativa."""
    logout_user()
    flash('Sesión finalizada correctamente. ¡Nos vemos en la montaña!', 'info')
    return redirect(url_for('main.home'))

# --- RUTAS DE VISTA PÚBLICA Y DASHBOARD ---

@main_bp.route('/')
def home():
    """Renderiza el catálogo principal de expediciones con filtros."""
    search_month = request.args.get('search_month', type=int)
    query = Event.query
    
    if search_month:
        query = query.filter(extract('month', Event.event_date) == search_month)
    
    # Ordenar por fecha de evento más cercana
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    """Panel de administración principal con métricas críticas."""
    if not current_user.is_superuser:
        flash('Acceso restringido a Superusuarios.', 'danger')
        return redirect(url_for('main.home'))
    
    # Recopilación de estadísticas para las tarjetas informativas
    stats = {
        'total': Event.query.count(),
        'active': Event.query.filter_by(status='Activa').count(),
        'members_count': Member.query.count(),
        'birthdays_count': Member.query.filter(
            extract('month', Member.birth_date) == date.today().month,
            extract('day', Member.birth_date) == date.today().day
        ).count()
    }
    
    # Listado de las últimas 50 reservas para monitoreo
    bookings = Booking.query.order_by(Booking.created_at.desc()).limit(50).all()
    
    # Top 10 de aventureros por acumulación de puntos
    ranking = Member.query.order_by(Member.puntos_totales.desc()).limit(10).all()
    
    return render_template('dashboard.html', stats=stats, bookings=bookings, ranking=ranking)

@main_bp.route('/admin/booking/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """
    Anula una reserva específica y ejecuta la reversión de puntos.
    Asegura que el saldo del miembro nunca sea negativo.
    """
    booking = Booking.query.get_or_404(booking_id)
    member = booking.member
    event = booking.event
    
    try:
        # Los puntos a restar son los mismos que otorgó el evento
        puntos_a_revertir = event.points_reward or 10
        member.puntos_totales = max(0, member.puntos_totales - puntos_a_revertir)
        
        db.session.delete(booking)
        db.session.commit()
        flash(f'Participación anulada. Se han restado {puntos_a_revertir} puntos a {member.nombre}.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error procesando la anulación: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('main.dashboard'))

@main_bp.route('/admin/member/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    """
    Borrado absoluto de un miembro. Elimina PIN, historial y puntos.
    Acción IRREVERSIBLE.
    """
    member = Member.query.get_or_404(member_id)
    try:
        nombre_afectado = member.nombre
        db.session.delete(member)
        db.session.commit()
        flash(f'El aventurero {nombre_afectado} ha sido removido permanentemente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error crítico al eliminar miembro: {str(e)}', 'danger')
        
    return redirect(url_for('main.dashboard'))

# --- API ENDPOINTS (LÓGICA DE NEGOCIO Y CONSULTA) ---

@main_bp.route('/api/lookup/<pin>')
def api_lookup(pin):
    """
    Servicio de consulta de miembros vía PIN.
    Crucial para el Portal de Puntos y el registro inteligente.
    """
    member = Member.query.filter_by(pin=pin).first()
    if member:
        return jsonify({
            'success': True,
            'id': member.id, # ID único para navegación
            'nombre': member.nombre,
            'apellido1': member.apellido1,
            'apellido2': member.apellido2,
            'telefono': member.telefono,
            'puntos': member.puntos_totales,
            'birth_date': member.birth_date.strftime('%Y-%m-%d') if member.birth_date else None
        })
    return jsonify({'success': False, 'error': 'El PIN ingresado no existe en La Tribu.'})

@main_bp.route('/api/reserve', methods=['POST'])
def api_reserve():
    """
    Gestión inteligente de reservas.
    1. Identifica al miembro (nuevo o existente).
    2. Valida duplicados de inscripción.
    3. Suma puntos del evento.
    4. Procesa bonos de cumpleaños en el acto.
    """
    data = request.json
    try:
        event = Event.query.get_or_404(data['event_id'])
        today = date.today()
        member = None
        
        # Intentar localizar al miembro mediante el PIN si lo proporcionó
        if data.get('pin'):
            member = Member.query.filter_by(pin=data.get('pin')).first()

        if not member:
            # FLUJO PARA MIEMBRO NUEVO: Generación de Identidad
            while True:
                new_pin = str(random.randint(100000, 999999))
                if not Member.query.filter_by(pin=new_pin).first():
                    break
            
            birth_date_obj = to_date(data.get('birth_date'))
            pts_recompensa = event.points_reward or 10
            regalo_año = 0
            
            # Bono inmediato si su primer registro coincide con su cumpleaños
            if birth_date_obj and birth_date_obj.month == today.month and birth_date_obj.day == today.day:
                pts_recompensa += 500
                regalo_año = today.year

            member = Member(
                pin=new_pin, 
                nombre=data['nombre'], 
                apellido1=data['apellido1'], 
                apellido2=data.get('apellido2', ''),
                telefono=data['telefono'], 
                birth_date=birth_date_obj, 
                puntos_totales=pts_recompensa,
                ultimo_regalo_bday=regalo_año
            )
            db.session.add(member)
            db.session.flush() # Sincronizar para obtener ID antes de crear Booking
        else:
            # FLUJO PARA MIEMBRO EXISTENTE: Actualización de Cuenta
            # Evitar que se registre dos veces en la misma actividad
            existing_booking = Booking.query.filter_by(member_id=member.id, event_id=event.id).first()
            if existing_booking:
                return jsonify({'success': False, 'error': 'Ya te encuentras registrado para esta aventura.'})
            
            # Sumar puntos estándar del evento
            member.puntos_totales += (event.points_reward or 10)
            
            # Verificación de bono de cumpleaños durante el registro
            if member.birth_date and member.birth_date.month == today.month and member.birth_date.day == today.day:
                if member.ultimo_regalo_bday != today.year:
                    member.puntos_totales += 500
                    member.ultimo_regalo_bday = today.year

        # Creación del ticket oficial de reserva
        db.session.add(Booking(
            member_id=member.id, 
            event_id=event.id, 
            pin=member.pin,
            nombre=member.nombre, 
            apellido1=member.apellido1, 
            telefono=member.telefono
        ))
        db.session.commit()
        
        return jsonify({'success': True, 'pin': member.pin, 'puntos': member.puntos_totales})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f"Fallo en reserva: {str(e)}"})

# --- GESTIÓN ADMINISTRATIVA DE CALENDARIO Y EVENTOS (CRUD) ---

@calendar_bp.route('/admin/calendar')
@login_required
def view():
    """Genera la vista de cuadrícula mensual para administración."""
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
    """Publica una nueva aventura procesando toda la logística del formulario."""
    file = request.files.get('flyer')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    
    if filename:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    try:
        new_event = Event(
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
        db.session.add(new_event)
        db.session.commit()
        flash('¡Nueva aventura publicada correctamente!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error logístico al crear: {str(e)}', 'danger')
            
    return redirect(url_for('calendar_view.view'))

@calendar_bp.route('/admin/event/edit/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    """Actualiza datos de un evento y gestiona la sustitución de archivos físicos."""
    ev = Event.query.get_or_404(event_id)
    file = request.files.get('flyer')
    
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # Limpiar archivo físico anterior para optimizar almacenamiento
        if ev.flyer:
            try:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception as e:
                print(f"Error borrando flyer antiguo: {e}")
        ev.flyer = filename

    try:
        # Actualización masiva de parámetros
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
        flash('Expedición actualizada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fallo al actualizar la base de datos: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('main.home'))

@calendar_bp.route('/admin/event/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    """Borra un evento, sus inscripciones y su archivo de imagen físico."""
    ev = Event.query.get_or_404(event_id)
    try:
        # Borrado del archivo de imagen
        if ev.flyer:
            try:
                path = os.path.join(app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
        
        db.session.delete(ev)
        db.session.commit()
        flash('Evento eliminado permanentemente del calendario.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error crítico al borrar evento: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

# --- REGISTRO DE BLUEPRINTS E INTEGRACIÓN DE SERVICIOS ---

from puntos import puntos_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(puntos_bp)

# --- INICIALIZACIÓN DE LA BASE DE DATOS Y SUPERUSUARIOS ---

with app.app_context():
    # Crea tablas si no existen
    db.create_all()
    
    # Configuración de administradores maestros
    super_users = [
        {"email": "kenth1977@gmail.com", "pass": "CR129x7848n"},
        {"email": "lthikingcr@gmail.com", "pass": "CR129x7848n"}
    ]
    
    for su in super_users:
        if not User.query.filter_by(email=su['email']).first():
            hashed_pw = bcrypt.generate_password_hash(su['pass']).decode('utf-8')
            db.session.add(User(
                email=su['email'], 
                password=hashed_pw, 
                is_superuser=True
            ))
            
    db.session.commit()

# --- LANZAMIENTO DEL SERVIDOR ---

if __name__ == '__main__':
    # El modo debug permite ver errores detallados en el navegador (Desarrollo)
    app.run(debug=True)