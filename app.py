# app.py
import os
import calendar
import random
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import extract
from db import db, bcrypt, User, Event, Booking, init_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_key_la_tribu_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'flyers')

# Asegurar la existencia de la carpeta para imágenes
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Lista de meses en español para la interfaz
MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Inicialización de extensiones
db.init_app(app)
bcrypt.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- PROCESADOR DE CONTEXTO ---
@app.context_processor
def inject_global_vars():
    """Inyecta variables comunes como el conteo de actividades del mes."""
    search_month_idx = request.args.get('search_month', type=int)
    if not search_month_idx:
        target_month = datetime.now().month
    else:
        target_month = search_month_idx
        
    count = Event.query.filter(extract('month', Event.event_date) == target_month).count()
    return dict(month_activity_count=count, meses_lista=MESES_ES)

# --- BLUEPRINTS ---
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
calendar_bp = Blueprint('calendar_view', __name__)

# --- RUTAS DE AUTENTICACIÓN ---

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
            flash('¡Acceso concedido! Bienvenido al panel.', 'success')
            return redirect(url_for('main.dashboard'))
        flash('Credenciales incorrectas.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('main.home'))

# --- RUTAS DE LA APLICACIÓN PRINCIPAL ---

@main_bp.route('/')
def home():
    search_month = request.args.get('search_month', type=int)
    query = Event.query
    if search_month:
        query = query.filter(extract('month', Event.event_date) == search_month)
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    """Ruta que alimenta el Canvas de Dashboard Administrativo."""
    if not current_user.is_superuser:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.home'))
    
    # Cálculo de métricas para el Dashboard
    total_count = Event.query.count()
    stats = {
        'total': total_count,
        'active': Event.query.filter_by(status='Activa').count(),
        'cancelled': Event.query.filter_by(status='Suspendido').count(),
        'moved': Event.query.filter_by(status='Se Traslado').count(),
        'camino': Event.query.filter_by(activity_type='El Camino de Costa Rica').count(),
        'nacionales': Event.query.filter_by(activity_type='Parque Nacional').count(),
        'internacionales': Event.query.filter_by(activity_type='Internacional').count()
    }
    
    # Obtener todas las reservas con la información del evento relacionado
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    
    return render_template('dashboard.html', stats=stats, bookings=bookings)

# --- API DE RESERVAS Y USUARIOS ---

@main_bp.route('/api/reserve', methods=['POST'])
def api_reserve():
    """Registra un nuevo miembro y genera un PIN único."""
    data = request.json
    try:
        # Generar un PIN único de 6 dígitos que no exista en la BD
        while True:
            new_pin = str(random.randint(100000, 999999))
            if not Booking.query.filter_by(pin=new_pin).first():
                break
        
        new_booking = Booking(
            nombre=data['nombre'],
            apellido1=data['apellido1'],
            apellido2=data.get('apellido2', ''),
            telefono=data['telefono'],
            pin=new_pin,
            event_id=data['event_id']
        )
        db.session.add(new_booking)
        db.session.commit()
        return jsonify({'success': True, 'pin': new_pin})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@main_bp.route('/api/lookup/<pin>')
def api_lookup(pin):
    """Busca datos de usuario por PIN para auto-rellenado."""
    booking = Booking.query.filter_by(pin=pin).first()
    if booking:
        return jsonify({
            'success': True,
            'nombre': booking.nombre,
            'apellido1': booking.apellido1,
            'apellido2': booking.apellido2,
            'telefono': booking.telefono
        })
    return jsonify({'success': False})

# --- GESTIÓN DE CALENDARIO Y EVENTOS ---

@calendar_bp.route('/admin/calendar')
@login_required
def view():
    if not current_user.is_superuser:
        return redirect(url_for('main.home'))
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    if month > 12: month = 1; year += 1
    elif month < 1: month = 12; year -= 1

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    
    month_name = MESES_ES[month]
    events = Event.query.all()
    
    return render_template('calendar.html', 
                           weeks=weeks, 
                           year=year, 
                           month=month, 
                           month_name=month_name,
                           events=events)

def to_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None

@calendar_bp.route('/admin/event/add', methods=['POST'])
@login_required
def add_event():
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    file = request.files.get('flyer')
    filename = None
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    try:
        event = Event(
            title=request.form.get('title'),
            flyer=filename,
            currency=request.form.get('currency'),
            price=float(request.form.get('price') or 0),
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
            status=request.form.get('status'),
            moved_date=to_date(request.form.get('moved_date'))
        )
        db.session.add(event)
        db.session.commit()
        flash('Nueva aventura creada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear evento: {str(e)}', 'danger')
            
    return redirect(url_for('calendar_view.view'))

@calendar_bp.route('/admin/event/edit/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    event = Event.query.get_or_404(event_id)
    file = request.files.get('flyer')
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # Eliminar flyer anterior si existe
        if event.flyer:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], event.flyer))
            except: pass
        event.flyer = filename

    try:
        event.title = request.form.get('title')
        event.currency = request.form.get('currency')
        event.price = float(request.form.get('price') or 0)
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
        flash('Aventura actualizada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

@calendar_bp.route('/admin/event/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    
    event = Event.query.get_or_404(event_id)
    try:
        if event.flyer:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], event.flyer))
            except: pass
        db.session.delete(event)
        db.session.commit()
        flash('Aventura eliminada permanentemente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

# Registro de Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)

if __name__ == '__main__':
    init_db(app)
    app.run(debug=True)