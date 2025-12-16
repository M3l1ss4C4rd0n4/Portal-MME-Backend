"""
Modelos SQLAlchemy para schema XM (datos de mercado eléctrico)
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, Index
from database import Base

class GeneracionReal(Base):
    """Generación real por recurso y hora"""
    __tablename__ = "generacion_real"
    __table_args__ = {'schema': 'xm'}
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False, index=True)
    hora = Column(Integer, nullable=False)  # 0-23
    recurso = Column(String(100), nullable=False, index=True)
    valor_mwh = Column(Float, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)
    
    # Índice compuesto para consultas rápidas
    __table_args__ = (
        Index('idx_generacion_fecha_recurso', 'fecha', 'recurso'),
        {'schema': 'xm'}
    )

class DemandaReal(Base):
    """Demanda real del sistema por hora"""
    __tablename__ = "demanda_real"
    __table_args__ = {'schema': 'xm'}
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False, index=True)
    hora = Column(Integer, nullable=False)
    demanda_mwh = Column(Float, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)
    
    __table_args__ = (
        Index('idx_demanda_fecha', 'fecha'),
        {'schema': 'xm'}
    )

class PreciosBolsa(Base):
    """Precios de bolsa (precio spot) por hora"""
    __tablename__ = "precios_bolsa"
    __table_args__ = {'schema': 'xm'}
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False, index=True)
    hora = Column(Integer, nullable=False)
    precio_cop_kwh = Column(Float, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)
    
    __table_args__ = (
        Index('idx_precios_fecha', 'fecha'),
        {'schema': 'xm'}
    )

# Crear todas las tablas
if __name__ == "__main__":
    from database import engine
    print("🗄️  Creando tablas en schema xm...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas exitosamente")
