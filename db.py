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
    password = db.Column(db.String(60), nullable=False)
    is_superuser = db.Column(db.Boolean, default=False)

class Event(db.Model):
    """Modelo para las aventuras y expediciones."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    flyer = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(5), default='¢')
    price = db.Column(db.Float, default=0.0)
    activity_type = db.Column(db.String(100))
    duration_days = db.Column(db.Integer, default=1)
    event_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    departure_point = db.Column(db.String(150))
    departure_time = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    capacity = db.Column(db.Integer)
    reservation_fee = db.Column(db.String(100))
    description = db.Column(db.Text)
    pickup_point = db.Column(db.String(150))
    status = db.Column(db.String(50), default='Activa')
    moved_date = db.Column(db.Date, nullable=True)
    
    # Puntos que otorga esta actividad al completarse
    points_reward = db.Column(db.Integer, default=15)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

class Member(db.Model):
    """
    Nuevo Modelo: Representa a una persona única en La Tribu.
    Aquí es donde se acumulan los puntos reales.
    """
    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(10), unique=True, nullable=False) # El PIN identifica al socio
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100))
    telefono = db.Column(db.String(20), nullable=False)
    puntos_totales = db.Column(db.Integer, default=10) # Puntos de bienvenida
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='member', lazy=True)

class Booking(db.Model):
    """Relaciona a un miembro con un evento específico."""
    id = db.Column(db.Integer, primary_key=True)
    
    # Campos redundantes para histórico o facilidad de consulta rápida
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    pin = db.Column(db.String(10), nullable=False) # IMPORTANTE: Se quitó el unique=True
    
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=True)
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