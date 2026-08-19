from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date
from sqlalchemy.sql import func
from .database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)


class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    celular = Column(String(15), unique=True, nullable=True, index=True)
    nombre = Column(String(150), nullable=False)
    estado = Column(String(20), nullable=False, default="Instalada")
    fuente_ultima = Column(String(100), nullable=True)
    fecha_listado = Column(Date, nullable=True)  # Fecha real del listado (elegida al subir)
    fecha_primera_carga = Column(DateTime(timezone=True), server_default=func.now())
    fecha_ultima_carga = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    pendiente_revision = Column(Boolean, default=False, nullable=False)


class Carga(Base):
    __tablename__ = "cargas"

    id = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String(255), nullable=False)
    fuente = Column(String(100), nullable=False)
    fecha_listado = Column(Date, nullable=True)  # Fecha real del listado
    fecha_carga = Column(DateTime(timezone=True), server_default=func.now())
    total_registros = Column(Integer, default=0)
    nuevos = Column(Integer, default=0)
    actualizados = Column(Integer, default=0)
    pendientes = Column(Integer, default=0)
