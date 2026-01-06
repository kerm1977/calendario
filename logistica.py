# logistica.py
# ==============================================================================
# GESTIÓN LOGÍSTICA Y CALENDARIO: LA TRIBU DE LOS LIBRES
# ==============================================================================
# Este archivo maneja la publicación de eventos, el calendario administrativo
# y las herramientas de exportación de datos para los guías.
# Se han distribuido las rutas entre 'main' y 'calendar_view' para mantener
# compatibilidad con las plantillas HTML existentes.
# ==============================================================================

import os
import csv
import calendar
import logging
import io
from datetime import datetime, date, timedelta, timezone

from flask import (
    render_template, redirect, url_for, request, 
    flash, Blueprint, make_response, abort, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import extract

from db import db, Member, Event, Booking, PointLog, AdminNotification
# Importamos utilidades y el blueprint principal para resolver errores de url_for
from rutas import to_date, calculate_age, MESES_ES, main_bp

# Configuración de Logging
logger = logging.getLogger(__name__)

# Blueprints - Registrado en app.py como 'calendar_view'
calendar_bp = Blueprint('calendar_view', __name__)

# ==============================================================================
# SECCIÓN 3: AUDITORÍA Y AJUSTES MANUALES (HERRAMIENTA LOGÍSTICA)
# ==============================================================================

# Se asigna a main_bp porque calendar.html usa url_for('main.export_participants')
@main_bp.route('/admin/event/export/<int:event_id>')
@login_required
def export_participants(event_id):
    """
    HERRAMIENTA LOGÍSTICA PARA GUÍAS:
    Genera un archivo CSV con la lista de participantes activos para uso offline.
    """
    event = db.session.get(Event, event_id)
    if not event: abort(404)
    active_list = Booking.query.filter_by(event_id=event.id, status='Activo').all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['AVENTURERO', 'TELÉFONO', 'PIN', 'EDAD', 'FECHA INSCRIPCIÓN'])
    
    for b in active_list:
        age = calculate_age(b.member.birth_date)
        writer.writerow([
            f"{b.member.nombre} {b.member.apellido1}", 
            b.member.telefono, 
            b.member.pin, 
            age, 
            b.created_at.strftime('%d/%m/%Y')
        ])
        
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=logistica_tribu_{event.id}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

# ==============================================================================
# SECCIÓN 4: EXPORTACIÓN LOGÍSTICA GLOBAL (TXT) - NUEVO REQUERIMIENTO
# ==============================================================================

@calendar_bp.route('/admin/export-active-txt')
@login_required
def export_active_txt():
    """
    Genera un archivo .txt con el estado de las caminatas activas.
    Incluye: Fecha, precio, puntos y lista numerada 1..Capacidad con PIN y Tel.
    Visible para el botón en base.html (calendar_view.export_active_txt).
    """
    if not current_user.is_superuser:
        abort(403)
        
    # Obtener eventos activos (hoy o futuro) ordenados por fecha
    active_events = Event.query.filter(Event.event_date >= date.today()).order_by(Event.event_date).all()
    
    output = io.StringIO()
    output.write("==========================================================\n")
    output.write("        ESTADO DE EXPEDICIONES ACTIVAS - LA TRIBU        \n")
    output.write(f"        Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}        \n")
    output.write("==========================================================\n\n")
    
    if not active_events:
        output.write("No hay caminatas activas programadas en este momento.\n")
    
    for ev in active_events:
        output.write(f"📍 AVENTURA: {ev.title.upper()}\n")
        output.write(f"📅 FECHA: {ev.event_date.strftime('%d/%m/%Y')} | HORA: {ev.departure_time}\n")
        output.write(f"💰 PRECIO: {ev.currency}{ev.price:,.0f} | ⭐ PUNTOS: +{ev.points_reward or 10} pts\n")
        output.write(f"👥 CAPACIDAD GRUPO: {ev.capacity} personas\n")
        output.write("-" * 58 + "\n")
        output.write("LISTA DE ASISTENCIA (NOMBRE, PIN, TELÉFONO):\n")
        
        # Filtrar bookings activos
        active_bookings = [b for b in ev.bookings if b.status == 'Activo']
        
        # Generar lista numerada del 1 al Límite de Capacidad (ej. 1 al 17)
        for i in range(1, ev.capacity + 1):
            if i <= len(active_bookings):
                b = active_bookings[i-1]
                m = b.member
                nombre_completo = f"{m.nombre} {m.apellido1} {m.apellido2 or ''}".strip()
                # Formato: 01. Nombre Completo - PIN: ABC123 - Tel: 88888888
                output.write(f"{i:02d}. {nombre_completo:<30} | PIN: {m.pin} | Tel: {m.telefono}\n")
            else:
                # Espacio disponible numerado hasta el límite de capacidad solicitado
                output.write(f"{i:02d}. [ ESPACIO DISPONIBLE ]\n")
        
        output.write("\n" + "="*58 + "\n\n")

    response = make_response(output.getvalue())
    file_name = f"Logistica_LaTribu_{date.today().strftime('%d_%m_%Y')}.txt"
    response.headers["Content-Disposition"] = f"attachment; filename={file_name}"
    response.headers["Content-type"] = "text/plain; charset=utf-8"
    
    return response

