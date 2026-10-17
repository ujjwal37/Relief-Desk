import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
import jwt

from app.config import settings

logger = logging.getLogger("relief_desk.auth")

router = APIRouter(prefix="/api", tags=["auth"])

DEMO_COORDINATOR_EMAIL = "demo-coordinator@reliefdesk.internal"
DEMO_COORDINATOR_TOKEN = "demo-coordinator-token"


class CoordinatorUser(BaseModel):
    uid: str
    email: str
    role: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    role: str
    display_name: str


def _signing_key() -> str:
    secret = (settings.JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET is not configured",
        )
    return secret


def create_coordinator_token(email: str = DEMO_COORDINATOR_EMAIL) -> str:
    payload = {
        "sub": email,
        "email": email,
        "role": "coordinator",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=12),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, _signing_key(), algorithm="HS256")


def is_production() -> bool:
    return (settings.ENV or "").strip().lower() in ("production", "prod")


def verify_coordinator_token(token: str) -> CoordinatorUser:
    # 1. The fixed demo token is public in the repo, so it only works outside production.
    if token == DEMO_COORDINATOR_TOKEN and not is_production():
        return CoordinatorUser(
            uid="demo-coord-01",
            email=DEMO_COORDINATOR_EMAIL,
            role="coordinator",
            display_name="Kerala Emergency Coordinator",
        )

    # 2. Check signed JWT. An empty key must not verify anything.
    secret = (settings.JWT_SECRET or "").strip()
    if secret:
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            if payload.get("role") != "coordinator":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: User lacks coordinator role claim",
                )
            return CoordinatorUser(
                uid=payload.get("sub", "coordinator-user"),
                email=payload.get("email", DEMO_COORDINATOR_EMAIL),
                role=payload.get("role", "coordinator"),
                display_name="Verified Coordinator",
            )
        except jwt.PyJWTError:
            pass

    # 3. Check Firebase Admin if initialized
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth

        if firebase_admin._apps:
            decoded = fb_auth.verify_id_token(token)
            role = decoded.get("role") or decoded.get("claims", {}).get("role")
            email = decoded.get("email", "")
            # Only the custom role claim grants coordinator access, never a matching email.
            if role == "coordinator":
                return CoordinatorUser(
                    uid=decoded.get("uid", "fb-coord"),
                    email=email,
                    role="coordinator",
                    display_name=decoded.get("name", "Firebase Coordinator"),
                )
    except Exception as e:
        logger.debug("Firebase auth verification fallback: %s", e)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Invalid or expired coordinator token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_coordinator(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> CoordinatorUser:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Authorization header must use Bearer scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    return verify_coordinator_token(token)


def _password_ok(password: str) -> bool:
    import hmac

    configured = (settings.COORDINATOR_PASSWORD or "").strip()
    if not configured:
        return False
    return hmac.compare_digest(password, configured)


def _demo_session() -> "LoginResponse":
    return LoginResponse(
        token=create_coordinator_token(DEMO_COORDINATOR_EMAIL),
        email=DEMO_COORDINATOR_EMAIL,
        role="coordinator",
        display_name="Kerala Emergency Coordinator",
    )


@router.post("/auth/demo-login", response_model=LoginResponse)
def demo_login():
    """One-click judge login: a real signed JWT for the demo coordinator, only while DEMO_MODE is on."""
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo login is off")
    return _demo_session()


@router.post("/auth/login", response_model=LoginResponse)
def login(creds: LoginRequest):
    email = creds.email.strip().lower()
    if email == DEMO_COORDINATOR_EMAIL.lower() and _password_ok(creds.password):
        token = create_coordinator_token(DEMO_COORDINATOR_EMAIL)
        return LoginResponse(
            token=token,
            email=DEMO_COORDINATOR_EMAIL,
            role="coordinator",
            display_name="Kerala Emergency Coordinator",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )


@router.get("/coordinator/verify")
def verify_session(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    return {
        "authenticated": True,
        "coordinator": coordinator.model_dump(),
    }
