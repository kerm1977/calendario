# db.py
import os
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    is_superuser = db.Column(db.Boolean, default=False)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Datos Principales
    title = db.Column(db.String(100), nullable=False) # Nombre del Evento
    flyer = db.Column(db.String(255), nullable=True) # Imagen
    currency = db.Column(db.String(5), default='¢') # $, ¢
    price = db.Column(db.Float, default=0.0)
    activity_type = db.Column(db.String(100)) # Caminata, Taller, etc.
    
    # Tiempos
    duration_days = db.Column(db.Integer, default=1)
    event_date = db.Column(db.Date, nullable=False) # Inicio o Fecha única
    end_date = db.Column(db.Date, nullable=True) # Solo si días > 1
    
    # Detalles
    departure_point = db.Column(db.String(150))
    departure_time = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    capacity = db.Column(db.Integer)
    reservation_fee = db.Column(db.String(100)) # Reserva con
    description = db.Column(db.Text)
    pickup_point = db.Column(db.String(150)) # Se recoge en
    
    # Estado
    status = db.Column(db.String(50), default='Activa') # Activa, Pendiente, Suspendido, Se Traslado
    moved_date = db.Column(db.Date, nullable=True) # Nueva fecha si se trasladó
    
    # Auditoría
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con reservas
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100))
    telefono = db.Column(db.String(20), nullable=False)
    pin = db.Column(db.String(10), nullable=False, unique=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db(app):
    """Crea la base de datos y los superusuarios iniciales."""
    with app.app_context():
        db.create_all()
        
        superusers_emails = ["kenth1977@gmail.com", "lthikingcr@gmail.com"]
        password_plain = "CR129x7848n"
        hashed_pw = bcrypt.generate_password_hash(password_plain).decode('utf-8')
        
        for email in superusers_emails:
            if not User.query.filter_by(email=email).first():
                user = User(email=email, password=hashed_pw, is_superuser=True)
                db.session.add(user)
        
        db.session.commit()