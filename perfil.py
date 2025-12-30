# ==============================================================================
# MÓDULO DE PERFIL PÚBLICO: LA TRIBU DE LOS LIBRES
# ==============================================================================
# Maneja la visualización del perfil personal del aventurero.
# Acceso público mediante PIN para facilitar la experiencia de usuario.
# ==============================================================================

from flask import Blueprint, render_template, abort, redirect, url_for, request, flash
from flask_login import login_required, current_user
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
    Incluye lógica de vencimiento de puntos (Regla de 365 días).
    """
    # 1. Búsqueda del miembro (Si no existe, 404 seguro)
    member = Member.query.filter_by(pin=pin).first()
    
    if not member:
        return render_template('errors/404.html'), 404

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
    cr_time = datetime.utcnow() - timedelta(hours=6)

    # --------------------------------------------------------------------------
    # LÓGICA DE VENCIMIENTO DE PUNTOS (ANUALIDAD) - RESTAURADA
    # --------------------------------------------------------------------------
    # Buscamos la fecha de origen (el primer movimiento de puntos o creación)
    fecha_origen = None
    primer_log = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.asc()).first()
    
    if primer_log:
        fecha_origen = primer_log.created_at.date()
    else:
        # Si no hay logs (raro), usamos hoy como referencia temporal
        fecha_origen = cr_time.date()

    # La fecha de vencimiento es 1 año después del origen
    fecha_vencimiento = fecha_origen + timedelta(days=365)
    dias_restantes = (fecha_vencimiento - cr_time.date()).days
    
    # Datos para el frontend sobre el vencimiento
    info_vencimiento = {
        'fecha_limite': fecha_vencimiento,
        'dias_restantes': dias_restantes,
        'vencido': dias_restantes < 0,
        'penalizacion_pendiente': False
    }

    # Si ya venció, calculamos cuánto sería el 25% (informativo)
    if info_vencimiento['vencido'] and member.puntos_totales > 0:
        info_vencimiento['penalizacion_pendiente'] = True
        info_vencimiento['monto_penalizacion'] = int(member.puntos_totales * 0.25)

    # 5. Renderizar
    return render_template(
        'perfil.html',
        member=member,
        logs=logs,
        proximas=proximas_aventuras,
        nivel=nivel,
        icono_nivel=icono_nivel,
        clase_nivel=clase_nivel,
        now=cr_time,
        vencimiento=info_vencimiento # Pasamos el objeto recuperado
    )

@perfil_bp.route('/accion/cambiar-pin', methods=['POST'])
def cambiar_pin():
    """
    Permite al usuario personalizar su PIN único.
    Reglas: Único globalmente, Alfanumérico, 6-8 caracteres.
    """
    member_id = request.form.get('member_id', type=int)
    nuevo_pin = request.form.get('nuevo_pin', '').strip().upper()
    
    member = Member.query.get_or_404(member_id)
    pin_actual = member.pin

    if not (6 <= len(nuevo_pin) <= 8):
        flash('El PIN debe tener entre 6 y 8 caracteres.', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    if not re.match("^[A-Z0-9]+$", nuevo_pin):
        flash('El PIN solo puede contener letras y números.', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    existe = Member.query.filter_by(pin=nuevo_pin).first()
    if existe:
        flash('Ese PIN ya está en uso por otro aventurero.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    try:
        member.pin = nuevo_pin
        db.session.commit()
        flash(f'¡Éxito! Tu nuevo PIN es: {nuevo_pin}.', 'success')
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
    
    if sender.id == recipient.id:
        flash('No puedes enviarte un regalo a ti mismo.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=sender.pin))

    if sender.puntos_totales < amount:
        flash(f'Saldo insuficiente. Tienes {sender.puntos_totales} puntos.', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=sender.pin))
    
    try:
        sender.puntos_totales -= amount
        db.session.add(PointLog(
            member_id=sender.id,
            transaction_type='Regalo Enviado',
            description=f'Regalo de cumpleaños para {recipient.nombre}',
            amount=-amount
        ))
        
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

@perfil_bp.route('/accion/admin-ajuste', methods=['POST'])
@login_required
def admin_ajuste_saldo():
    """
    Gestión avanzada de saldo para Superusuarios.
    Permite: Restituir, Donar, Eliminar (con validación).
    """
    if not current_user.is_superuser:
        abort(403)

    member_id = request.form.get('member_id', type=int)
    tipo_accion = request.form.get('action_type') # 'restituir', 'donar', 'eliminar'
    monto = request.form.get('amount', type=int)
    motivo = request.form.get('reason')

    member = Member.query.get_or_404(member_id)

    if not monto or monto <= 0:
        flash('El monto debe ser mayor a 0.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=member.pin))

    try:
        if tipo_accion == 'restituir':
            member.puntos_totales += monto
            log = PointLog(
                member_id=member.id,
                transaction_type='Restitución Admin',
                description=f'Restitución: {motivo}',
                amount=monto
            )
            flash(f'Se han restituido {monto} puntos.', 'success')

        elif tipo_accion == 'donar':
            member.puntos_totales += monto
            log = PointLog(
                member_id=member.id,
                transaction_type='Donación Admin',
                description=f'Bono/Regalo: {motivo}',
                amount=monto
            )
            flash(f'Se han donado {monto} puntos.', 'success')

        elif tipo_accion == 'eliminar':
            member.puntos_totales = max(0, member.puntos_totales - monto)
            log = PointLog(
                member_id=member.id,
                transaction_type='Penalización Admin',
                description=f'Deducción: {motivo}',
                amount=-monto,
                is_penalized=True,
                penalty_reason=motivo
            )
            flash(f'Se han eliminado {monto} puntos.', 'warning')
        
        else:
            flash('Acción no reconocida.', 'danger')
            return redirect(url_for('perfil.ver_perfil', pin=member.pin))

        db.session.add(log)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f'Error administrativo: {str(e)}', 'danger')

    return redirect(url_for('perfil.ver_perfil', pin=member.pin))