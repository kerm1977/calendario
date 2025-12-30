from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime

# --- INICIALIZACIÓN DE EXTENSIONES ---
# db: Motor de ORM para gestionar la base de datos SQLite
db = SQLAlchemy()
# bcrypt: Utilidad para el hashing seguro de contraseñas administrativas
bcrypt = Bcrypt()

# ==========================================
# MODELO: User (Administradores)
# ==========================================
class User(db.Model, UserMixin):
    """
    Entidad que representa a los guías o administradores del sistema.
    Permite el acceso al Dashboard y la gestión de expediciones.
    """
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    # is_superuser: Define si tiene acceso total a auditoría y borrado
    is_superuser = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<User {self.email}>'

# ==========================================
# MODELO: AdminNotification (Centro de Alertas) - NUEVO
# ==========================================
class AdminNotification(db.Model):
    """
    Registro de eventos críticos para el panel de control de superusuarios.
    Notifica sobre acciones de usuarios (regalos, compras, etc.).
    """
    __tablename__ = 'admin_notification'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False) # 'info', 'warning', 'success', 'danger'
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False) # Para marcar como leída a futuro si se desea
    
    # Opcional: Link para ir directo al detalle (ej: perfil del usuario)
    action_link = db.Column(db.String(200))

# ==========================================
# MODELO: Event (Aventuras / Expediciones)
# ==========================================
class Event(db.Model):
    """
    Representa una expedición o ruta organizada por La Tribu.
    Contiene toda la información logística, financiera y de calendario.
    """
    __tablename__ = 'event'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    flyer = db.Column(db.String(120)) # Nombre del archivo de imagen
    
    # Datos Financieros
    currency = db.Column(db.String(5), default='¢')
    price = db.Column(db.Float, nullable=False)
    reservation_fee = db.Column(db.String(50)) # Texto libre ej: "5000 colones"
    
    # Datos de Fidelidad
    points_reward = db.Column(db.Integer, default=10) # Puntos que otorga
    
    # Datos Logísticos
    activity_type = db.Column(db.String(50)) # Caminata, Camping, etc.
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    duration_days = db.Column(db.Integer, default=1)
    
    # Fechas
    event_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date) # Para eventos de varios días
    
    # Detalles operativos
    departure_point = db.Column(db.String(150))
    departure_time = db.Column(db.String(20))
    pickup_point = db.Column(db.String(200))
    capacity = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    
    # Estado del evento
    status = db.Column(db.String(20), default='Activa') # Activa, Suspendido, Se Traslado
    moved_date = db.Column(db.Date) # Nueva fecha si se traslada

    # Relaciones
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

# ==========================================
# MODELO: Member (Aventureros / Socios)
# ==========================================
class Member(db.Model):
    """
    Perfil del usuario final. Identificado por un PIN único de 6 dígitos.
    Almacena su saldo de puntos y datos personales básicos.
    """
    __tablename__ = 'member'

    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(6), unique=True, nullable=False)
    
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    
    # Saldo de Puntos (Caché para acceso rápido, la verdad está en los logs)
    puntos_totales = db.Column(db.Integer, default=0)
    
    # Control de Bonos
    ultimo_regalo_bday = db.Column(db.Integer, default=0) # Año del último regalo
    
    # Relaciones
    bookings = db.relationship('Booking', backref='member', lazy=True)
    logs = db.relationship('PointLog', backref='member', lazy=True)

# ==========================================
# MODELO: Booking (Inscripciones / Reservas)
# ==========================================
class Booking(db.Model):
    """
    Tabla intermedia que registra la participación de un miembro en un evento.
    Esencial para el historial y la logística de asistentes.
    """
    __tablename__ = 'booking'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    
    # Copia de datos al momento de reservar (Snapshots)
    pin = db.Column(db.String(6))
    nombre = db.Column(db.String(100))
    apellido1 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    
    # Estado de la reserva: 'Activo', 'Cancelado', 'Retirado', 'No Participó'
    status = db.Column(db.String(20), default='Activo')
    
    # Puntos que valía el evento al momento de registrarse (para devoluciones justas)
    points_at_registration = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# MODELO: PointLog (Cronograma Detallado)
# ==========================================
class PointLog(db.Model):
    """
    TABLA MAESTRA DE AUDITORÍA (El Cronograma).
    Aquí se registra cada movimiento individual de puntos para máxima precisión.
    """
    __tablename__ = 'point_log'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    
    # tipo: 'Inscripción', 'Retiro', 'Bono Cumpleaños', 'Ajuste Manual', 'Penalización'
    transaction_type = db.Column(db.String(50), nullable=False)
    
    # detalle: Nombre de la aventura o motivo del movimiento
    description = db.Column(db.String(200))
    
    # amount: Cantidad de puntos (Puede ser positivo como 10 o negativo como -10)
    amount = db.Column(db.Integer, nullable=False)
    
    # timestamp: Fecha y hora exacta del movimiento
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Referencia opcional a un booking específico
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=True)
    
    # Campos para manejo de penalizaciones
    is_penalized = db.Column(db.Boolean, default=False)
    penalty_reason = db.Column(db.String(200))