import { Injectable, signal } from '@angular/core';

export interface SavedRequest { id: string; token: string; at: number; }
const KEY = 'rd_my_requests';

/** Requests saved on this device (ID + status token). Also keeps the legacy single-request keys in sync. */
@Injectable({ providedIn: 'root' })
export class MyRequestsService {
  readonly list = signal<SavedRequest[]>(this.load());

  private load(): SavedRequest[] {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) || '[]');
      if (Array.isArray(raw) && raw.length) return raw as SavedRequest[];
      const id = localStorage.getItem('rd_last_report_id');
      if (id) return [{ id, token: localStorage.getItem('rd_last_status_token') || '', at: Date.now() }];
    } catch { /* ignore */ }
    return [];
  }

  latest(): SavedRequest | undefined { return this.list()[0]; }

  add(id: string, token: string): void {
    const next = [{ id, token, at: Date.now() }, ...this.list().filter((r) => r.id !== id)].slice(0, 5);
    this.list.set(next);
    this.persist(next);
  }

  remove(id: string): void {
    const next = this.list().filter((r) => r.id !== id);
    this.list.set(next);
    this.persist(next);
  }

  private persist(next: SavedRequest[]): void {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
      if (next[0]) {
        localStorage.setItem('rd_last_report_id', next[0].id);
        localStorage.setItem('rd_last_status_token', next[0].token);
      } else {
        localStorage.removeItem('rd_last_report_id');
        localStorage.removeItem('rd_last_status_token');
      }
    } catch { /* ignore */ }
  }
}
