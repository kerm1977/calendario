from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from db import db, Member, PointLog, Booking, Event, AdminNotification
from sqlalchemy import desc
from datetime import date

# Definición del Blueprint para administración de puntos
puntos_bp = Blueprint('puntos', __name__, url_prefix='/admin/puntos')

def _formatear_log(log):
    """
    Ayudante para transformar el objeto PointLog (Inglés/DB) 
    al formato que espera puntos.html (Español/Vista).
    """
    color = "text-success" if log.amount > 0 else "text-danger"
    icono = "bi-circle-fill"
    
    if log.transaction_type == 'Inscripción':
        icono = "bi-calendar-check"
    elif log.transaction_type == 'Retiro':
        icono = "bi-x-circle"
    elif log.transaction_type == 'Bono Cumpleaños':
        icono = "bi-gift"
        color = "text-primary"
    elif 'Canje' in log.transaction_type:
        icono = "bi-shop"
        color = "text-danger"
    elif log.transaction_type == 'Compra Puntos':
        icono = "bi-cash-coin"
        color = "text-success"
    elif 'Ajuste' in log.transaction_type:
        icono = "bi-pencil-square"
    elif 'Regalo' in log.transaction_type:
        icono = "bi-send-fill" if log.amount < 0 else "bi-gift-fill"
        color = "text-warning" if log.amount < 0 else "text-primary"

    return {
        'fecha': log.created_at,
        'member': f"{log.member.nombre} {log.member.apellido1}",
        'pin': log.member.pin,
        'tipo': log.transaction_type,
        'detalle': log.description,
        'monto': log.amount,
        'puntos': log.amount,
        'color': color,
        'icono': icono
    }

@puntos_bp.route('/ranking')
@login_required
def historial_global():
    """Vista principal: Muestra el ranking general de miembros."""
    if not current_user.is_superuser:
        flash('Acceso restringido a líderes.', 'danger')
        return redirect(url_for('main.home'))

    members = Member.query.order_by(Member.puntos_totales.desc()).all()
    
    return render_template('puntos.html', 
                         members=members, 
                         selected_member=None, 
                         is_global_schedule=False)

@puntos_bp.route('/cronograma')
@login_required
def cronograma_total():
    """Vista de auditoría: Muestra TODOS los movimientos del sistema."""
    if not current_user.is_superuser:
        abort(403)

    raw_logs = PointLog.query.order_by(PointLog.created_at.desc()).limit(200).all()
    formatted_logs = [_formatear_log(log) for log in raw_logs]

    return render_template('puntos.html', 
                         logs=formatted_logs, 
                         selected_member=None, 
                         is_global_schedule=True)

@puntos_bp.route('/miembro/<int:member_id>')
@login_required
def detalle_miembro(member_id):
    """Vista individual: Gestión específica de un miembro."""
    if not current_user.is_superuser:
        abort(403)

    member = Member.query.get_or_404(member_id)
    raw_logs = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.desc()).all()
    movimientos = [_formatear_log(log) for log in raw_logs]
    aventuras_activas = Event.query.filter_by(status='Activa').all()

    return render_template('puntos.html', 
                         selected_member=member,
                         movimientos=movimientos,
                         eventos_activos=aventuras_activas, 
                         is_global_schedule=False)

