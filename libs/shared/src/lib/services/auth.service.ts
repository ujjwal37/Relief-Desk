import { Injectable, computed, signal } from '@angular/core';

export interface UserSession {
  email: string;
  role: 'coordinator' | 'admin' | 'public';
  token: string;
  displayName?: string;
}

export const DEMO_COORDINATOR_EMAIL = 'demo-coordinator@reliefdesk.internal';
export const DEMO_COORDINATOR_PASSWORD = 'RiverbendRelief2026!';
export const DEMO_COORDINATOR_TOKEN = 'demo-coordinator-token';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly STORAGE_KEY = 'rd_auth_session';

  readonly currentUser = signal<UserSession | null>(this.getInitialSession());
  readonly isAuthenticated = computed(() => this.currentUser() !== null);
  readonly isCoordinator = computed(() => this.currentUser()?.role === 'coordinator');

  private getInitialSession(): UserSession | null {
    if (typeof window === 'undefined' || !window.localStorage) {
      return null;
    }
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored) as UserSession;
      }
    } catch {
      // Fallback if localStorage parse fails
    }
    return null;
  }

  async login(email: string, password: string): Promise<{ success: boolean; error?: string }> {
    const trimmedEmail = email.trim().toLowerCase();

    // Verify against synthetic demo coordinator account or valid coordinator credentials
    if (
      trimmedEmail === DEMO_COORDINATOR_EMAIL.toLowerCase() &&
      password === DEMO_COORDINATOR_PASSWORD
    ) {
      const session: UserSession = {
        email: DEMO_COORDINATOR_EMAIL,
        role: 'coordinator',
        token: DEMO_COORDINATOR_TOKEN,
        displayName: 'Riverbend Emergency Coordinator',
      };
      this.persistSession(session);
      return { success: true };
    }

    return { success: false, error: 'Invalid email or password' };
  }

  async loginDemo(): Promise<boolean> {
    const result = await this.login(DEMO_COORDINATOR_EMAIL, DEMO_COORDINATOR_PASSWORD);
    return result.success;
  }

  logout(): void {
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        localStorage.removeItem(this.STORAGE_KEY);
      } catch {
        // ignore storage error
      }
    }
    this.currentUser.set(null);
  }

  getToken(): string | null {
    return this.currentUser()?.token || null;
  }

  private persistSession(session: UserSession): void {
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(session));
      } catch {
        // ignore storage error
      }
    }
    this.currentUser.set(session);
  }
}
