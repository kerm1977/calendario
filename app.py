import os
import calendar
import random
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import extract

# --- CONFIGURACIÓN INICIAL ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_key_la_tribu_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'flyers')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# --- MODELOS DE DATOS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_superuser = db.Column(db.Boolean, default=False)

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(10), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100), default='')
    telefono = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    puntos_totales = db.Column(db.Integer, default=0)
    bookings = db.relationship('Booking', backref='member', lazy=True, cascade="all, delete-orphan")

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    flyer = db.Column(db.String(200))
    currency = db.Column(db.String(10), default='CRC')
    price = db.Column(db.Float, default=0.0)
    points_reward = db.Column(db.Integer, default=10)
    activity_type = db.Column(db.String(50))
    duration_days = db.Column(db.Integer, default=1)
    event_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    departure_point = db.Column(db.String(200))
    departure_time = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    capacity = db.Column(db.Integer, default=0)
    reservation_fee = db.Column(db.String(100))
    description = db.Column(db.Text)
    pickup_point = db.Column(db.String(200))
    status = db.Column(db.String(50), default='Activa')
    moved_date = db.Column(db.Date)
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    nombre = db.Column(db.String(100))
    apellido1 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    pin = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- FUNCIONES DE UTILIDAD ---

def calculate_age(born):
    if not born: return "N/A"
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def to_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None

@app.context_processor
def inject_global_vars():
    search_month_idx = request.args.get('search_month', type=int)
    target_month = search_month_idx if search_month_idx else datetime.now().month
    count = Event.query.filter(extract('month', Event.event_date) == target_month).count()
    return dict(month_activity_count=count, meses_lista=MESES_ES, calculate_age=calculate_age, now=datetime.now())

# --- BLUEPRINTS ---
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
calendar_bp = Blueprint('calendar_view', __name__)

# --- RUTAS DE AUTENTICACIÓN ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.home'))
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

# --- RUTAS PRINCIPALES ---
@main_bp.route('/')
def home():
    search_month = request.args.get('search_month', type=int)
    query = Event.query
    if search_month: query = query.filter(extract('month', Event.event_date) == search_month)
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    if not current_user.is_superuser:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.home'))
    today = date.today()
    birthdays_today = Member.query.filter(extract('month', Member.birth_date) == today.month, extract('day', Member.birth_date) == today.day).all()
    stats = {
        'total': Event.query.count(),
        'active': Event.query.filter_by(status='Activa').count(),
        'cancelled': Event.query.filter_by(status='Suspendido').count(),
        'moved': Event.query.filter_by(status='Se Traslado').count(),
        'members_count': Member.query.count(),
        'birthdays_count': len(birthdays_today)
    }
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    ranking = Member.query.order_by(Member.puntos_totales.desc()).limit(10).all()
    return render_template('dashboard.html', stats=stats, birthdays_today=birthdays_today, bookings=bookings, ranking=ranking)

