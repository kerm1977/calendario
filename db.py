from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime, timezone

# --- INICIALIZACIÓN DE EXTENSIONES ---
# db: Motor de ORM para gestionar la base de datos SQLite
db = SQLAlchemy()
# bcrypt: Utilidad para el hashing seguro de contraseñas administrativas
bcrypt = Bcrypt()

# ==========================================
# MODELO: SystemConfig (Configuraciones Editables)
# ==========================================
class SystemConfig(db.Model):
    """
    Almacena variables globales del sistema como datos de pago SINPE.
    Permite que el administrador cambie datos críticos sin tocar el código fuente.
    """
    __tablename__ = 'system_config'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False) # ej: 'sinpe_number'
    value = db.Column(db.String(255)) # ej: '86529837'

# ==========================================
# MODELO: User (Administradores / Guías)
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
    # is_superuser: Define si tiene acceso total a auditoría, finanzas y borrado radical
    is_superuser = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<User {self.email}>'

# ==========================================
# MODELO: AdminNotification (Centro de Alertas)
# ==========================================
class AdminNotification(db.Model):
    """
    Registro de eventos críticos para el panel de control de superusuarios.
    Notifica sobre acciones de usuarios (regalos, compras de puntos, retiros, etc.).
    """
    __tablename__ = 'admin_notification'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False) # 'info', 'warning', 'success', 'danger'
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    # Uso de lambda para obtener la fecha UTC actual de forma moderna y aware
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)
    
    # Enlace opcional para navegación directa desde la notificación
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
    flyer = db.Column(db.String(120)) # Nombre del archivo de imagen física
    
    # Datos Financieros
    currency = db.Column(db.String(5), default='¢')
    price = db.Column(db.Float, nullable=False)
    reservation_fee = db.Column(db.String(50)) # Texto descriptivo ej: "5000 colones"
    
    # Datos de Fidelidad
    points_reward = db.Column(db.Integer, default=10) # Puntos base que otorga el evento
    
    # Datos Logísticos
    activity_type = db.Column(db.String(50)) # Caminata, Camping, Taller, etc.
    difficulty = db.Column(db.String(50))
    distance = db.Column(db.String(50))
    duration_days = db.Column(db.Integer, default=1)
    
    # Fechas
    event_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date) # Para expediciones de varios días
    
    # Detalles operativos
    departure_point = db.Column(db.String(150))
    departure_time = db.Column(db.String(20))
    pickup_point = db.Column(db.String(200))
    capacity = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    
    # Estado del evento
    status = db.Column(db.String(20), default='Activa') # Activa, Suspendido, Se Traslado, Oculto
    moved_date = db.Column(db.Date) # Nueva fecha en caso de reprogramación

    # Relaciones: Cascade asegura que al borrar el evento radicalmente se limpien las reservas
    bookings = db.relationship('Booking', backref='event', lazy=True, cascade="all, delete-orphan")

# ==========================================
# MODELO: Member (Aventureros / Socios)
# ==========================================
class Member(db.Model):
    """
    Perfil del usuario final (Aventurero). Identificado por un PIN único de 6 dígitos.
    Centraliza el saldo de puntos y el estatus VIP.
    """
    __tablename__ = 'member'

    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(6), unique=True, nullable=False)
    
    nombre = db.Column(db.String(100), nullable=False)
    apellido1 = db.Column(db.String(100), nullable=False)
    apellido2 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    
    # Saldo de Puntos (Caché de rendimiento; la verdad contable reside en PointLog)
    puntos_totales = db.Column(db.Integer, default=0)
    
    # Estado de Deuda (True = Tiene pendiente dinero o comprobantes)
    debt_pending = db.Column(db.Boolean, default=False)
    
    # Control de Bonos de Fidelidad
    ultimo_regalo_bday = db.Column(db.Integer, default=0) # Año del último bono acreditado
    
    # Relaciones
    bookings = db.relationship('Booking', backref='member', lazy=True)
    logs = db.relationship('PointLog', backref='member', lazy=True)

# ==========================================
# MODELO: Booking (Inscripciones / Reservas)
# ==========================================
class Booking(db.Model):
    """
    Tabla intermedia que registra la participación de un miembro en una expedición.
    Mantiene snapshots de datos del usuario para auditoría histórica.
    """
    __tablename__ = 'booking'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    
    # Datos persistidos al momento de la reserva
    pin = db.Column(db.String(6))
    nombre = db.Column(db.String(100))
    apellido1 = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    
    # Estado: 'Activo', 'Retirado' (Conserva puntos), 'Cancelado' (Revoca puntos)
    status = db.Column(db.String(20), default='Activo')
    
    # Puntos que otorgaba el evento en el momento del registro
    points_at_registration = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ==========================================
# MODELO: PointLog (Cronograma Transaccional)
# ==========================================
class PointLog(db.Model):
    """
    TABLA MAESTRA DE AUDITORÍA (El Libro Mayor).
    Registra cada movimiento individual de puntos para garantizar transparencia total.
    """
    __tablename__ = 'point_log'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    
    # Tipos: 'Inscripción', 'Retiro', 'Bono Cumpleaños', 'Canje', 'Compra Puntos', 'Ajuste'
    transaction_type = db.Column(db.String(50), nullable=False)
    
    # Detalle descriptivo del movimiento
    description = db.Column(db.String(200))
    
    # Cantidad: Positiva para abonos, Negativa para cargos
    amount = db.Column(db.Integer, nullable=False)
    
    # Timestamp preciso de la transacción
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relación opcional a una reserva específica
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=True)
    
    # Campos para auditoría de penalizaciones
    is_penalized = db.Column(db.Boolean, default=False)
    penalty_reason = db.Column(db.String(200))