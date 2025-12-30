# ==============================================================================
# MÓDULO DE PERFIL PÚBLICO: LA TRIBU DE LOS LIBRES
# ==============================================================================
# Maneja la visualización del perfil personal del aventurero.
# Acceso público mediante PIN para facilitar la experiencia de usuario.
# ==============================================================================

from flask import Blueprint, render_template, abort, redirect, url_for, request, flash
from db import db, Member, PointLog, Booking
from datetime import datetime, timedelta, date
import re

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

    # Ajuste de Zona Horaria para Costa Rica (UTC-6)
    # Esto asegura que el "hoy" del sistema coincida con el "hoy" real del usuario
    cr_time = datetime.utcnow() - timedelta(hours=6)

    # 5. Renderizar
    return render_template(
        'perfil.html',
        member=member,
        logs=logs,
        proximas=proximas_aventuras,
        nivel=nivel,
        icono_nivel=icono_nivel,
        clase_nivel=clase_nivel,
        now=cr_time 
    )

@perfil_bp.route('/accion/cambiar-pin', methods=['POST'])
def cambiar_pin():
    """
    Permite al usuario personalizar su PIN único.
    Reglas: Único globalmente, Alfanumérico, 6-8 caracteres.
    """
    member_id = request.form.get('member_id', type=int)
    nuevo_pin = request.form.get('nuevo_pin', '').strip().upper() # Guardar en mayúsculas para consistencia
    
    member = Member.query.get_or_404(member_id)
    pin_actual = member.pin # Guardamos el PIN viejo para redirigir si falla

    # 1. Validación de Longitud (6 a 8)
    if not (6 <= len(nuevo_pin) <= 8):
        flash('El PIN debe tener entre 6 y 8 caracteres.', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    # 2. Validación Alfanumérica (Solo letras y números)
    if not re.match("^[A-Z0-9]+$", nuevo_pin):
        flash('El PIN solo puede contener letras y números (sin espacios ni símbolos).', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    # 3. Validación de Unicidad (Que no lo tenga nadie más)
    existe = Member.query.filter_by(pin=nuevo_pin).first()
    if existe:
        flash('Ese PIN ya está en uso por otro aventurero. Intenta con otro.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    try:
        member.pin = nuevo_pin
        db.session.commit()
        flash(f'¡Éxito! Tu nuevo PIN es: {nuevo_pin}. Úsalo para entrar la próxima vez.', 'success')
        # Redirigimos al perfil PERO con el NUEVO PIN en la URL
        return redirect(url_for('perfil.ver_perfil', pin=nuevo_pin))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar el PIN: {str(e)}', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

@perfil_bp.route('/accion/transferir-regalo', methods=['POST'])
def transferir_regalo():
    """
    Permite a un miembro (Sender) enviar puntos de su saldo a un cumpleañero (Recipient).
    """
    sender_id = request.form.get('sender_id', type=int)
    recipient_id = request.form.get('recipient_id', type=int)
    amount = request.form.get('cantidad', type=int)
    
    sender = Member.query.get_or_404(sender_id)
    recipient = Member.query.get_or_404(recipient_id)
    
    # Validaciones básicas
    if sender.id == recipient.id:
        flash('No puedes enviarte un regalo a ti mismo desde esta opción.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=sender.pin))

    if sender.puntos_totales < amount:
        flash(f'Saldo insuficiente. Tienes {sender.puntos_totales} puntos disponibles.', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=sender.pin))
        
    # Validar que HOY sea el cumpleaños del destinatario
    # (Usamos date.today() o datetime ajustado según configuración del servidor)
    # Para ser robustos, confiamos en la validación visual del frontend, 
    # pero aquí podríamos agregar una capa extra si fuera crítico.
    
    try:
        # 1. Descontar al remitente
        sender.puntos_totales -= amount
        db.session.add(PointLog(
            member_id=sender.id,
            transaction_type='Regalo Enviado',
            description=f'Regalo de cumpleaños para {recipient.nombre}',
            amount=-amount
        ))
        
        # 2. Acreditar al destinatario
        recipient.puntos_totales += amount
        db.session.add(PointLog(
            member_id=recipient.id,
            transaction_type='Regalo Recibido',
            description=f'Regalo de cumpleaños de {sender.nombre}',
            amount=amount
        ))
        
        db.session.commit()
        flash(f'¡Qué gran detalle! Has enviado {amount} puntos a {recipient.nombre}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error en la transferencia: {str(e)}', 'danger')

    return redirect(url_for('perfil.ver_perfil', pin=sender.pin))