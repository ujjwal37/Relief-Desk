#!/usr/bin/env python3
"""
scripts/seed.py — Seeds synthetic demo coordinator credentials and initial data for Relief Desk.
Creates demo-coordinator@reliefdesk.internal with role 'coordinator'.
Supports Firebase Auth Emulator if running, and writes data/synthetic/coordinator_credentials.json.
"""

import json
import os
import sys
from pathlib import Path

# Credentials for demo-only local environment
DEMO_COORDINATOR = {
    "email": "demo-coordinator@reliefdesk.internal",
    "role": "coordinator",
    "displayName": "Kerala Emergency Coordinator",
    "uid": "demo-coord-01",
    "token": "demo-coordinator-token",
}


def seed_coordinator_account():
    print("=" * 60)
    print("Relief Desk — Synthetic Demo Coordinator Seeding")
    print("=" * 60)

    password = (os.getenv("COORDINATOR_PASSWORD") or "").strip()
    if not password:
        print("COORDINATOR_PASSWORD environment variable is not set.")
        print("Skipping coordinator credential creation (no hardcoded fallback).")
        print("=" * 60)
        return

    # 1. Check / update Firebase Auth emulator if host is present
    emulator_host = os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
    if emulator_host:
        print(f"Connecting to Firebase Auth Emulator at {emulator_host}...")
        try:
            import firebase_admin
            from firebase_admin import auth as fb_auth

            if not firebase_admin._apps:
                firebase_admin.initialize_app()

            try:
                user = fb_auth.get_user_by_email(DEMO_COORDINATOR["email"])
                print(f"Existing coordinator user found (UID: {user.uid}). Updating claims...")
            except Exception:
                user = fb_auth.create_user(
                    email=DEMO_COORDINATOR["email"],
                    password=password,
                    display_name=DEMO_COORDINATOR["displayName"],
                    uid=DEMO_COORDINATOR["uid"],
                )
                print(f"Created new Firebase user (UID: {user.uid}).")

            fb_auth.set_custom_user_claims(user.uid, {"role": "coordinator"})
            print("Successfully assigned custom role claim: {'role': 'coordinator'}")
        except Exception as err:
            print(f"Notice: Firebase Auth emulator seeding fallback: {err}")
    else:
        print("Note: Running with local synthetic auth mode (FIREBASE_AUTH_EMULATOR_HOST not set).")

    # 2. Persist synthetic credentials file
    out_dir = Path(__file__).resolve().parent.parent / "data" / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    creds_path = out_dir / "coordinator_credentials.json"

    with open(creds_path, "w", encoding="utf-8") as f:
        json.dump(DEMO_COORDINATOR, f, indent=2)

    print(f"\nSynthetic coordinator credentials written to:\n  {creds_path}")
    print("\nDemo Coordinator Credentials:")
    print(f"  Email:    {DEMO_COORDINATOR['email']}")
    print(f"  Role:     {DEMO_COORDINATOR['role']}")
    print(f"  Token:    {DEMO_COORDINATOR['token']}")
    print("=" * 60)


if __name__ == "__main__":
    seed_coordinator_account()