@main_bp.route('/admin/member/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    member = Member.query.get_or_404(member_id)
    try:
        db.session.delete(member)
        db.session.commit()
        flash(f'El miembro {member.nombre} ha sido eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    return redirect(url_for('main.dashboard'))

# ==========================================
# LÓGICA DE PUNTOS Y MIEMBROS (SEPARADA)
# ==========================================

@main_bp.route('/api/lookup/<pin>')
def api_lookup(pin):
    """
    Endpoint de consulta de puntos.
    Separa la lógica de búsqueda del Miembro de la vista de reserva.
    """
    member = Member.query.filter_by(pin=pin).first()
    if member:
        return jsonify({
            'success': True,
            'nombre': member.nombre,
            'apellido1': member.apellido1,
            'puntos': member.puntos_totales,
            'birth_date': member.birth_date.strftime('%Y-%m-%d') if member.birth_date else None
        })
    return jsonify({'success': False, 'error': 'PIN no encontrado en La Tribu.'})

@main_bp.route('/api/reserve', methods=['POST'])
def api_reserve():
    data = request.json
    try:
        pin_proporcionado = data.get('pin')
        member = None
        event = Event.query.get_or_404(data['event_id'])
        birth_date_obj = datetime.strptime(data['birth_date'], '%Y-%m-%d').date() if data.get('birth_date') else None

        if pin_proporcionado:
            member = Member.query.filter_by(pin=pin_proporcionado).first()

        if not member:
            while True:
                new_pin = str(random.randint(100000, 999999))
                if not Member.query.filter_by(pin=new_pin).first(): break
            member = Member(pin=new_pin, nombre=data['nombre'], apellido1=data['apellido1'], apellido2=data.get('apellido2', ''), telefono=data['telefono'], birth_date=birth_date_obj, puntos_totales=event.points_reward or 10)
            db.session.add(member)
            db.session.flush()
        else:
            existing_booking = Booking.query.filter_by(member_id=member.id, event_id=event.id).first()
            if existing_booking: return jsonify({'success': False, 'error': 'Ya estás registrado en esta aventura.'})
            if birth_date_obj: member.birth_date = birth_date_obj
            member.puntos_totales += (event.points_reward or 10)

        new_booking = Booking(member_id=member.id, event_id=event.id, nombre=member.nombre, apellido1=member.apellido1, telefono=member.telefono, pin=member.pin)
        db.session.add(new_booking)
        db.session.commit()
        return jsonify({'success': True, 'pin': member.pin, 'puntos': member.puntos_totales})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# --- GESTIÓN DE CALENDARIO Y EVENTOS (Sin cambios) ---
@calendar_bp.route('/admin/calendar')
@login_required
def view():
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    if month > 12: month = 1; year += 1
    elif month < 1: month = 12; year -= 1
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    events = Event.query.all()
    monthly_birthdays = Member.query.filter(extract('month', Member.birth_date) == month).all()
    return render_template('calendar.html', weeks=weeks, year=year, month=month, month_name=MESES_ES[month], events=events, monthly_birthdays=monthly_birthdays)

@calendar_bp.route('/admin/event/add', methods=['POST'])
@login_required
def add_event():
    if not current_user.is_superuser: return redirect(url_for('main.home'))
    file = request.files.get('flyer')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    if filename: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    try:
        event = Event(title=request.form.get('title'), flyer=filename, currency=request.form.get('currency'), price=float(request.form.get('price') or 0), points_reward=int(request.form.get('points_reward') or 10), activity_type=request.form.get('activity_type'), duration_days=int(request.form.get('duration_days') or 1), event_date=to_date(request.form.get('event_date')), end_date=to_date(request.form.get('end_date')), departure_point=request.form.get('departure_point'), departure_time=request.form.get('departure_time'), difficulty=request.form.get('difficulty'), distance=request.form.get('distance'), capacity=int(request.form.get('capacity') or 0), reservation_fee=request.form.get('reservation_fee'), description=request.form.get('description'), pickup_point=request.form.get('pickup_point'), status=request.form.get('status') or 'Activa', moved_date=to_date(request.form.get('moved_date')))
        db.session.add(event)
        db.session.commit()
        flash('Nueva aventura creada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
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
        if event.flyer:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], event.flyer))
            except: pass
        event.flyer = filename
    try:
        event.title = request.form.get('title'); event.currency = request.form.get('currency'); event.price = float(request.form.get('price') or 0); event.points_reward = int(request.form.get('points_reward') or 10); event.activity_type = request.form.get('activity_type'); event.duration_days = int(request.form.get('duration_days') or 1); event.event_date = to_date(request.form.get('event_date')); event.end_date = to_date(request.form.get('end_date')); event.departure_point = request.form.get('departure_point'); event.departure_time = request.form.get('departure_time'); event.difficulty = request.form.get('difficulty'); event.distance = request.form.get('distance'); event.capacity = int(request.form.get('capacity') or 0); event.reservation_fee = request.form.get('reservation_fee'); event.description = request.form.get('description'); event.pickup_point = request.form.get('pickup_point'); event.status = request.form.get('status'); event.moved_date = to_date(request.form.get('moved_date'))
        db.session.commit()
        flash('Aventura actualizada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
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
        flash('Aventura eliminada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('main.home'))

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@latribu.com').first():
        hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(email='admin@latribu.com', password=hashed_pw, is_superuser=True)
        db.session.add(admin); db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)