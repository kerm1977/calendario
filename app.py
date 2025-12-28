# app.py
import os
import calendar
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import extract
from db import db, bcrypt, User, Event, init_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_key_calendario_flexbox'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'flyers')

# Asegurar que la carpeta de subidas de flyers exista
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Inicializar DB y extensiones
db.init_app(app)
bcrypt.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- PROCESADOR DE CONTEXTO GLOBAL ---
@app.context_processor
def inject_activity_count():
    """
    Calcula la cantidad de actividades para el buscador en base.html.
    Ahora es flexible con el año para que encuentre eventos futuros como los de 2026.
    """
    search_month = request.args.get('search_month', type=int)
    
    # Si no hay búsqueda activa, mostramos el conteo del mes real actual
    if not search_month:
        target_month = datetime.now().month
    else:
        target_month = search_month
        
    # Filtramos por mes sin importar el año para dar visibilidad a eventos de 2026 y más allá
    count = Event.query.filter(
        extract('month', Event.event_date) == target_month
    ).count()
    
    return dict(month_activity_count=count)

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
            flash('¡Bienvenido a La Tribu!', 'success')
            return redirect(url_for('main.home'))
        flash('Correo o contraseña incorrectos', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('main.home'))

# --- RUTAS PÚBLICAS ---

@main_bp.route('/')
def home():
    search_month = request.args.get('search_month', type=int)
    query = Event.query
    
    if search_month:
        # Filtramos por mes sin importar el año para dar visibilidad a planes futuros
        query = query.filter(
            extract('month', Event.event_date) == search_month
        )
    
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

# --- RUTAS DE ADMINISTRACIÓN ---

@calendar_bp.route('/admin/calendar')
@login_required
def view():
    if not current_user.is_superuser:
        flash('Acceso restringido.', 'danger')
        return redirect(url_for('main.home'))
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    if month > 12: month = 1; year += 1
    if month < 1: month = 12; year -= 1

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    
    month_name = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][month]
    
    events = Event.query.all()
    return render_template('calendar.html', 
                           weeks=weeks, 
                           year=year, 
                           month=month, 
                           month_name=month_name,
                           events=events)

def to_date(s):
    return datetime.strptime(s, '%Y-%m-%d').date() if s else None

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
        new_event = Event(
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
        db.session.add(new_event)
        db.session.commit()
        flash('Actividad creada exitosamente.', 'success')
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
        flash('Actividad actualizada.', 'success')
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
        flash('Actividad eliminada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(calendar_bp)

if __name__ == '__main__':
    init_db(app)
    app.run(debug=True)