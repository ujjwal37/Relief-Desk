import { Injectable, inject } from '@angular/core';
import { ApiClientService } from '@rd/shared';
import { DEMO_MAP_ID } from './map-pins';

export type MapMode = 'google' | 'svg';

interface MapsConfig {
  enabled: boolean;
  apiKey: string | null;
  mapId?: string | null;
}

@Injectable({ providedIn: 'root' })
export class MapProviderService {
  private api = inject(ApiClientService);
  private pending: Promise<MapMode> | null = null;
  private last: MapsConfig | null = null;

  /** Cloud map id. DEMO_MAP_ID is the id that works with the Google demo key. */
  mapId(): string {
    const id = (this.last?.mapId || '').trim();
    return id || DEMO_MAP_ID;
  }

  decide(): Promise<MapMode> {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return Promise.resolve('svg');
    }
    if (!this.pending) {
      this.pending = new Promise((resolve) => {
        this.api.getMapsConfig().subscribe({
          next: (cfg) => {
            this.last = cfg;
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
    const w = window as unknown as { google?: { maps?: { marker?: { AdvancedMarkerElement?: unknown } } } };
    if (w.google?.maps?.marker?.AdvancedMarkerElement) {
      return Promise.resolve(true);
    }
    return new Promise((resolve) => {
      const existing = document.querySelector('script[data-rd-maps="1"]') as HTMLScriptElement | null;
      if (existing) {
        existing.addEventListener('load', () => resolve(this.markerReady()));
        existing.addEventListener('error', () => resolve(false));
        return;
      }
      const script = document.createElement('script');
      script.async = true;
      script.dataset['rdMaps'] = '1';
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&libraries=marker`;
      script.onload = () => resolve(this.markerReady());
      script.onerror = () => resolve(false);
      document.head.appendChild(script);
    });
  }

  private markerReady(): boolean {
    const w = window as unknown as { google?: { maps?: { marker?: { AdvancedMarkerElement?: unknown } } } };
    return !!w.google?.maps?.marker?.AdvancedMarkerElement;
  }
}