@puntos_bp.route('/booking/no-show/<int:booking_id>', methods=['POST'])
@login_required
def registrar_no_participacion(booking_id):
    """Acción: Marca que un usuario no asistió y revierte puntos."""
    booking = Booking.query.get_or_404(booking_id)
    member = booking.member
    
    if booking.status in ['Retirado', 'No Participó']:
        flash('Este registro ya fue procesado anteriormente.', 'warning')
        return redirect(request.referrer)

    try:
        puntos_a_restar = booking.points_at_registration or booking.event.points_reward or 0
        member.puntos_totales = max(0, member.puntos_totales - puntos_a_restar)

        log = PointLog(
            member_id=member.id,
            transaction_type='Penalización',
            description=f'No participación: {booking.event.title}',
            amount=-puntos_a_restar,
            booking_id=booking.id,
            is_penalized=True,
            penalty_reason='No presentación al evento'
        )
        db.session.add(log)
        booking.status = 'No Participó'
        
        db.session.add(AdminNotification(
            category='danger',
            title='No Participación (No Show)',
            message=f'{member.nombre} no asistió a "{booking.event.title}". Se restaron {puntos_a_restar} pts.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        
        db.session.commit()
        flash(f'Se registró la inasistencia de {member.nombre}. Se descontaron {puntos_a_restar} puntos.', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar la inasistencia: {str(e)}', 'danger')

    return redirect(url_for('puntos.detalle_miembro', member_id=member.id))

# --- RUTAS DE ACCIÓN ADMIN (Canjes manuales, compras, obsequios) ---

@puntos_bp.route('/accion/canjear-aventura', methods=['POST'])
def canjear_aventura():
    """Canje desde panel admin"""
    member_id = request.form.get('member_id', type=int)
    event_id = request.form.get('event_id', type=int)
    costo_puntos = request.form.get('costo_puntos', type=int)
    
    member = Member.query.get_or_404(member_id)
    event = Event.query.get_or_404(event_id)

    if member.puntos_totales < 5000:
        flash(f'Saldo insuficiente. {member.nombre} necesita al menos 5000 puntos para canjear.', 'danger')
        return redirect(request.referrer)
    
    if member.puntos_totales < costo_puntos:
        flash(f'Saldo insuficiente. Costo: {costo_puntos} pts.', 'danger')
        return redirect(request.referrer)

    try:
        member.puntos_totales -= costo_puntos
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Canje Aventura',
            description=f'Canje: {event.title}',
            amount=-costo_puntos
        ))
        
        db.session.add(AdminNotification(
            category='warning', 
            title='Nuevo Canje de Aventura (Admin)',
            message=f'{member.nombre} canjeó {costo_puntos} pts por "{event.title}".',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'¡Canje exitoso! Se descontaron {costo_puntos} puntos.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(request.referrer)

@puntos_bp.route('/accion/canjear-otro', methods=['POST'])
def canjear_otro():
    """Canje de items desde panel admin"""
    member_id = request.form.get('member_id', type=int)
    descripcion = request.form.get('descripcion')
    costo_puntos = request.form.get('costo_puntos', type=int)
    
    member = Member.query.get_or_404(member_id)

    if member.puntos_totales < 5000:
        flash(f'Saldo insuficiente. Mínimo 5000 pts requeridos.', 'danger')
        return redirect(request.referrer)

    if member.puntos_totales < costo_puntos:
        flash(f'No tiene suficientes puntos ({costo_puntos} pts).', 'danger')
        return redirect(request.referrer)

    try:
        member.puntos_totales -= costo_puntos
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Canje Otro',
            description=f'Canje: {descripcion}',
            amount=-costo_puntos
        ))
        
        db.session.add(AdminNotification(
            category='warning',
            title='Solicitud de Canje (Items)',
            message=f'{member.nombre} canjeó {costo_puntos} pts por: {descripcion}.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'Canje realizado: {descripcion}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(request.referrer)

@puntos_bp.route('/accion/comprar-puntos', methods=['POST'])
def comprar_puntos():
    """Compra de puntos (Admin)"""
    member_id = request.form.get('member_id', type=int)
    cantidad = request.form.get('cantidad', type=int)
    
    if not (1000 <= cantidad <= 10000):
        flash('La compra debe ser entre 1,000 y 10,000 puntos.', 'warning')
        return redirect(request.referrer)

    member = Member.query.get_or_404(member_id)
    
    try:
        member.puntos_totales += cantidad
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Compra Puntos',
            description='Adquisición de paquete de puntos',
            amount=cantidad
        ))
        
        db.session.add(AdminNotification(
            category='success',
            title='Compra de Puntos',
            message=f'¡Ingreso! {member.nombre} compró {cantidad} puntos.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'Se acreditaron {cantidad} puntos a {member.nombre}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(request.referrer)

@puntos_bp.route('/accion/obsequiar-cumple', methods=['POST'])
def obsequiar_cumple():
    """Obsequio Cumpleañero"""
    member_id = request.form.get('member_id', type=int)
    cantidad = request.form.get('cantidad', type=int)
    
    member = Member.query.get_or_404(member_id)
    hoy = date.today()
    
    if not (member.birth_date and member.birth_date.month == hoy.month and member.birth_date.day == hoy.day):
        flash(f'Hoy no es el cumpleaños de {member.nombre}.', 'danger')
        return redirect(request.referrer)
        
    if not (250 <= cantidad <= 1000):
        flash('El obsequio debe ser entre 250 y 1,000 puntos.', 'warning')
        return redirect(request.referrer)

    try:
        member.puntos_totales += cantidad
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Bono Cumpleaños',
            description=f'Obsequio Especial de Admin ({hoy.year})',
            amount=cantidad
        ))
        
        db.session.add(AdminNotification(
            category='info',
            title='Regalo de Cumpleaños Entregado',
            message=f'Se enviaron {cantidad} pts a {member.nombre}.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'¡Regalo enviado a {member.nombre}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(request.referrer)

@puntos_bp.route('/accion/ajuste-saldo', methods=['POST'])
@login_required
def admin_ajuste_saldo():
    """
    Ruta administrativa llamada desde el modal avanzado en puntos.html.
    Gestiona Restitución, Donación y Eliminación (Manual).
    """
    if not current_user.is_superuser:
        abort(403)
        
    member_id = request.form.get('member_id', type=int)
    action = request.form.get('action_type') # 'restituir', 'donar', 'eliminar'
    amount = request.form.get('amount', type=int)
    reason = request.form.get('reason')
    
    member = Member.query.get_or_404(member_id)
    
    try:
        tipo_transaccion = ""
        monto_final = 0
        
        if action == 'restituir':
            member.puntos_totales += amount
            monto_final = amount
            tipo_transaccion = 'Restitución Admin'
            flash(f'Se restituyeron {amount} puntos a {member.nombre}.', 'success')
            
        elif action == 'donar':
            member.puntos_totales += amount
            monto_final = amount
            tipo_transaccion = 'Donación Admin'
            flash(f'Se donaron {amount} puntos a {member.nombre}.', 'success')
            
        elif action == 'eliminar':
            member.puntos_totales = max(0, member.puntos_totales - amount)
            monto_final = -amount
            tipo_transaccion = 'Penalización Admin'
            flash(f'Se eliminaron {amount} puntos de {member.nombre}.', 'warning')
            
        else:
            flash('Acción no reconocida.', 'danger')
            return redirect(request.referrer)

        # Crear Log
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type=tipo_transaccion,
            description=f'{reason} (Por: {current_user.email})',
            amount=monto_final
        ))
        
        # Notificación interna
        db.session.add(AdminNotification(
            category='warning',
            title=f'Gestión de Saldo: {action.upper()}',
            message=f'Admin ejecutó {action} de {amount} pts a {member.nombre}. Razón: {reason}',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error procesando ajuste: {str(e)}', 'danger')
        
    return redirect(request.referrer)