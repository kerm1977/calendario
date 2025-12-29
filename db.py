# db.py
import os
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(db.Model, UserMixin):
    """Modelo para los administradores del sistema."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_superuser = db.Column(db.Boolean, default=False)

class Event(db.Model):
    """Modelo para las aventuras y expediciones con toda su logística."""
    id = db.Column(db.Integer, primary_key=True)
    # Datos Principales
    title = db.Column(db.String(150), nullable=False)
    flyer = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(10), default='¢')
    price = db.Column(db.Float, default=0.0)
    activity_type = db.Column(db.String(100))
    
    # Gestión de Tiempos y Duración
    duration_days = db.Column(db.Integer, default=1)
    event_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    
    # Detalles Logísticos
    departure_point = db.Column(db.String(200))
    departure_time = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    capacity = db.Column(db.Integer, default=0)
    reservation_fee = db.Column(db.String(100))
    description = db.Column(db.Text)
    pickup_point = db.Column(db.String(200))
    
    # Estado de la Actividad
    status = db.Column(db.String(50), default='Activa')
    moved_date = db.Column(db.Date, nullable=True)
    
    # --- SISTEMA DE PUNTOS ---
    points_reward = db.Column(db.Integer, default=10) # Puntos que otorga este evento
    
    # Auditoría
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con reservas
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

class Member(db.Model):
    """
    Representa a una persona única de La Tribu. 
    Aquí se centralizan los puntos y la información personal permanente.
    """
    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(10), unique=True, nullable=False) # Identificador único
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100), default='')
    telefono = db.Column(db.String(20), nullable=False)
    
    # --- CAMPOS DE FIDELIDAD ---
    birth_date = db.Column(db.Date, nullable=True) # Para el cálculo de edad y felicitaciones
    puntos_totales = db.Column(db.Integer, default=0) # Acumulado histórico de puntos
    
    # Control para el bono de cumpleaños anual (bono de 500 pts)
    # Almacena el año del último regalo para no darlo dos veces el mismo año.
    ultimo_regalo_bday = db.Column(db.Integer, default=0) 
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='member', lazy=True, cascade="all, delete-orphan")

class Booking(db.Model):
    """Relaciona un Miembro con un Evento específico."""
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    
    # Campos informativos (capturan el estado al momento de reservar)
    nombre = db.Column(db.String(100))
    apellido1 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    pin = db.Column(db.String(10)) 

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db(app):
    """Crea la base de datos y configura los administradores por defecto."""
    with app.app_context():
        db.create_all()
        
        # Lista de superusuarios autorizados
        superusers_emails = ["kenth1977@gmail.com", "lthikingcr@gmail.com"]
        password_plain = "CR129x7848n"
        hashed_pw = bcrypt.generate_password_hash(password_plain).decode('utf-8')
        
        for email in superusers_emails:
            if not User.query.filter_by(email=email).first():
                user = User(email=email, password=hashed_pw, is_superuser=True)
                db.session.add(user)
        
        db.session.commit()