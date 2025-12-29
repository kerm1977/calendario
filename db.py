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
# MODELO: Event (Aventuras / Expediciones)
# ==========================================
class Event(db.Model):
    """
    Representa una expedición o ruta organizada por La Tribu.
    Contiene toda la información logística, financiera y de fidelidad.
    """
    __tablename__ = 'event'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    flyer = db.Column(db.String(255)) # Nombre del archivo de imagen en el servidor
    
    # Parámetros Financieros y de Recompensa
    currency = db.Column(db.String(10), default='¢')
    price = db.Column(db.Float, default=0.0)
    points_reward = db.Column(db.Integer, default=10) # Puntos que otorga al aventurero
    
    # Detalles Logísticos de la Ruta
    activity_type = db.Column(db.String(100)) # Caminata, Internacional, etc.
    duration_days = db.Column(db.Integer, default=1)
    event_date = db.Column(db.Date, nullable=False) # Fecha de inicio
    end_date = db.Column(db.Date) # Fecha de cierre para expediciones de varios días
    
    departure_point = db.Column(db.String(200)) # Punto de encuentro principal
    departure_time = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    capacity = db.Column(db.Integer, default=0) # Cupos disponibles
    
    reservation_fee = db.Column(db.String(100)) # Monto requerido para apartar lugar
    description = db.Column(db.Text) # Itinerario detallado
    pickup_point = db.Column(db.String(200)) # Puntos de recogida adicionales
    
    # Estados de la publicación
    status = db.Column(db.String(50), default='Activa') # Activa, Suspendido, Se Traslado
    moved_date = db.Column(db.Date) # Nueva fecha en caso de traslado
    
    # Relación: Un evento puede tener múltiples reservas
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Event {self.title}>'

# ==========================================
# MODELO: Member (Aventureros / Miembros)
# ==========================================
class Member(db.Model):
    """
    Representa a un miembro de La Tribu.
    Identificado por un PIN único de 6 dígitos para facilitar su acceso.
    """
    __tablename__ = 'member'
    
    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(10), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    
    # Saldo acumulado de fidelidad (Caché del total general)
    puntos_totales = db.Column(db.Integer, default=0)
    # Registro del año del último regalo de cumpleaños para evitar duplicidad
    ultimo_regalo_bday = db.Column(db.Integer, default=0)
    
    # Relaciones
    bookings = db.relationship('Booking', backref='member', lazy=True, cascade="all, delete-orphan")
    # Point_logs: El cronograma detallado de cada punto ganado o perdido
    point_logs = db.relationship('PointLog', backref='member', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Member {self.nombre} {self.apellido1}>'

# ==========================================
# MODELO: Booking (Inscripciones / Reservas)
# ==========================================
class Booking(db.Model):
    """
    Entidad de enlace entre Miembros y Eventos.
    Permite auditar el historial de participación y la trazabilidad de puntos.
    """
    __tablename__ = 'booking'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    
    # Datos de contacto espejo (para acceso rápido sin Joins complejos)
    pin = db.Column(db.String(10))
    nombre = db.Column(db.String(100))
    apellido1 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    
    # CRÍTICO: Registra cuántos puntos valía la aventura al momento de inscribirse
    points_at_registration = db.Column(db.Integer, default=0)
    
    # status: 'Activo' (Suma puntos), 'Retirado' (Se mantiene la línea pero resta puntos)
    status = db.Column(db.String(50), default='Activo')
    
    # Fecha de registro original
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Booking {self.id} - Member: {self.member_id} - Event: {self.event_id}>'

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
    is_penalized = db.Column(db.Boolean, default=False)  # Si el movimiento fue penalizado
    penalty_reason = db.Column(db.String(200), nullable=True)  # Razón de la penalización

    def __repr__(self):
        return f'<PointLog {self.transaction_type}: {self.amount} pts para Member {self.member_id}>'