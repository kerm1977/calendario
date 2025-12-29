# ==============================================================================
# MÓDULO DE AUDITORÍA Y FIDELIZACIÓN: LA TRIBU DE LOS LIBRES (VERSIÓN 2026)
# ==============================================================================
# Este archivo centraliza la lógica de visualización del "Libro Mayor" de puntos.
# Utiliza la tabla PointLog como fuente única de verdad para garantizar que
# el registro cronológico sea 100% veraz e inalterable.
# ==============================================================================

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime
import logging

# --- IMPORTACIÓN DE MODELOS E INFRAESTRUCTURA DE PERSISTENCIA ---
# PointLog: Contiene el rastro transaccional de cada punto ganado o perdido.
# Member: Proporciona la identidad del aventurero y su saldo de caché.
# Booking/Event: Permiten relacionar los movimientos con rutas específicas.
from db import db, Member, Booking, Event, PointLog

# Configuración del motor de registro para trazabilidad de acciones administrativas
logger = logging.getLogger(__name__)

# Definición del Blueprint modular para la sección de puntos y auditoría
puntos_bp = Blueprint('puntos', __name__)

# ==============================================================================
# RUTA 1: Historial Global (Ranking de Aventureros)
# ==============================================================================
@puntos_bp.route('/admin/puntos')
@login_required
def historial_global():
    """
    VISTA ADMINISTRATIVA MAESTRA:
    Muestra el listado de todos los miembros ordenados por saldo real.
    """
    if not current_user.is_authenticated or not current_user.is_superuser:
        logger.warning(f"Intento de acceso no autorizado al ranking por: {current_user.email}")
        flash('Acceso denegado. Se requiere nivel de Superusuario para auditar la tribu.', 'danger')
        return redirect(url_for('main.home'))
    
    try:
        members = Member.query.order_by(Member.puntos_totales.desc()).all()
        logger.info(f"Admin {current_user.email} generó el ranking global de fidelidad.")
        return render_template('puntos.html', members=members)
        
    except Exception as e:
        logger.error(f"FALLO CRÍTICO al cargar el ranking global: {str(e)}")
        db.session.rollback()
        flash('Error de servidor al recuperar el listado de miembros de La Tribu.', 'danger')
        return redirect(url_for('main.dashboard'))

