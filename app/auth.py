import os
import bcrypt
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from .models import Usuario

# Credenciales desde variables de entorno (con valores por defecto para desarrollo local)
DEFAULT_USER = os.getenv("APP_USER", "gestion")
DEFAULT_PASSWORD = os.getenv("APP_PASSWORD", "infomira2026")


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def create_default_user(db: Session):
    """Crea o actualiza el usuario compartido."""
    user = db.query(Usuario).filter(Usuario.usuario == DEFAULT_USER).first()
    if not user:
        user = Usuario(
            usuario=DEFAULT_USER,
            password_hash=hash_password(DEFAULT_PASSWORD)
        )
        db.add(user)
        db.commit()
        print(f"Usuario creado: {DEFAULT_USER}")
    else:
        # Si cambia la contraseña por variable de entorno, actualizarla
        if not verify_password(DEFAULT_PASSWORD, user.password_hash):
            user.password_hash = hash_password(DEFAULT_PASSWORD)
            db.commit()
            print(f"Contraseña actualizada para: {DEFAULT_USER}")


def authenticate_user(db: Session, username: str, password: str) -> bool:
    user = db.query(Usuario).filter(Usuario.usuario == username).first()
    if not user:
        return False
    return verify_password(password, user.password_hash)


def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user