# ==============================================================================
# SECCIÓN 5: GESTIÓN LOGÍSTICA DE CALENDARIO Y EVENTOS (BLUEPRINT: CALENDAR)
# ==============================================================================

@calendar_bp.route('/admin/calendar')
@login_required
def view():
    """Generador de cuadrícula administrativa mensual con logística detallada."""
    cr_today_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)
    year = request.args.get('year', cr_today_dt.year, type=int)
    month = request.args.get('month', cr_today_dt.month, type=int)
    
    if month > 12: month = 1; year += 1
    elif month < 1: month = 12; year -= 1

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    
    events = Event.query.all()
    monthly_birthdays = Member.query.filter(extract('month', Member.birth_date) == month).all()
    
    return render_template('calendar.html', 
                            weeks=weeks, year=year, month=month, 
                            month_name=MESES_ES[month],
                            events=events,
                            monthly_birthdays=monthly_birthdays)

@calendar_bp.route('/admin/event/add', methods=['POST'])
@login_required
def add_event():
    """Publica una nueva expedición procesando los 21 campos logísticos del sistema."""
    
    if 'flyer' not in request.files:
        print("ALERTA: No se encontró la parte 'flyer' en la solicitud.")
    else:
        file = request.files['flyer']
        if file.filename == '':
            print("ALERTA: El usuario no seleccionó ningún archivo.")
        else:
            print(f"ÉXITO: Archivo recibido: {file.filename}")

    file = request.files.get('flyer')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    
    if filename:
        try:
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        except Exception as e:
            print(f"ERROR GUARDANDO ARCHIVO: {e}")
            flash(f'Error al guardar la imagen: {str(e)}', 'warning')

    try:
        new_ev = Event(
            title=request.form.get('title'),
            flyer=filename,
            currency=request.form.get('currency', '¢'),
            price=float(request.form.get('price') or 0),
            points_reward=int(request.form.get('points_reward') or 10),
            activity_type=request.form.get('activity_type'),
            duration_days=int(request.form.get('duration_days') or 1),
            event_date=to_date(request.form.get('event_date')),
            end_date=to_date(request.form.get('end_date')),
            departure_point=request.form.get('departure_point'),
            departure_time=request.form.get('departure_time'),
            difficulty=request.form.get('difficulty'),
            distance=request.form.get('distance'),
            capacity=int(request.form.get('capacity') or 0),
            reservation_fee=request.form.get('reservation_fee'),
            description=request.form.get('description'),
            pickup_point=request.form.get('pickup_point'),
            status=request.form.get('status') or 'Activa',
            moved_date=to_date(request.form.get('moved_date'))
        )
        db.session.add(new_ev)
        
        db.session.add(AdminNotification(
            category='info',
            title='Nueva Aventura Creada',
            message=f'Se publicó la aventura "{new_ev.title}" para el {new_ev.event_date}.',
            action_link='#'
        ))
        
        db.session.commit()
        flash('¡Aventura publicada con éxito!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo técnico creando expedición: {e}")
        flash(f'Error al crear el evento: {str(e)}', 'danger')
            
    return redirect(url_for('calendar_view.view'))

@calendar_bp.route('/admin/event/edit/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    """Actualización total de logística y mantenimiento físico de imágenes."""
    ev = db.session.get(Event, event_id)
    if not ev: abort(404)
    file = request.files.get('flyer')
    
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        if ev.flyer:
            try:
                old_p = os.path.join(current_app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(old_p): os.remove(old_p)
            except Exception as e:
                logger.warning(f"No se pudo limpiar el flyer antiguo ID {ev.id}: {e}")
        ev.flyer = filename

    try:
        ev.title = request.form.get('title')
        ev.currency = request.form.get('currency')
        ev.price = float(request.form.get('price') or 0)
        ev.points_reward = int(request.form.get('points_reward') or 10)
        ev.activity_type = request.form.get('activity_type')
        ev.duration_days = int(request.form.get('duration_days') or 1)
        ev.event_date = to_date(request.form.get('event_date'))
        ev.end_date = to_date(request.form.get('end_date'))
        ev.departure_point = request.form.get('departure_point')
        ev.departure_time = request.form.get('departure_time')
        ev.difficulty = request.form.get('difficulty')
        ev.distance = request.form.get('distance')
        ev.capacity = int(request.form.get('capacity') or 0)
        ev.reservation_fee = request.form.get('reservation_fee')
        ev.description = request.form.get('description')
        ev.pickup_point = request.form.get('pickup_point')
        ev.status = request.form.get('status')
        ev.moved_date = to_date(request.form.get('moved_date'))
        
        db.session.add(AdminNotification(
            category='info',
            title='Aventura Modificada',
            message=f'Se actualizaron los detalles de la ruta "{ev.title}".',
            action_link='#'
        ))
        
        db.session.commit()
        flash('Datos de expedición actualizados correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editando evento {event_id}: {e}")
        flash(f'Fallo al guardar cambios: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('main.home'))

# --- RUTAS DE CICLO DE VIDA (CONCLUIR / ELIMINAR) ---

@calendar_bp.route('/admin/event/conclude/<int:event_id>')
@login_required
def conclude_event(event_id):
    """
    ELIMINACIÓN SEGURA (CONCLUIR):
    Borra el evento de la cartelera y las reservas, PERO MANTIENE LOS PUNTOS.
    """
    if not current_user.is_superuser: abort(403)
    ev = db.session.get(Event, event_id)
    if not ev: abort(404)
    titulo = ev.title
    
    try:
        bookings = Booking.query.filter_by(event_id=ev.id).all()
        for b in bookings:
            logs = PointLog.query.filter_by(booking_id=b.id).all()
            for l in logs:
                l.booking_id = None
                if "Histórico" not in l.description:
                    l.description += " (Evento Concluido)"
        
        db.session.commit()

        if ev.flyer:
            try:
                path = os.path.join(current_app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(path): os.remove(path)
            except Exception: pass
        
        db.session.delete(ev)
        
        db.session.add(AdminNotification(
            category='success',
            title='Caminata Concluida',
            message=f'El evento "{titulo}" se cerró correctamente.',
            action_link='#'
        ))
        
        db.session.commit()
        flash(f'Caminata "{titulo}" concluida e historial preservado.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error concluyendo evento {event_id}: {e}")
        flash(f'Error al concluir evento: {str(e)}', 'danger')

    return redirect(url_for('main.home'))

@calendar_bp.route('/admin/event/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    """
    ELIMINACIÓN RADICAL (BASURERO):
    Borra evento, reservas Y REVIERTE LOS PUNTOS ganados.
    """
    if not current_user.is_superuser: abort(403)
    ev = db.session.get(Event, event_id)
    if not ev: abort(404)
    titulo = ev.title
    
    try:
        bookings = Booking.query.filter_by(event_id=ev.id).all()
        puntos_revocados_total = 0
        
        for b in bookings:
            logs = PointLog.query.filter_by(booking_id=b.id).all()
            for l in logs:
                if l.amount > 0:
                    b.member.puntos_totales = max(0, b.member.puntos_totales - l.amount)
                    puntos_revocados_total += l.amount
                    db.session.delete(l)
        
        if ev.flyer:
            try:
                path = os.path.join(current_app.config['UPLOAD_FOLDER'], ev.flyer)
                if os.path.exists(path): os.remove(path)
            except Exception: pass
        
        db.session.delete(ev)
        
        db.session.add(AdminNotification(
            category='danger',
            title='Aventura Eliminada (Radical)',
            message=f'"{titulo}" eliminada. Se revocaron {puntos_revocados_total} pts.',
            action_link='#'
        ))
        
        db.session.commit()
        flash(f'Evento "{titulo}" eliminado y puntos revocados.', 'warning')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fallo borrando evento {event_id}: {e}")
        flash(f'No se pudo eliminar el evento: {str(e)}', 'danger')
        
    return redirect(url_for('main.home'))