import os
import calendar
import random
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import extract, desc

# --- IMPORTACIÓN DE MODELOS Y CONFIGURACIÓN ---
# Importamos desde db.py para romper el ciclo de importación con puntos.py
from db import db, bcrypt, User, Member, Event, Booking

# --- CONFIGURACIÓN DE LA APLICACIÓN ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_key_la_tribu_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'flyers')

# Garantizar que la carpeta de flyers exista para evitar errores de E/S
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Listado global de meses para traducciones y visualización en la interfaz
MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Inicialización de extensiones vinculadas a la instancia de la app
db.init_app(app)
bcrypt.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
login_manager.login_message = "Por favor inicia sesión para acceder a esta página."

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- FUNCIONES DE APOYO LOGÍSTICO ---

def calculate_age(born):
    """Calcula la edad actual de un miembro basada en su fecha de nacimiento."""
    if not born: return "N/A"
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def to_date(date_str):
    """Convierte strings de formularios (YYYY-MM-DD) a objetos de fecha seguros para SQLAlchemy."""
    if not date_str: return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None

# --- LÓGICA GLOBAL DE PUNTOS Y CELEBRACIONES ---

@app.context_processor
def inject_global_vars():
    """
    Inyecta datos en todas las plantillas y procesa automáticamente 
    los puntos de cumpleaños (500 pts) de forma global y en tiempo real.
    """
    today = date.today()
    
    # Identificar miembros que cumplen años el día de hoy
    birthdays_today = Member.query.filter(
        extract('month', Member.birth_date) == today.month,
        extract('day', Member.birth_date) == today.day
    ).all()

    # PROCESO AUTOMÁTICO: Regalo de 500 Puntos por Cumpleaños
    # Esta lógica se dispara con cada carga de página para asegurar fidelización inmediata.
    commit_needed = False
    for member in birthdays_today:
        # Verificamos que el miembro no haya recibido ya el regalo de este año
        if member.ultimo_regalo_bday != today.year:
            member.puntos_totales += 500
            member.ultimo_regalo_bday = today.year
            commit_needed = True
    
    if commit_needed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Contador de expediciones filtradas por mes para el componente de búsqueda
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

# --- BLUEPRINTS ---
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
calendar_bp = Blueprint('calendar_view', __name__)

# --- RUTAS DE AUTENTICACIÓN (GESTIÓN DE ACCESO) ---

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('¡Acceso concedido! Bienvenido al panel de control de La Tribu.', 'success')
            return redirect(url_for('main.dashboard'))
        flash('Credenciales incorrectas. Verifique su email y contraseña.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Has cerrado sesión correctamente. ¡Nos vemos en la montaña!', 'info')
    return redirect(url_for('main.home'))

# --- RUTAS DE LA VISTA PÚBLICA Y DASHBOARD ---

@main_bp.route('/')
def home():
    """Muestra el catálogo principal de aventuras para los usuarios."""
    search_month = request.args.get('search_month', type=int)
    query = Event.query
    if search_month:
        query = query.filter(extract('month', Event.event_date) == search_month)
    # Ordenamos por fecha más próxima
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    """Panel de control administrativo con métricas, ranking y actividad reciente."""
    if not current_user.is_superuser:
        flash('Acceso denegado. Se requieren permisos de superusuario.', 'danger')
        return redirect(url_for('main.home'))
    
    # Cálculo de métricas para las tarjetas informativas
    stats = {
        'total': Event.query.count(),
        'active': Event.query.filter_by(status='Activa').count(),
        'cancelled': Event.query.filter_by(status='Suspendido').count(),
        'moved': Event.query.filter_by(status='Se Traslado').count(),
        'members_count': Member.query.count(),
        'birthdays_count': Member.query.filter(
            extract('month', Member.birth_date) == date.today().month,
            extract('day', Member.birth_date) == date.today().day
        ).count()
    }
    
    # Listado de reservas recientes para la tabla de actividad
    bookings = Booking.query.order_by(Booking.created_at.desc()).limit(50).all()
    # Ranking de líderes basado en acumulación de puntos
    ranking = Member.query.order_by(Member.puntos_totales.desc()).limit(10).all()
    
    return render_template('dashboard.html', stats=stats, bookings=bookings, ranking=ranking)

# --- REVERSIÓN DE PUNTOS Y GESTIÓN DE MIEMBROS ---

