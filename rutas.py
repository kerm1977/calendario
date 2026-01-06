# rutas.py
# ==============================================================================
# GESTIÓN DE RUTAS Y LÓGICA TRANSACCIONAL: LA TRIBU DE LOS LIBRES
# ==============================================================================
# Este archivo centraliza los Blueprints de autenticación y funciones principales,
# incluyendo la API de reservas y los sistemas de auditoría de integridad.
# ==============================================================================

import os
import csv
import random
import logging
import io
from datetime import datetime, date, timedelta, timezone

from flask import (
    render_template, redirect, url_for, request, 
    flash, Blueprint, jsonify, make_response, abort, send_from_directory, current_app
)
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy import extract, desc, func

# --- IMPORTACIÓN DE MODELOS ---
from db import db, bcrypt, User, Member, Event, Booking, PointLog, AdminNotification, SystemConfig

# Configuración de Logging para auditoría técnica.
logger = logging.getLogger(__name__)

# Mapeo universal de meses para la capa de presentación en español.
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# --- ARQUITECTURA MODULAR DE BLUEPRINTS ---
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)

# --- UTILIDADES DE CONFIGURACIÓN DINÁMICA ---
def get_config(key, default_val=""):
    """Recupera un valor de la tabla SystemConfig de forma segura."""
    try:
        conf = SystemConfig.query.filter_by(key=key).first()
        return conf.value if conf else default_val
    except:
        return default_val

# --- UTILIDADES DE PROCESAMIENTO Y LÓGICA DE NEGOCIO ---
def calculate_age(born):
    """
    Algoritmo de precisión para determinar la edad de los aventureros.
    Crucial para logística de seguros y personalización de rutas.
    """
    if not born:
        return "N/A"
    today = date.today()
    try:
        # Se descuenta un año si la fecha actual es anterior al día/mes de nacimiento.
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception as e:
        logger.error(f"Fallo en algoritmo de cálculo de edad: {e}")
        return "N/A"

def to_date(date_str):
    """
    Transformador robusto de cadenas de texto ISO a objetos Date de Python.
    Maneja inputs de formularios HTML y asegura la integridad en la base de datos.
    """
    if not date_str:
        return None
    try:
        # Formato ISO estándar: YYYY-MM-DD
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        # En caso de error, retorna None para evitar caídas del servidor.
        return None

