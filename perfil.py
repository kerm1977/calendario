# ==============================================================================
# MÓDULO DE PERFIL PÚBLICO: LA TRIBU DE LOS LIBRES
# ==============================================================================
# Maneja la visualización del perfil personal del aventurero.
# Acceso público mediante PIN para facilitar la experiencia de usuario.
# ==============================================================================

from flask import Blueprint, render_template, abort, redirect, url_for
from db import Member, PointLog, Booking
from datetime import datetime

# Definición del Blueprint
perfil_bp = Blueprint('perfil', __name__)

@perfil_bp.route('/mi-perfil/<string:pin>')
def ver_perfil(pin):
    """
    Renderiza la vista completa del perfil del aventurero.
    Muestra datos personales, saldo, nivel (calculado) e historial.
    """
    # 1. Búsqueda del miembro (Si no existe, 404 seguro)
    member = Member.query.filter_by(pin=pin).first()
    
    if not member:
        return render_template('errors/404.html'), 404  # O redirigir a home si prefieres

    # 2. Obtener historial cronológico (Reutilizando la lógica de PointLog)
    # Ordenamos por más reciente primero
    logs = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.desc()).all()

    # 3. Obtener próximas aventuras (Bookings activos futuros)
    proximas_aventuras = []
    bookings = Booking.query.filter_by(member_id=member.id, status='Activo').all()
    today = datetime.now().date()
    
    for b in bookings:
        if b.event.event_date >= today:
            proximas_aventuras.append(b)

    # 4. Cálculo de Nivel de Fidelidad (Gamificación simple)
    # Ejemplo: < 1000: Caminante, 1000-3000: Explorador, > 3000: Leyenda
    nivel = "Caminante"
    icono_nivel = "bi-backpack2"
    clase_nivel = "text-secondary"
    
    pts = member.puntos_totales
    if pts >= 1000 and pts < 3000:
        nivel = "Explorador"
        icono_nivel = "bi-compass-fill"
        clase_nivel = "text-primary"
    elif pts >= 3000:
        nivel = "Leyenda"
        icono_nivel = "bi-trophy-fill"
        clase_nivel = "text-warning"

    # 5. Renderizar
    return render_template(
        'perfil.html',
        member=member,
        logs=logs,
        proximas=proximas_aventuras,
        nivel=nivel,
        icono_nivel=icono_nivel,
        clase_nivel=clase_nivel,
        now=datetime.now()
    )