@main_bp.route('/admin/booking/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """Anula una reserva y revierte exactamente los puntos otorgados por ese evento."""
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    booking = Booking.query.get_or_404(booking_id)
    member = booking.member
    event = booking.event
    
    try:
        puntos_a_restar = event.points_reward or 10
        # Revertimos los puntos asegurando que el saldo no sea negativo
        member.puntos_totales = max(0, member.puntos_totales - puntos_a_restar)
            
        db.session.delete(booking)
        db.session.commit()
        flash(f'Participación anulada. Se han restado {puntos_a_restar} puntos a {member.nombre}.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar la anulación: {str(e)}', 'danger')
        
    return redirect(url_for('main.dashboard'))

@main_bp.route('/admin/member/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    """Elimina permanentemente a un miembro, su PIN y todo su historial de puntos."""
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    member = Member.query.get_or_404(member_id)
    try:
        db.session.delete(member)
        db.session.commit()
        flash(f'El miembro {member.nombre} ha sido eliminado de la base de datos.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar miembro: {str(e)}', 'danger')
    return redirect(url_for('main.dashboard'))

# --- API PARA FRONTEND (PUNTOS Y REGISTROS) ---

@main_bp.route('/api/lookup/<pin>')
def api_lookup(pin):
    """Búsqueda AJAX de miembros por PIN para precargar datos y consultar puntos."""
    member = Member.query.filter_by(pin=pin).first()
    if member:
        return jsonify({
            'success': True,
            'nombre': member.nombre,
            'apellido1': member.apellido1,
            'apellido2': member.apellido2,
            'telefono': member.telefono,
            'puntos': member.puntos_totales,
            'birth_date': member.birth_date.strftime('%Y-%m-%d') if member.birth_date else None
        })
    return jsonify({'success': False, 'error': 'PIN no encontrado.'})

@main_bp.route('/api/reserve', methods=['POST'])
def api_reserve():
    """
    Gestiona la creación de reservas, miembros nuevos y la suma de puntos.
    Incluye lógica para otorgar bonos de cumpleaños de 500 puntos en tiempo real.
    """
    data = request.json
    try:
        pin_proporcionado = data.get('pin')
        member = None
        event = Event.query.get_or_404(data['event_id'])
        today = date.today()
        
        if pin_proporcionado:
            member = Member.query.filter_by(pin=pin_proporcionado).first()

        if not member:
            # Miembro Nuevo: Generar un PIN aleatorio único de 6 dígitos
            while True:
                new_pin = str(random.randint(100000, 999999))
                if not Member.query.filter_by(pin=new_pin).first(): break
            
            birth_date_obj = to_date(data.get('birth_date'))
            inicial_puntos = event.points_reward or 10
            regalo_año = 0
            
            # Bono inmediato si hoy es su cumpleaños al registrarse por primera vez
            if birth_date_obj and birth_date_obj.month == today.month and birth_date_obj.day == today.day:
                inicial_puntos += 500
                regalo_año = today.year

            member = Member(
                pin=new_pin, 
                nombre=data['nombre'], 
                apellido1=data['apellido1'], 
                apellido2=data.get('apellido2', ''),
                telefono=data['telefono'], 
                birth_date=birth_date_obj, 
                puntos_totales=inicial_puntos,
                ultimo_regalo_bday=regalo_año
            )
            db.session.add(member)
            db.session.flush() # Sincronizamos para obtener el ID antes de la reserva
        else:
            # Miembro Existente: Validar que no esté ya inscrito en este evento
            existing = Booking.query.filter_by(member_id=member.id, event_id=event.id).first()
            if existing:
                return jsonify({'success': False, 'error': 'Ya estás inscrito en esta aventura.'})
            
            # Sumar puntos normales del evento
            member.puntos_totales += (event.points_reward or 10)
            
            # Verificar si hoy es su cumpleaños para aplicar el bono de 500 si no lo tiene
            if member.birth_date and member.birth_date.month == today.month and member.birth_date.day == today.day:
                if member.ultimo_regalo_bday != today.year:
                    member.puntos_totales += 500
                    member.ultimo_regalo_bday = today.year

        # Creación del ticket de reserva
        new_booking = Booking(
            member_id=member.id,
            event_id=event.id,
            nombre=member.nombre,
            apellido1=member.apellido1,
            telefono=member.telefono,
            pin=member.pin
        )
        db.session.add(new_booking)
        db.session.commit()
        
        return jsonify({'success': True, 'pin': member.pin, 'puntos': member.puntos_totales})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# --- GESTIÓN DE CALENDARIO Y OPERACIONES CRUD ---

@calendar_bp.route('/admin/calendar')
@login_required
def view():
    """Genera la vista de calendario administrativo con eventos y cumpleaños."""
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    if month > 12: month = 1; year += 1
    elif month < 1: month = 12; year -= 1

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    events = Event.query.all()
    # Filtrar cumpleaños para mostrar en el calendario
    monthly_birthdays = Member.query.filter(extract('month', Member.birth_date) == month).all()
    
    return render_template('calendar.html', 
                           weeks=weeks, year=year, month=month, 
                           month_name=MESES_ES[month],
                           events=events,
                           monthly_birthdays=monthly_birthdays)

@calendar_bp.route('/admin/event/add', methods=['POST'])
@login_required
def add_event():
    """Crea una nueva aventura procesando toda la logística del formulario."""
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    file = request.files.get('flyer')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    if filename:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    try:
        event = Event(
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
        db.session.add(event)
        db.session.commit()
        flash('Nueva expedición publicada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear el evento: {str(e)}', 'danger')
            
    return redirect(url_for('calendar_view.view'))

@calendar_bp.route('/admin/event/edit/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    """Actualiza datos de un evento y maneja la sustitución física del flyer."""
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    event = Event.query.get_or_404(event_id)
    file = request.files.get('flyer')
    
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # Eliminar el archivo antiguo si existe para no saturar el servidor
        if event.flyer:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], event.flyer)
            if os.path.exists(old_path):
                try: os.remove(old_path)
                except Exception: pass
        event.flyer = filename

    try:
        # Actualización masiva de campos logísticos
        event.title = request.form.get('title')
        event.currency = request.form.get('currency')
        event.price = float(request.form.get('price') or 0)
        event.points_reward = int(request.form.get('points_reward') or 10)
        event.activity_type = request.form.get('activity_type')
        event.duration_days = int(request.form.get('duration_days') or 1)
        event.event_date = to_date(request.form.get('event_date'))
        event.end_date = to_date(request.form.get('end_date'))
        event.departure_point = request.form.get('departure_point')
        event.departure_time = request.form.get('departure_time')
        event.difficulty = request.form.get('difficulty')
        event.distance = request.form.get('distance')
        event.capacity = int(request.form.get('capacity') or 0)
        event.reservation_fee = request.form.get('reservation_fee')
        event.description = request.form.get('description')
        event.pickup_point = request.form.get('pickup_point')
        event.status = request.form.get('status')
        event.moved_date = to_date(request.form.get('moved_date'))
        
        db.session.commit()
        flash('La aventura ha sido actualizada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar los datos: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

@calendar_bp.route('/admin/event/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    """Borra un evento, sus reservas asociadas y su imagen física."""
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    event = Event.query.get_or_404(event_id)
    try:
        # Borrar flyer físico
        if event.flyer:
            path = os.path.join(app.config['UPLOAD_FOLDER'], event.flyer)
            if os.path.exists(path):
                try: os.remove(path)
                except Exception: pass
        
        db.session.delete(event)
        db.session.commit()
        flash('Expedición eliminada permanentemente del sistema.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la aventura: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

# --- REGISTRO FINAL DE BLUEPRINTS E INTEGRACIÓN ---

# Importamos el Blueprint de historial detallado
from puntos import puntos_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(puntos_bp)

# --- INICIALIZACIÓN DE BASE DE DATOS Y SUPERUSUARIOS ---

with app.app_context():
    db.create_all()
    # Listado de administradores autorizados (Sincronizado con db.py)
    super_users = [
        {"email": "kenth1977@gmail.com", "pass": "CR129x7848n"},
        {"email": "lthikingcr@gmail.com", "pass": "CR129x7848n"}
    ]
    
    for su in super_users:
        if not User.query.filter_by(email=su['email']).first():
            hashed_pw = bcrypt.generate_password_hash(su['pass']).decode('utf-8')
            new_su = User(email=su['email'], password=hashed_pw, is_superuser=True)
            db.session.add(new_su)
    
    db.session.commit()

if __name__ == '__main__':
    # Lanzar la aplicación en modo desarrollo
    app.run(debug=True)