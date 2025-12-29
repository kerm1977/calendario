from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date
# Importamos desde db.py para romper el ciclo de dependencia con app.py
from db import db, Member, Booking, Event

# Definición del Blueprint para la sección de fidelidad y auditoría
puntos_bp = Blueprint('puntos', __name__)

@puntos_bp.route('/admin/puntos')
@login_required
def historial_global():
    """
    Vista administrativa maestra que lista a todos los miembros de La Tribu
    ordenados por el ranking de puntos acumulados.
    """
    if not current_user.is_superuser:
        flash('Acceso denegado. Se requiere nivel de Superusuario.', 'danger')
        return redirect(url_for('main.home'))
    
    # Ranking global: de más puntos a menos puntos
    members = Member.query.order_by(Member.puntos_totales.desc()).all()
    return render_template('puntos.html', members=members)

@puntos_bp.route('/admin/puntos/miembro/<int:member_id>')
@login_required
def detalle_miembro(member_id):
    """
    Vista de auditoría profunda. Reconstruye cronológicamente cada punto
    ganado por un miembro, normalizando los tipos de fecha para evitar errores.
    """
    if not current_user.is_superuser:
        return redirect(url_for('main.home'))
    
    member = Member.query.get_or_404(member_id)
    
    # Reconstrucción manual de la línea de tiempo de puntos
    movimientos = []
    
    # 1. Puntos ganados por inscripciones reales (Expediciones) - Tipo: datetime
    for b in member.bookings:
        movimientos.append({
            'tipo': 'Aventura',
            'detalle': b.event.title,
            'fecha': b.created_at, # Este es un objeto datetime
            'puntos': b.event.points_reward or 10,
            'icono': 'bi-geo-alt-fill',
            'color': 'text-success'
        })
    
    # 2. Puntos ganados por el Bono de la Tribu (Cumpleaños) - Tipo: date
    if member.ultimo_regalo_bday > 0:
        try:
            fecha_bono_date = member.birth_date.replace(year=member.ultimo_regalo_bday)
        except ValueError:
            # Manejo para nacidos el 29 de febrero en años no bisiestos
            fecha_bono_date = member.birth_date.replace(year=member.ultimo_regalo_bday, day=28)
            
        # FIX: Convertimos el objeto date a datetime para que sea comparable con las reservas
        fecha_bono_dt = datetime.combine(fecha_bono_date, datetime.min.time())
            
        movimientos.append({
            'tipo': 'Bono Anual',
            'detalle': f'Celebración de Cumpleaños {member.ultimo_regalo_bday}',
            'fecha': fecha_bono_dt,
            'puntos': 500,
            'icono': 'bi-gift-fill',
            'color': 'text-primary'
        })
    
    # Función auxiliar de normalización para asegurar que la ordenación nunca falle
    def normalize_for_sort(val):
        if isinstance(val, datetime):
            return val
        if isinstance(val, date):
            return datetime.combine(val, datetime.min.time())
        return datetime.min

    # Ordenar: lo más reciente aparece arriba (descendente)
    # Usamos la normalización para evitar el TypeError entre date y datetime
    movimientos.sort(key=lambda x: normalize_for_sort(x['fecha']), reverse=True)
    
    return render_template('puntos.html', selected_member=member, movimientos=movimientos)