# ==============================================================================
# RUTA 2: Detalle de Miembro (El Libro Mayor Individual)
# ==============================================================================
@puntos_bp.route('/admin/puntos/miembro/<int:member_id>')
@login_required
def detalle_miembro(member_id):
    """
    VISTA DE AUDITORÍA PROFUNDA (Trazabilidad Total):
    Muestra CUALQUIER movimiento que haya afectado el saldo.
    """
    if not current_user.is_authenticated or not current_user.is_superuser:
        flash('Privilegios insuficientes para ver el historial privado.', 'danger')
        return redirect(url_for('main.home'))
    
    member = Member.query.get_or_404(member_id)
    
    try:
        logs = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.desc()).all()
        movimientos = []
        
        for log in logs:
            # Mapeo visual extendido
            ui_map = {
                'Inscripción': {'icono': 'bi-geo-alt-fill', 'color': 'text-success', 'etiqueta': 'SUMA'},
                'Retiro': {'icono': 'bi-person-dash-fill', 'color': 'text-danger', 'etiqueta': 'RESTA'},
                'No Participó': {'icono': 'bi-x-octagon-fill', 'color': 'text-danger', 'etiqueta': 'PENALIZACIÓN'},
                'Bono Cumpleaños': {'icono': 'bi-gift-fill', 'color': 'text-primary', 'etiqueta': 'BONO'},
                'Ajuste Manual': {'icono': 'bi-pencil-square', 'color': 'text-warning', 'etiqueta': 'AJUSTE'}
            }
            
            config = ui_map.get(log.transaction_type, {
                'icono': 'bi-dot', 'color': 'text-secondary', 'etiqueta': 'LOG'
            })
            
            movimientos.append({
                'id_log': log.id,
                'tipo': log.transaction_type,
                'detalle': log.description,
                'fecha': log.created_at,
                'puntos': log.amount,
                'icono': config['icono'],
                'color': config['color'],
                'etiqueta': config['etiqueta']
            })
        
        logger.info(f"Historial individual generado para PIN: {member.pin}")
        
        return render_template(
            'puntos.html', 
            selected_member=member, 
            movimientos=movimientos,
            now=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Fallo generando auditoría para ID {member_id}: {str(e)}")
        flash('No se pudo procesar el historial contable de este miembro.', 'danger')
        return redirect(url_for('puntos.historial_global'))

# ==============================================================================
# RUTA 3: Cronograma Maestro Global
# ==============================================================================
@puntos_bp.route('/admin/puntos/cronograma-total')
@login_required
def cronograma_total():
    if not current_user.is_superuser: abort(403)
    try:
        all_logs = PointLog.query.order_by(PointLog.created_at.desc()).limit(100).all()
        ui_logs = []
        for log in all_logs:
            impacto_color = "text-success" if log.amount > 0 else "text-danger"
            if log.transaction_type == 'Ajuste Manual': impacto_color = "text-warning"
            
            ui_logs.append({
                'member': f"{log.member.nombre} {log.member.apellido1}",
                'pin': log.member.pin,
                'tipo': log.transaction_type,
                'detalle': log.description,
                'fecha': log.created_at,
                'monto': log.amount,
                'color': impacto_color
            })
        return render_template('puntos.html', logs=ui_logs, is_global_schedule=True)
    except Exception as e:
        flash('No se pudo cargar el cronograma maestro.', 'danger')
        return redirect(url_for('main.dashboard'))

# ==============================================================================
# RUTA 4: API de Historial
# ==============================================================================
@puntos_bp.route('/api/v1/member/history/<string:pin>')
def api_member_history(pin):
    if not pin or len(pin) != 6: return jsonify({'success': False, 'error': 'PIN inválido.'}), 400
    member = Member.query.filter_by(pin=pin).first()
    if not member: return jsonify({'success': False, 'error': 'Identidad no localizada.'}), 404
        
    logs = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.desc()).limit(15).all()
    historial_json = [{'fecha': l.created_at.strftime('%d/%m/%Y'), 'motivo': l.description, 'puntos': l.amount} for l in logs]
    
    return jsonify({'success': True, 'nombre': member.nombre, 'saldo': member.puntos_totales, 'historial': historial_json})

# ==============================================================================
# NUEVA RUTA: REGISTRAR NO PARTICIPACIÓN (RESTA PUNTOS SIN BORRAR)
# ==============================================================================
@puntos_bp.route('/admin/booking/no-participa/<int:booking_id>', methods=['POST'])
@login_required
def registrar_no_participacion(booking_id):
    """
    Gestiona cuando un miembro inscrito finalmente NO asiste al evento.
    Acción:
    1. Resta los puntos que se le habían dado (Equilibrio Contable).
    2. Genera un log de 'No Participó' para el historial.
    3. Cambia el estado a 'No Participó' en lugar de borrar el registro.
    """
    if not current_user.is_superuser: abort(403)
    
    booking = Booking.query.get_or_404(booking_id)
    member = booking.member
    event = booking.event
    
    # Validación para no restar doble
    if booking.status in ['Retirado', 'No Participó']:
        flash('Este registro ya fue procesado como inactivo anteriormente.', 'warning')
        return redirect(url_for('puntos.detalle_miembro', member_id=member.id))
    
    try:
        # Recuperamos cuántos puntos valía esta inscripción específica
        puntos_a_reversar = booking.points_at_registration or event.points_reward or 10
        
        # 1. Ajuste de Saldo (Nunca menor a 0)
        member.puntos_totales = max(0, member.puntos_totales - puntos_a_reversar)
        
        # 2. Creación del Log de Auditoría (El rastro visible)
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='No Participó',
            description=f'No asistencia: {event.title}',
            amount=-puntos_a_reversar, # Valor negativo explícito
            booking_id=booking.id
        ))
        
        # 3. Actualización de estado (Sin borrar la fila)
        booking.status = 'No Participó'
        booking.created_at = datetime.utcnow() # Fecha del movimiento
        
        db.session.commit()
        
        logger.info(f"Registrada no participación de {member.nombre} en {event.title}. Puntos descontados: {puntos_a_reversar}")
        flash(f'Se registró la no participación en "{event.title}". Se descontaron {puntos_a_reversar} puntos del saldo.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al registrar no participación ID {booking_id}: {e}")
        flash(f'Error al procesar la solicitud: {str(e)}', 'danger')
        
    return redirect(url_for('puntos.detalle_miembro', member_id=member.id))