# ==============================================================================
# SECCIÓN 1: GESTIÓN DE ACCESO (BLUEPRINT: AUTH)
# ==============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Ruta administrativa para el ingreso de guías líderes."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        # Validación con hashing Bcrypt.
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('¡Acceso verificado! Bienvenido líder al panel de control.', 'success')
            return redirect(url_for('main.dashboard'))
        
        flash('Credenciales incorrectas. Verifique su PIN o contraseña.', 'danger')
        
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Finaliza la sesión administrativa de forma segura."""
    logout_user()
    flash('Sesión administrativa cerrada. ¡Nos vemos en la ruta!', 'info')
    return redirect(url_for('main.home'))

# ==============================================================================
# SECCIÓN 2: VISTAS PRINCIPALES Y PANEL DE CONTROL (BLUEPRINT: MAIN)
# ==============================================================================

@main_bp.route('/service-worker.js')
def service_worker():
    """Ruta especial para servir el Service Worker desde la raíz del dominio."""
    return send_from_directory(os.path.join(current_app.root_path, 'static', 'js'), 'service-worker.js', mimetype='application/javascript')

@main_bp.route('/')
def home():
    """Catálogo público inteligente. Filtra rutas por mes y cercanía cronológica."""
    search_month = request.args.get('search_month', type=int)
    # FIX: Usar la fecha ajustada a CR (now con timezone)
    today = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)).date()
    query = Event.query
    
    if search_month:
        query = query.filter(extract('month', Event.event_date) == search_month)
    
    # VISIBILIDAD INTELIGENTE:
    # - Usuarios normales: Solo ven eventos futuros o de hoy.
    # - Admins: Ven eventos futuros Y eventos pasados (para poder concluirlos/eliminarlos).
    if not (current_user.is_authenticated and current_user.is_superuser):
        query = query.filter(Event.event_date >= today)
    
    # Mostrar primero las expediciones más próximas a ocurrir.
    events = query.order_by(Event.event_date.asc()).all()
    return render_template('home.html', events=events)

@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    """Panel central con métricas transaccionales, ranking y actividad en vivo."""
    if not current_user.is_superuser:
        flash('Acceso denegado. Se requieren permisos de superusuario.', 'danger')
        return redirect(url_for('main.home'))
    
    # Recopilación de estadísticas dinámicas.
    cr_today_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)
    stats = {
        'total': Event.query.count(),
        'active': Event.query.filter_by(status='Activa').count(),
        'members_count': Member.query.count(),
        # FIX: Ajuste de timezone también aquí para el contador
        'birthdays_count': Member.query.filter(
            extract('month', Member.birth_date) == cr_today_dt.month,
            extract('day', Member.birth_date) == cr_today_dt.day
        ).count(),
        'total_bookings': Booking.query.filter_by(status='Activo').count()
    }
    
    # ACTIVIDAD RECIENTE: Obtenemos reservas activas para monitorear ingresos.
    default_limit = 10
    limit_val = request.args.get('limit', default_limit, type=int)

    bookings = Booking.query.filter_by(status='Activo')\
        .order_by(Booking.created_at.desc())\
        .limit(limit_val)\
        .all()
    
    ranking = Member.query.order_by(Member.puntos_totales.desc()).limit(50).all()
    
    notifications = AdminNotification.query.order_by(
        AdminNotification.is_read.asc(), 
        AdminNotification.created_at.desc()
    ).limit(50).all()
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         bookings=bookings, 
                         ranking=ranking, 
                         notifications=notifications,
                         current_limit=limit_val)

# --- ACTUALIZACIÓN DE CONFIGURACIÓN SINPE ---
@main_bp.route('/admin/settings/update', methods=['POST'])
@login_required
def update_settings():
    """Actualiza los datos de pago SINPE en la tabla de configuración."""
    if not current_user.is_superuser: abort(403)
    
    num = request.form.get('sinpe_number')
    nom = request.form.get('sinpe_name')
    
    configs = {'sinpe_number': num, 'sinpe_name': nom}
    for key, val in configs.items():
        conf = SystemConfig.query.filter_by(key=key).first()
        if conf: conf.value = val
        else: db.session.add(SystemConfig(key=key, value=val))
    
    db.session.commit()
    flash('¡Datos de pago SINPE actualizados correctamente!', 'success')
    return redirect(url_for('main.dashboard'))

# --- RUTA API PARA MARCAR NOTIFICACIONES COMO LEÍDAS ---
@main_bp.route('/admin/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    if not current_user.is_superuser:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        AdminNotification.query.filter_by(is_read=False).update({AdminNotification.is_read: True})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# --- EXPORTACIÓN MASIVA DE MIEMBROS A TXT ---
@main_bp.route('/admin/export/members/txt')
@login_required
def export_all_members_txt():
    """Genera un reporte TXT completo de toda la base de datos de miembros."""
    if not current_user.is_superuser:
        abort(403)

    members = Member.query.order_by(Member.nombre.asc()).all()
    
    output =  "====================================================================================================\n"
    output += "                            LA TRIBU - REPORTE GENERAL DE MIEMBROS                                  \n"
    output += f"                            Fecha de Corte: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    output += "====================================================================================================\n\n"
    
    header = f"{'NOMBRE COMPLETO'.ljust(35)} | {'PIN'.center(8)} | {'TELÉFONO'.center(12)} | {'EDAD'.center(5)} | {'CUMPLEAÑOS'.center(12)} | {'PUNTOS'.rjust(10)}\n"
    output += header
    output += "-" * 105 + "\n"

    total_puntos_sistema = 0

    for m in members:
        edad = calculate_age(m.birth_date)
        cumple = m.birth_date.strftime('%d/%m') if m.birth_date else "N/A"
        nombre_full = f"{m.nombre} {m.apellido1} {m.apellido2 or ''}".strip()
        nombre_fmt = nombre_full[:34].ljust(35)
        
        pin_fmt = m.pin.center(8); tel_fmt = m.telefono.center(12)
        edad_fmt = str(edad).center(5); cumple_fmt = cumple.center(12)
        pts_fmt = str(m.puntos_totales).rjust(10)
        
        total_puntos_sistema += m.puntos_totales
        output += f"{nombre_fmt} | {pin_fmt} | {tel_fmt} | {edad_fmt} | {cumple_fmt} | {pts_fmt}\n"

    output += "-" * 105 + "\n"
    output += f"TOTAL MIEMBROS: {len(members)}\n"
    output += f"TOTAL PUNTOS CIRCULANTES: {total_puntos_sistema}\n"
    output += "====================================================================================================\n"

    response = make_response(output)
    response.headers["Content-Disposition"] = f"attachment; filename=Reporte_Miembros_LaTribu_{datetime.now().strftime('%Y%m%d')}.txt"
    response.headers["Content-type"] = "text/plain; charset=utf-8"
    return response

@main_bp.route('/admin/booking/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """SISTEMA DE RETIRO CON TRAZABILIDAD (POINTLOG)."""
    booking = db.session.get(Booking, booking_id)
    if not booking: abort(404)
    member = booking.member; event = booking.event
    
    if booking.status == 'Retirado':
        flash('Este registro ya consta como retirado.', 'info')
        return redirect(request.referrer)
    
    try:
        pts_a_quitar = booking.points_at_registration or event.points_reward or 10
        member.puntos_totales = max(0, (member.puntos_totales or 0) - pts_a_quitar)
        
        db.session.add(PointLog(
            member_id=member.id, transaction_type='Retiro', 
            description=f'Deducción por retiro: {event.title}', 
            amount=-pts_a_quitar, booking_id=booking.id
        ))
        
        booking.status = 'Retirado'
        booking.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

        db.session.add(AdminNotification(
            category='warning', title='Retiro de Aventura',
            message=f'Admin retiró a {member.nombre} de "{event.title}".',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        
        db.session.commit()
        flash(f'Participación anulada para {member.nombre}. Se debitaron {pts_a_quitar} puntos.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar el retiro: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('main.dashboard'))

@main_bp.route('/admin/member/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    """Eliminación irreversible de un miembro y todo su historial."""
    member = db.session.get(Member, member_id)
    if not member: abort(404)
    try:
        nombre_m = member.nombre
        Booking.query.filter_by(member_id=member.id).delete()
        PointLog.query.filter_by(member_id=member.id).delete()
        
        db.session.add(AdminNotification(
            category='danger', title='Eliminación de Usuario',
            message=f'Se eliminó permanentemente a {nombre_m}.',
            action_link='#'
        ))

        db.session.delete(member)
        db.session.commit()
        flash(f'El miembro {nombre_m} ha sido removido.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'No se pudo eliminar al miembro: {str(e)}', 'danger')
        
    return redirect(url_for('puntos.historial_global'))

# ==============================================================================
# SECCIÓN 3: AUDITORÍA Y AJUSTES MANUALES (ULTRA MASTER)
# ==============================================================================

@main_bp.route('/admin/member/adjust_points', methods=['POST'])
@login_required
def adjust_points():
    """Permite premiar o penalizar puntos manualmente con registro PointLog."""
    if not current_user.is_superuser: abort(403)
    
    member_id = request.form.get('member_id', type=int)
    amount = request.form.get('amount', type=int)
    reason = request.form.get('reason', 'Ajuste manual administrativo')
    
    member = db.session.get(Member, member_id)
    if not member: abort(404)
    try:
        member.puntos_totales = (member.puntos_totales or 0) + amount
        db.session.add(PointLog(
            member_id=member.id, transaction_type='Ajuste Manual', 
            description=reason, amount=amount
        ))
        db.session.add(AdminNotification(
            category='info', title='Ajuste Manual Rápido',
            message=f'Se ajustaron {amount} pts a {member.nombre}.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'Estado de cuenta de {member.nombre} ajustado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al aplicar el ajuste: {str(e)}', 'danger')
    return redirect(request.referrer)

@main_bp.route('/admin/member/integrity_check/<int:member_id>')
@login_required
def integrity_check(member_id):
    """AUDITORÍA DE INTEGRIDAD: Repara el saldo Member.puntos_totales sumando PointLogs."""
    member = db.session.get(Member, member_id)
    if not member: abort(404)
    real_sum = db.session.query(func.sum(PointLog.amount)).filter(PointLog.member_id == member.id).scalar() or 0
    
    if member.puntos_totales != real_sum:
        desfase = real_sum - (member.puntos_totales or 0)
        member.puntos_totales = real_sum
        db.session.add(AdminNotification(
            category='warning', title='Corrección de Integridad',
            message=f'Se corrigió un desfase de {desfase} pts en {member.nombre}.',
            action_link=url_for('puntos.detalle_miembro', member_id=member.id)
        ))
        db.session.commit()
        flash(f'Integridad corregida. Desfase de {desfase} pts.', 'info')
    else:
        flash('El estado de cuenta es 100% íntegro.', 'success')
    return redirect(request.referrer)

# ==============================================================================
# SECCIÓN 4: API ENDPOINTS Y REGISTRO INTELIGENTE
# ==============================================================================

@main_bp.route('/api/check-phone/<string:phone>', methods=['GET'])
def check_phone_exists(phone):
    """Endpoint para prevenir registros duplicados por número de teléfono."""
    try:
        clean_phone = ''.join(filter(str.isdigit, phone))
        member = Member.query.filter_by(telefono=clean_phone).first()
        return jsonify({"exists": bool(member)})
    except Exception as e:
        return jsonify({"exists": False, "error": str(e)})

@main_bp.route('/api/lookup/<string:pin>')
def api_lookup(pin):
    """Endpoint AJAX para consulta de identidad mediante PIN."""
    member = Member.query.filter_by(pin=pin).first()
    if member:
        return jsonify({
            'success': True,
            'id': member.id,
            'nombre': member.nombre,
            'apellido1': member.apellido1,
            'apellido2': member.apellido2,
            'telefono': member.telefono,
            'puntos': member.puntos_totales,
            'birth_date': member.birth_date.strftime('%Y-%m-%d') if member.birth_date else None
        })
    return jsonify({'success': False, 'error': 'El PIN ingresado no está en La Tribu.'})

@main_bp.route('/api/reserve', methods=['POST'])
def api_reserve():
    """LÓGICA MAESTRA DE INSCRIPCIÓN: Registra, suma puntos y genera logs."""
    data = request.json
    try:
        event = db.session.get(Event, data['event_id'])
        if not event: abort(404)
        
        today = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)).date()
        
        member = None
        existing_booking = None 
        es_nuevo = False
        val_pts = event.points_reward or 10
        puntos_ganados_hoy = 0

        provided_pin = data.get('pin')
        if provided_pin:
            member = Member.query.filter_by(pin=provided_pin).first()

        # --- FASE 1: OBTENCIÓN O CREACIÓN DE MIEMBRO ---
        if not member:
            # FLUJO: NUEVO AVENTURERO
            raw_tel = data.get('telefono', '').strip()
            telefono = ''.join(filter(str.isdigit, raw_tel))
            if Member.query.filter_by(telefono=telefono).first():
                return jsonify({'success': False, 'error': 'Ya este número existe. Solicite su PIN a Movil - 86227500'})

            while True:
                new_pin = str(random.randint(100000, 999999))
                if not Member.query.filter_by(pin=new_pin).first(): break
            
            b_date = to_date(data.get('birth_date'))
            WELCOME_BONUS = 500
            puntos_ganados_hoy = val_pts + WELCOME_BONUS
            reg_year_bono = 0
            
            if b_date and b_date.month == today.month and b_date.day == today.day:
                puntos_ganados_hoy += 500
                reg_year_bono = today.year

            member = Member(
                pin=new_pin, nombre=data['nombre'], apellido1=data['apellido1'], 
                apellido2=data.get('apellido2', ''), telefono=telefono,
                birth_date=b_date, puntos_totales=puntos_ganados_hoy, ultimo_regalo_bday=reg_year_bono
            )
            db.session.add(member)
            db.session.flush() 
            
            db.session.add(PointLog(member_id=member.id, transaction_type='Bienvenida', description='Registro Inicial', amount=0))
            db.session.add(PointLog(member_id=member.id, transaction_type='Bono Bienvenida', description='Regalo inicial', amount=WELCOME_BONUS))
            if reg_year_bono > 0:
                db.session.add(PointLog(member_id=member.id, transaction_type='Bono Cumpleaños', description='Bono natalicio inicial', amount=500))
            
            db.session.add(AdminNotification(category='success', title='Nuevo Aventurero', message=f'¡Bienvenida! {member.nombre} se unió.', action_link=url_for('puntos.detalle_miembro', member_id=member.id)))
            es_nuevo = True
        else:
            # FLUJO: MIEMBRO EXISTENTE (USO DE PIN)
            existing_booking = Booking.query.filter_by(member_id=member.id, event_id=event.id).first()
            puntos_ganados_hoy = val_pts
            
            if existing_booking:
                if existing_booking.status != 'Activo':
                    existing_booking.status = 'Activo'
                    existing_booking.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    member.puntos_totales = (member.puntos_totales or 0) + val_pts
                    db.session.add(PointLog(member_id=member.id, transaction_type='Reactivación', description=f'Reincorporación: {event.title}', amount=val_pts, booking_id=existing_booking.id))
                    db.session.add(AdminNotification(category='success', title='Retorno', message=f'{member.nombre} se reactivó.', action_link=url_for('puntos.detalle_miembro', member_id=member.id)))
                    db.session.commit()
                    return jsonify({
                        'success': True, 'pin': member.pin, 'puntos': member.puntos_totales, 
                        'puntos_ganados': val_pts, 'es_nuevo': False,
                        'message': f'Te has registrado satisfactoriamente a esta caminata que tiene un valor de {val_pts}pts'
                    })
                else:
                    return jsonify({'success': False, 'error': 'Ya tienes un cupo activo en esta aventura.'})

            # Caso: Socio antiguo, Aventura nueva
            member.puntos_totales = (member.puntos_totales or 0) + val_pts
            
            if member.birth_date and member.birth_date.month == today.month and member.birth_date.day == today.day:
                if member.ultimo_regalo_bday != today.year:
                    bonus = 500
                    member.puntos_totales += bonus
                    puntos_ganados_hoy += bonus
                    member.ultimo_regalo_bday = today.year
                    db.session.add(PointLog(member_id=member.id, transaction_type='Bono Cumpleaños', description=f'Bono natalicio ({today.year})', amount=bonus))

            db.session.add(AdminNotification(category='info', title='Nueva Inscripción', message=f'{member.nombre} se anotó con PIN.', action_link=url_for('puntos.detalle_miembro', member_id=member.id)))

        # --- FASE 2: CREACIÓN DE LA CAMINATA (BOOKING) ---
        if not existing_booking:
            nueva_reserva = Booking(
                member_id=member.id, 
                event_id=event.id, 
                points_at_registration=val_pts, 
                status='Activo',
                pin=member.pin, nombre=member.nombre, apellido1=member.apellido1, telefono=member.telefono
            )
            db.session.add(nueva_reserva)
            db.session.flush() 

            db.session.add(PointLog(
                member_id=member.id, transaction_type='Inscripción', 
                description=f'Inscripción: {event.title}', 
                amount=val_pts, booking_id=nueva_reserva.id
            ))

        db.session.commit()
        
        return jsonify({
            'success': True, 
            'pin': member.pin, 
            'puntos': member.puntos_totales, 
            'puntos_ganados': puntos_ganados_hoy, 
            'es_nuevo': es_nuevo,
            'message': f'Te has registrado satisfactoriamente a esta caminata que tiene un valor de {val_pts}pts'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error crítico en api_reserve: {str(e)}")
        return jsonify({'success': False, 'error': f"Fallo en servidor: {str(e)}"})