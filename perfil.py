# ==============================================================================
# MÓDULO DE PERFIL PÚBLICO: LA TRIBU DE LOS LIBRES
# ==============================================================================
# Maneja la visualización del perfil personal del aventurero.
# Acceso público mediante PIN para facilitar la experiencia de usuario.
# VERSIÓN: 5.8 (DEBT MANAGEMENT + FULL TRANSACTIONS + ORIGINAL LOGIC)
# ==============================================================================

from flask import Blueprint, render_template, abort, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from db import db, Member, PointLog, Booking, AdminNotification, Event
from sqlalchemy import extract
from datetime import datetime, timedelta, date
import re

# Definición del Blueprint
perfil_bp = Blueprint('perfil', __name__)

# ==============================================================================
# 1. VISTA PRINCIPAL DEL PERFIL
# ==============================================================================
@perfil_bp.route('/mi-perfil/<string:pin>')
def ver_perfil(pin):
    """
    Renderiza la vista completa del perfil del aventurero.
    """
    # A. Búsqueda del miembro
    member = Member.query.filter_by(pin=pin).first()
    
    if not member:
        flash('Perfil no encontrado. Verifique el PIN.', 'danger')
        return redirect(url_for('main.home'))

    # B. Obtener historial cronológico de Puntos (Logs)
    logs = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.desc()).all()

    # --- CORRECCIÓN CRÍTICA DE ZONA HORARIA (CR UTC-6) ---
    # Definimos 'today' y 'cr_time' AL PRINCIPIO para usarlo en toda la lógica
    cr_time = datetime.utcnow() - timedelta(hours=6)
    today = cr_time.date()

    # C. GESTIÓN Y CLASIFICACIÓN DE AVENTURAS
    all_bookings = Booking.query.filter_by(member_id=member.id).all()
    
    proximas_aventuras = []
    bitacora_aventuras = []
    eventos_cancelados = [] # Lista específica para la ventana de penalizaciones
    caminatas_validas_vip = 0 

    for b in all_bookings:
        if not b.event: continue

        # Lógica de conteo VIP (Solo cuentan las activas)
        if b.status == 'Activo':
            caminatas_validas_vip += 1
            
        es_futura = b.event.event_date >= today
        esta_activa = (b.status == 'Activo')
        esta_cancelada = (b.status in ['No Participó', 'Retirado', 'Cancelado'])

        if esta_cancelada:
            # 1. Lógica de Cancelación/Penalización
            # Buscamos si hubo penalización económica (Log negativo asociado al booking)
            penalidad_log = PointLog.query.filter_by(booking_id=b.id).filter(PointLog.amount < 0).first()
            # Asignamos el monto temporalmente al objeto para usarlo en el HTML
            b.monto_penalizacion = abs(penalidad_log.amount) if penalidad_log else 0
            eventos_cancelados.append(b)
            
        elif esta_activa and es_futura:
            # 2. Rutas Activas Futuras -> Mis Próximas Rutas
            proximas_aventuras.append(b)
            
        else:
            # 3. Rutas Pasadas (Completadas) o inactivas sin penalización -> Bitácora
            bitacora_aventuras.append(b)

    # Ordenamiento lógico
    proximas_aventuras.sort(key=lambda x: x.event.event_date)
    eventos_cancelados.sort(key=lambda x: x.event.event_date, reverse=True)
    bitacora_aventuras.sort(key=lambda x: x.event.event_date, reverse=True)

    eventos_activos = Event.query.filter(
        Event.event_date >= today,
        Event.status == 'Activa'
    ).order_by(Event.event_date.asc()).all()

    # D. LÓGICA VIP
    total_caminatas = caminatas_validas_vip
    
    if total_caminatas > 15:
        nivel = "VIP - La Tribu"
        icono_nivel = "bi-crown"
        clase_nivel = "text-warning animate__animated animate__pulse animate__infinite"
        progreso_vip = 100
        mensaje_prox_nivel = "¡Eres un miembro de la élite!"
    elif total_caminatas > 5:
        nivel = "Explorador Constante"
        icono_nivel = "bi-compass-fill"
        clase_nivel = "text-success"
        progreso_vip = int((total_caminatas / 15) * 100)
        mensaje_prox_nivel = f"Faltan {16 - total_caminatas} aventuras para ser VIP"
    else:
        nivel = "Aventurero Iniciado"
        icono_nivel = "bi-backpack2-fill"
        clase_nivel = "text-secondary"
        progreso_vip = int((total_caminatas / 15) * 100)
        mensaje_prox_nivel = f"Completa 15 rutas para el estatus VIP (Llevas {total_caminatas})"

    # E. VENCIMIENTO DE PUNTOS
    primer_log = PointLog.query.filter_by(member_id=member.id).order_by(PointLog.created_at.asc()).first()
    fecha_origen = primer_log.created_at.date() if primer_log else today
    fecha_vencimiento = fecha_origen + timedelta(days=365)
    dias_restantes = (fecha_vencimiento - today).days
    
    info_vencimiento = {
        'fecha_limite': fecha_vencimiento,
        'dias_restantes': dias_restantes,
        'vencido': dias_restantes < 0
    }
    
    # --- LISTA DE CUMPLEAÑEROS (FILTRADO CON HORA CR) ---
    # Esto asegura que el modal de "Regalar" muestre a las personas correctas hoy.
    birthdays_today = Member.query.filter(
        extract('month', Member.birth_date) == today.month,
        extract('day', Member.birth_date) == today.day
    ).all()

    return render_template(
        'perfil.html',
        member=member,
        logs=logs,
        proximas=proximas_aventuras,
        bitacora=bitacora_aventuras,
        eventos_cancelados=eventos_cancelados,
        eventos_activos=eventos_activos, 
        nivel=nivel,
        icono_nivel=icono_nivel,
        clase_nivel=clase_nivel,
        total_caminatas=total_caminatas, 
        progreso_vip=progreso_vip,        
        mensaje_prox_nivel=mensaje_prox_nivel, 
        now=cr_time,
        vencimiento=info_vencimiento,
        birthdays_today=birthdays_today
    )

