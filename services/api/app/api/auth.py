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
DEMO_COORDINATOR_PASSWORD = "KeralaRelief2026!"
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


def create_coordinator_token(email: str = DEMO_COORDINATOR_EMAIL) -> str:
    payload = {
        "sub": email,
        "email": email,
        "role": "coordinator",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_coordinator_token(token: str) -> CoordinatorUser:
    # 1. Accept synthetic demo coordinator token
    if token == DEMO_COORDINATOR_TOKEN:
        return CoordinatorUser(
            uid="demo-coord-01",
            email=DEMO_COORDINATOR_EMAIL,
            role="coordinator",
            display_name="Kerala Emergency Coordinator",
        )

    # 2. Check signed JWT
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
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
            if role == "coordinator" or email.lower() == DEMO_COORDINATOR_EMAIL.lower():
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


@router.post("/auth/login", response_model=LoginResponse)
def login(creds: LoginRequest):
    email = creds.email.strip().lower()
    if (
        email == DEMO_COORDINATOR_EMAIL.lower()
        and creds.password == DEMO_COORDINATOR_PASSWORD
    ):
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
