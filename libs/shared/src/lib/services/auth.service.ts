import { Injectable, computed, signal } from '@angular/core';

export interface UserSession {
  email: string;
  role: 'coordinator' | 'admin' | 'public';
  token: string;
  displayName?: string;
}

export const DEMO_COORDINATOR_EMAIL = 'demo-coordinator@reliefdesk.internal';
/** Public sentinel. Stored sessions that still carry this token are dropped. Production refuses it. */
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
        const session = JSON.parse(stored) as UserSession;
        // The fixed demo token is refused in production. Sign in again for a real JWT.
        if (session?.token === DEMO_COORDINATOR_TOKEN) return null;
        return session;
      }
    } catch {
      // Fallback if localStorage parse fails
    }
    return null;
  }

  async login(email: string, password: string): Promise<{ success: boolean; error?: string }> {
    return this.signIn('/api/auth/login', { email: email.trim().toLowerCase(), password });
  }

  /** One-click judge login. The API signs a real JWT while its demo mode is on. */
  async loginDemo(): Promise<boolean> {
    const result = await this.signIn('/api/auth/demo-login', {});
    return result.success;
  }

  private async signIn(url: string, body: Record<string, string>): Promise<{ success: boolean; error?: string }> {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) return { success: false, error: 'Invalid email or password' };
      const data = (await res.json()) as { token: string; email: string; role: string; display_name?: string };
      if (!data?.token || data.role !== 'coordinator') return { success: false, error: 'Invalid email or password' };
      this.persistSession({
        email: data.email,
        role: 'coordinator',
        token: data.token,
        displayName: data.display_name || 'Kerala Emergency Coordinator',
      });
      return { success: true };
    } catch {
      return { success: false, error: 'Could not reach the server. Try again.' };
    }
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