# ==============================================================================
# 2. RUTAS DE ACCIÓN Y GESTIÓN
# ==============================================================================

@perfil_bp.route('/accion/cambiar-pin', methods=['POST'])
def cambiar_pin():
    """Permite al usuario personalizar su PIN único."""
    member_id = request.form.get('member_id', type=int)
    nuevo_pin = request.form.get('nuevo_pin', '').strip().upper()
    
    member = Member.query.get_or_404(member_id)
    pin_actual = member.pin

    if not (6 <= len(nuevo_pin) <= 8) or not re.match("^[A-Z0-9]+$", nuevo_pin):
        flash('El PIN debe tener entre 6 y 8 caracteres alfanuméricos.', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    existe = Member.query.filter_by(pin=nuevo_pin).first()
    if existe and existe.id != member.id:
        flash('Ese PIN ya está en uso.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))

    try:
        member.pin = nuevo_pin
        db.session.add(AdminNotification(
            category='info', title='Cambio de PIN',
            message=f'{member.nombre} cambió su PIN de seguridad.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'¡Éxito! Tu nuevo PIN es: {nuevo_pin}.', 'success')
        return redirect(url_for('perfil.ver_perfil', pin=nuevo_pin))
    except Exception as e:
        db.session.rollback()
        flash(f'Error técnico: {str(e)}', 'danger')
        return redirect(url_for('perfil.ver_perfil', pin=pin_actual))


@perfil_bp.route('/accion/transferir-regalo', methods=['POST'])
def transferir_regalo():
    """Envío de puntos entre miembros."""
    sender_id = request.form.get('sender_id', type=int)
    recipient_id = request.form.get('recipient_id', type=int)
    amount = request.form.get('cantidad', type=int)
    
    sender = Member.query.get_or_404(sender_id)
    recipient = Member.query.get_or_404(recipient_id)
    
    if sender.id == recipient.id:
        flash('No puedes enviarte un regalo a ti mismo.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=sender.pin))

    if amount <= 0:
        flash('La cantidad a regalar debe ser mayor a cero.', 'danger')
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
        
        db.session.add(AdminNotification(
            category='success',
            title='Intercambio de Puntos',
            message=f'{sender.nombre} regaló {amount} pts a {recipient.nombre}.',
            action_link=url_for('puntos.detalle_miembro', member_id=recipient.id)
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
    """Ajustes manuales por el administrador."""
    if not current_user.is_superuser: abort(403)
    
    member_id = request.form.get('member_id', type=int)
    tipo_accion = request.form.get('action_type')
    monto = request.form.get('amount', type=int)
    motivo = request.form.get('reason')
    
    member = Member.query.get_or_404(member_id)

    if not monto or monto <= 0:
        flash('El monto debe ser mayor a 0.', 'warning')
        return redirect(url_for('perfil.ver_perfil', pin=member.pin))

    try:
        log = None
        if tipo_accion == 'restituir':
            member.puntos_totales += monto
            log = PointLog(
                member_id=member.id,
                transaction_type='Restitución Admin',
                description=f'Restitución: {motivo}',
                amount=monto
            )
            flash(f'Se han restituido {monto} puntos.', 'success')
            
            db.session.add(AdminNotification(
                category='info',
                title='Restitución de Saldo',
                message=f'Admin restituyó {monto} pts a {member.nombre}. Razón: {motivo}',
                action_link=url_for('puntos.detalle_miembro', member_id=member.id)
            ))

        elif tipo_accion == 'donar':
            member.puntos_totales += monto
            log = PointLog(
                member_id=member.id,
                transaction_type='Donación Admin',
                description=f'Bono/Regalo: {motivo}',
                amount=monto
            )
            flash(f'Se han donado {monto} puntos.', 'success')
            
            db.session.add(AdminNotification(
                category='success',
                title='Donación Admin',
                message=f'Se donaron {monto} pts a {member.nombre}. Razón: {motivo}',
                action_link=url_for('puntos.detalle_miembro', member_id=member.id)
            ))

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
            
            db.session.add(AdminNotification(
                category='danger',
                title='Eliminación de Saldo',
                message=f'¡Alerta! Se eliminaron {monto} pts a {member.nombre}. Razón: {motivo}',
                action_link=url_for('puntos.detalle_miembro', member_id=member.id)
            ))
        
        else:
            flash('Acción no reconocida.', 'danger')
            return redirect(url_for('perfil.ver_perfil', pin=member.pin))

        db.session.add(log)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f'Error administrativo: {str(e)}', 'danger')

    return redirect(url_for('perfil.ver_perfil', pin=member.pin))

# ==============================================================================
# 3. LÓGICA DE CANJES Y COMPRAS (FUNCIONES NUEVAS)
# ==============================================================================

@perfil_bp.route('/accion/canjear-aventura', methods=['POST'])
def canjear_aventura():
    """Opción 1: Canjear puntos por una Aventura Activa"""
    member_id = request.form.get('member_id', type=int)
    event_id = request.form.get('event_id', type=int)
    costo_puntos = request.form.get('costo_puntos', type=int)
    
    member = Member.query.get_or_404(member_id)
    event = Event.query.get_or_404(event_id)

    if member.puntos_totales < 5000:
        flash('Saldo insuficiente. Se requieren 5000 puntos mínimos para canjear.', 'danger')
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
            title='Nuevo Canje de Aventura',
            message=f'{member.nombre} canjeó {costo_puntos} pts por "{event.title}".',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        
        db.session.commit()
        flash(f'¡Canje exitoso! Se descontaron {costo_puntos} puntos.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error procesando el canje: {str(e)}', 'danger')

    return redirect(request.referrer)

@perfil_bp.route('/accion/canjear-otro', methods=['POST'])
def canjear_otro():
    """Opción 2: Canjear puntos por Otros"""
    member_id = request.form.get('member_id', type=int)
    descripcion = request.form.get('descripcion')
    costo_puntos = request.form.get('costo_puntos', type=int)
    
    member = Member.query.get_or_404(member_id)

    if member.puntos_totales < 5000:
        flash('Saldo insuficiente. Mínimo 5000 pts requeridos.', 'danger')
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

@perfil_bp.route('/accion/comprar-puntos', methods=['POST'])
def comprar_puntos():
    """Opción 3: Compra de Puntos (Con Retención del 5%)"""
    member_id = request.form.get('member_id', type=int)
    cantidad_bruta = request.form.get('cantidad', type=int)
    
    if not (1000 <= cantidad_bruta <= 10000):
        flash('La compra debe ser entre 1,000 y 10,000 puntos.', 'warning')
        return redirect(request.referrer)

    member = Member.query.get_or_404(member_id)
    
    try:
        # --- CÁLCULO FINANCIERO: RETENCIÓN 5% ---
        # Si compra 1000, se retienen 50. El usuario recibe 950.
        deduccion = int(cantidad_bruta * 0.05) 
        cantidad_neta = cantidad_bruta - deduccion
        
        # Acreditar solo el NETO
        member.puntos_totales += cantidad_neta
        
        # Registro transparente en el historial
        db.session.add(PointLog(
            member_id=member.id,
            transaction_type='Compra Puntos',
            description=f'Compra: {cantidad_bruta} pts (-{deduccion} gastos admin)',
            amount=cantidad_neta
        ))
        
        # Notificación al Admin con el desglose
        db.session.add(AdminNotification(
            category='success',
            title='Ingreso por Compra de Puntos',
            message=f'{member.nombre} compró {cantidad_bruta} pts. Neto acreditado: {cantidad_neta}. Retención Admin: {deduccion}.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        
        db.session.commit()
        flash(f'Compra exitosa. Se acreditaron {cantidad_neta} puntos (se descontó el 5% por gastos administrativos).', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error en la compra: {str(e)}', 'danger')

    return redirect(request.referrer)

# ==============================================================================
# 5. API: TOGGLE DEUDA (NUEVO)
# ==============================================================================
@perfil_bp.route('/admin/toggle_debt/<int:member_id>', methods=['POST'])
@login_required
def toggle_debt(member_id):
    """
    Alterna el estado de deuda pendiente del miembro.
    Solo accesible por SuperAdmin.
    """
    if not current_user.is_superuser:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
        
    member = Member.query.get_or_404(member_id)
    
    # Invertir estado
    member.debt_pending = not member.debt_pending
    db.session.commit()
    
    status_text = "Pendiente" if member.debt_pending else "Al Día"
    
    return jsonify({
        'success': True, 
        'new_status': member.debt_pending, 
        'message': f'Estado de deuda actualizado a: {status_text}'
    })