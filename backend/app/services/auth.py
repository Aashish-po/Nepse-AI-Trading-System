from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def register_user(db: Session, email: str, password: str, role: str = "researcher") -> User:
    user = User(email=email.lower(), hashed_password=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> str | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return create_access_token(subject=user.email)
