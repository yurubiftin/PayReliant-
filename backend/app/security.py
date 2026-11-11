"""Authentication and authorization (proposal 3.1.3 "Security" and 3.5).

Three kinds of caller:

  1. ADMIN user      - logs in with username + password, sees and manages everything
  2. MERCHANT user   - logs in, sees ONLY their own merchant's data
  3. USSD gateway    - not a person: a system that submits payments using an API key
                       (in this project, the USSD simulator plays this role)

How a login works:
  - POST /auth/login with username + password
  - the password is checked against the stored Argon2 HASH (the password itself is never stored)
  - if correct, the API returns a signed token (JWT) that expires after TOKEN_MINUTES
  - the dashboard sends that token with every request:  Authorization: Bearer <token>
  - the token is signed with SECRET_KEY, so it cannot be forged or edited
"""

from datetime import datetime, timedelta, timezone
from secrets import compare_digest
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import User

password_hasher = PasswordHash.recommended()  # Argon2

# These two objects also make the "Authorize" button appear on the /docs page.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

ALGORITHM = "HS256"


# --- Passwords -------------------------------------------------------------------

def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter_by(username=username).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None  # same answer for "no such user" and "wrong password": don't reveal which
    return user


# --- Tokens ----------------------------------------------------------------------

def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=config.TOKEN_MINUTES)
    payload = {"sub": str(user.user_id), "role": user.role, "exp": expires}
    return jwt.encode(payload, config.SECRET_KEY, algorithm=ALGORITHM)


def _user_from_token(db: Session, token: str) -> User | None:
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])  # also checks expiry
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(payload["sub"]))
    return user if user and user.is_active else None


# --- Dependencies: add one of these to an endpoint to protect it -------------------

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not logged in, or your session has expired. Please log in.",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)], db: Session = Depends(get_db)
) -> User:
    """Any logged-in user (admin or merchant)."""
    user = _user_from_token(db, token) if token else None
    if user is None:
        raise UNAUTHORIZED
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    """Only admins."""
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")
    return user


def is_gateway(api_key: str | None) -> bool:
    # compare_digest takes the same time whether the key is right or wrong (prevents timing attacks)
    return api_key is not None and compare_digest(api_key, config.GATEWAY_API_KEY)


def gateway(api_key: Annotated[str | None, Depends(api_key_header)]) -> None:
    """Only the USSD gateway (correct X-API-Key header)."""
    if not is_gateway(api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid API key.")


def gateway_or_admin(
    api_key: Annotated[str | None, Depends(api_key_header)],
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> None:
    """The USSD gateway, or a logged-in admin."""
    if is_gateway(api_key):
        return
    user = _user_from_token(db, token) if token else None
    if user is None:
        raise UNAUTHORIZED
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")


def gateway_or_user(
    api_key: Annotated[str | None, Depends(api_key_header)],
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User | None:
    """Any logged-in user, or the USSD gateway. Returns the user (None for the gateway).

    A valid login takes priority, so an admin who also sends the API key is still treated as the admin.
    """
    user = _user_from_token(db, token) if token else None
    if user is not None:
        return user
    if is_gateway(api_key):
        return None
    raise UNAUTHORIZED
