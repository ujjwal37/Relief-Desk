import { Injectable, inject, signal } from '@angular/core';
import { ApiClientService, LanguageService, RecentReport } from '@rd/shared';
import { LIVE_CHANNEL, LIVE_REPORT } from '../core/live-report';
import { arrivalPlace, arrivalType, visibleReports } from './just-reported';

/** Shared list so Cases and Overview show the same arrivals, and a toast only once. */
@Injectable({ providedIn: 'root' })
export class JustReportedService {
  private readonly api = inject(ApiClientService);
  private readonly lang = inject(LanguageService);
  readonly items = signal<RecentReport[]>([]);
  readonly toast = signal<string | null>(null);
  private seen = new Set<string>();
  private primed = false;
  private users = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private toastTimer: ReturnType<typeof setTimeout> | null = null;
  private channel?: { close: () => void };

  retain(): void {
    this.users += 1;
    if (this.users !== 1) return;
    this.refresh();
    this.timer = setInterval(() => this.refresh(), 4000);
    try {
      const channel = new BroadcastChannel(LIVE_CHANNEL);
      channel.onmessage = (event) => {
        const data = event.data as { type?: string } | null;
        if (data?.type === LIVE_REPORT) this.refresh();
      };
      this.channel = channel;
    } catch {
      // The 4s poll still picks the report up.
    }
  }

  release(): void {
    this.users = Math.max(0, this.users - 1);
    if (this.users > 0) return;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.channel?.close();
    this.channel = undefined;
  }

  refresh(): void {
    this.api.getRecentReports().subscribe({
      next: (rows) => this.apply(rows),
      error: () => undefined,
    });
  }

  /** First load remembers what is already there. Later arrivals raise the toast. */
  apply(rows: RecentReport[]): void {
    const visible = visibleReports(rows);
    if (!this.primed) {
      for (const row of visible) this.seen.add(row.id);
      this.primed = true;
    } else {
      const fresh = visible.filter((row) => !this.seen.has(row.id));
      for (const row of visible) this.seen.add(row.id);
      if (fresh[0]) this.showToast(fresh[0]);
    }
    this.items.set(visible);
  }

  private showToast(row: RecentReport): void {
    const lang = this.lang.currentLang();
    const text = this.lang.translate('coord.justArrived')
      .replace('{place}', arrivalPlace(row, lang))
      .replace('{type}', arrivalType(row, lang, (key) => this.lang.translate(key)));
    this.toast.set(text);
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toast.set(null), 4000);
  }
}
