import { timeout } from 'rxjs';
import { Injectable, inject } from '@angular/core';
import { ApiClientService } from '@rd/shared';

export type MapMode = 'google' | 'svg';

@Injectable({ providedIn: 'root' })
export class MapProviderService {
  private api = inject(ApiClientService);
  private pending: Promise<MapMode> | null = null;
  /** Browser Maps key from GET /api/config/maps. Used for Routes API REST as well. */
  apiKey: string | null = null;
  /** Set when the browser key is rejected. Later maps stay on the SVG. */
  authFailed = false;

  /** One map style on every page: the Kuttanad schematic. Google tiles mixed two looks across screens. */
  static readonly ONE_STYLE: MapMode | null = 'svg';

  decide(): Promise<MapMode> {
    if (MapProviderService.ONE_STYLE) return Promise.resolve(MapProviderService.ONE_STYLE);
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return Promise.resolve('svg');
    }
    if (!this.pending) {
      this.pending = new Promise((resolve) => {
        this.api.getMapsConfig().pipe(timeout(6000)).subscribe({
          next: (cfg) => {
            if (!cfg?.enabled || !cfg.apiKey) {
              resolve('svg');
              return;
            }
            this.apiKey = cfg.apiKey;
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
      const timer = setTimeout(() => resolve(false), 10000);
      const finish = (ok: boolean) => { clearTimeout(timer); resolve(ok); };
      const existing = document.querySelector('script[data-rd-maps="1"]') as HTMLScriptElement | null;
      if (existing) {
        existing.addEventListener('load', () => finish(true), { once: true });
        existing.addEventListener('error', () => finish(false), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.async = true;
      script.dataset['rdMaps'] = '1';
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&libraries=routes`;
      script.onload = () => finish(!!(window as unknown as { google?: { maps?: unknown } }).google?.maps);
      script.onerror = () => finish(false);
      document.head.appendChild(script);
    });
  }
}
