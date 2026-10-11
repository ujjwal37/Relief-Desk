import { Injectable, signal } from '@angular/core';

export type ThemeMode = 'system' | 'light' | 'dark';
const KEY = 'rd_theme_mode';

/** One theme service for public and coordinator apps. Default: follow system, persisted. */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly mode = signal<ThemeMode>('system');
  readonly resolved = signal<'light' | 'dark'>('light');
  private mq: MediaQueryList | null = null;

  constructor() {
    if (typeof window === 'undefined') return;
    try {
      const saved = localStorage.getItem(KEY) as ThemeMode | null;
      if (saved === 'light' || saved === 'dark' || saved === 'system') this.mode.set(saved);
    } catch { /* ignore */ }
    this.mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    this.mq?.addEventListener?.('change', () => this.apply());
    this.apply();
  }

  setMode(mode: ThemeMode): void {
    this.mode.set(mode);
    try { localStorage.setItem(KEY, mode); } catch { /* ignore */ }
    this.apply();
  }

  private apply(): void {
    const m = this.mode();
    const dark = m === 'dark' || (m === 'system' && !!this.mq?.matches);
    this.resolved.set(dark ? 'dark' : 'light');
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
      document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
    }
  }
}
