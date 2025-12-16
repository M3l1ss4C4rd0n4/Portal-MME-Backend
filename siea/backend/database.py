"""
Configuración de la base de datos PostgreSQL para SIEA
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# URL de conexión a PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://siea_app:siea2025_secure@localhost:5432/energia_colombia")

# Motor de SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verificar conexiones antes de usar
    echo=False  # Cambiar a True para debug SQL
)

# Sesión de base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos
Base = declarative_base()

def get_db():
    """
    Dependency para FastAPI - provee sesión de base de datos
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection():
    """
    Prueba de conexión a PostgreSQL
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✅ Conexión exitosa a PostgreSQL")
            print(f"📊 Versión: {version}")
            return True
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False

if __name__ == "__main__":
    test_connection()
