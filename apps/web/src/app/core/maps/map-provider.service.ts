import { Injectable, inject } from '@angular/core';
import { ApiClientService } from '@rd/shared';

export type MapMode = 'google' | 'svg';

@Injectable({ providedIn: 'root' })
export class MapProviderService {
  private api = inject(ApiClientService);
  private pending: Promise<MapMode> | null = null;
  /** Set when the browser key is rejected. Later maps stay on the SVG. */
  authFailed = false;

  decide(): Promise<MapMode> {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return Promise.resolve('svg');
    }
    if (!this.pending) {
      this.pending = new Promise((resolve) => {
        this.api.getMapsConfig().subscribe({
          next: (cfg) => {
            if (!cfg?.enabled || !cfg.apiKey) {
              resolve('svg');
              return;
            }
            this.loadScript(cfg.apiKey).then((ok) => resolve(ok ? 'google' : 'svg'));
          },
          error: () => resolve('svg'),
        });
      });
    }
    return this.pending;
  }

  loadScript(apiKey: string): Promise<boolean> {
    const w = window as unknown as { google?: { maps?: unknown } };
    if (w.google?.maps) {
      return Promise.resolve(true);
    }
    return new Promise((resolve) => {
      const existing = document.querySelector('script[data-rd-maps="1"]') as HTMLScriptElement | null;
      if (existing) {
        existing.addEventListener('load', () => resolve(true));
        existing.addEventListener('error', () => resolve(false));
        return;
      }
      const script = document.createElement('script');
      script.async = true;
      script.dataset['rdMaps'] = '1';
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly`;
      script.onload = () => resolve(!!(window as unknown as { google?: { maps?: unknown } }).google?.maps);
      script.onerror = () => resolve(false);
      document.head.appendChild(script);
    });
  }
}
