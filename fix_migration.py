import sqlite3
import os

def reparar_base_datos():
    print("--- INICIANDO REPARACIÓN DE BASE DE DATOS ---")
    
    # 1. Buscar el archivo de base de datos
    # Flask suele guardar la DB en 'instance/db.db' o en la raíz 'db.db'
    rutas_posibles = ['instance/db.db', 'db.db']
    db_path = None
    
    for ruta in rutas_posibles:
        if os.path.exists(ruta):
            db_path = ruta
            break
            
    if not db_path:
        print("❌ ERROR: No se encontró el archivo de base de datos (db.db).")
        print("Asegúrate de colocar este archivo en la misma carpeta que 'app.py'.")
        return

    print(f"✅ Base de datos encontrada en: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 2. Verificar columnas actuales en la tabla 'member'
        cursor.execute("PRAGMA table_info(member)")
        columnas_info = cursor.fetchall()
        columnas = [col[1] for col in columnas_info]
        
        print(f"Columnas actuales encontradas: {len(columnas)}")
        
        # 3. Agregar la columna 'debt_pending' si falta
        if 'debt_pending' not in columnas:
            print("🛠️ Agregando columna faltante 'debt_pending'...")
            # Agregamos la columna como BOOLEAN (que en SQLite es INTEGER 0/1) por defecto False (0)
            cursor.execute("ALTER TABLE member ADD COLUMN debt_pending BOOLEAN DEFAULT 0")
            print("   -> ¡Columna agregada exitosamente!")
        else:
            print("✅ La columna 'debt_pending' ya existe. No es necesario hacer nada.")

        # 4. Confirmar cambios y cerrar
        conn.commit()
        conn.close()
        print("\n✨ REPARACIÓN COMPLETADA ✨")
        print("Ya puedes ejecutar tu aplicación (python app.py) sin el error OperationalError.")
        
    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado: {e}")
        print("Intenta borrar el archivo db.db si no tienes datos importantes.")

if __name__ == "__main__":
    reparar_base_datos()