import { Injectable, inject, signal } from '@angular/core';
import { ApiClientService, ReportSubmitRequest, ReportSubmitResponse } from '@rd/shared';
import { announceReport } from '../live-report';
import { MyRequestsService } from './my-requests.service';

export interface PendingOfflineReport {
  client_id: string;
  idempotency_key: string;
  payload: ReportSubmitRequest;
  timestamp: string;
  attempts: number;
  last_attempt_at?: string;
}

export interface SyncedReport {
  client_id: string;
  response: ReportSubmitResponse;
}

const STORAGE_KEY = 'rd_offline_pending_reports';

@Injectable({
  providedIn: 'root',
})
export class OfflineSyncService {
  private apiClient = inject(ApiClientService);
  private myRequests = inject(MyRequestsService);

  readonly isOnline = signal<boolean>(typeof navigator !== 'undefined' ? navigator.onLine : true);
  readonly pendingCount = signal<number>(0);
  readonly lastSyncedToken = signal<string | null>(null);
  readonly lastSynced = signal<SyncedReport | null>(null);

  private flushing = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.handleOnlineState(true));
      window.addEventListener('offline', () => this.handleOnlineState(false));
      this.refreshCount();
      if (this.readOnline()) {
        this.syncPendingReports();
      } else {
        this.schedule();
      }
    }
  }

  /** Read the browser flag at call time. Playwright offline mode updates this before the event. */
  readOnline(): boolean {
    const online = typeof navigator === 'undefined' ? true : navigator.onLine;
    if (online !== this.isOnline()) {
      this.isOnline.set(online);
    }
    return online;
  }

  private handleOnlineState(online: boolean): void {
    this.isOnline.set(online);
    if (online) {
      this.syncPendingReports();
    }
  }

  getPendingReports(): PendingOfflineReport[] {
    if (typeof localStorage === 'undefined') return [];
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      const parsed = data ? JSON.parse(data) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  saveReportOffline(payload: ReportSubmitRequest): PendingOfflineReport {
    const existing = this.getPendingReports();
    const reused = payload.idempotency_key
      ? existing.find((item) => item.idempotency_key === payload.idempotency_key)
      : undefined;
    if (reused) {
      return reused;
    }
    const idempotencyKey = payload.idempotency_key || `idem_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const pendingItem: PendingOfflineReport = {
      client_id: `cli_${idempotencyKey}`,
      idempotency_key: idempotencyKey,
      payload: { ...payload, idempotency_key: idempotencyKey },
      timestamp: new Date().toISOString(),
      attempts: 0,
    };
    existing.push(pendingItem);
    this.write(existing);
    this.schedule();
    return pendingItem;
  }

  syncPendingReports(): void {
    if (this.flushing || !this.readOnline()) {
      this.schedule();
      return;
    }
    const pending = this.getPendingReports();
    if (pending.length === 0) return;
    this.flushing = true;
    this.flushNext(pending[0]);
  }

  private flushNext(item: PendingOfflineReport): void {
    const attempts = item.attempts + 1;
    this.patch(item.idempotency_key, { attempts, last_attempt_at: new Date().toISOString() });
    const body: ReportSubmitRequest = { ...item.payload, idempotency_key: item.idempotency_key };
    this.apiClient.submitReport(body).subscribe({
      next: (resp: ReportSubmitResponse) => {
        this.lastSyncedToken.set(resp.status_token);
        this.lastSynced.set({ client_id: item.client_id, response: resp });
        this.myRequests.add(resp.report_id, resp.status_token);
        announceReport(resp.report_id, resp.request_id);
        this.removePendingReport(item.idempotency_key);
        this.flushing = false;
        if (this.getPendingReports().length) {
          this.syncPendingReports();
        }
      },
      error: () => {
        this.flushing = false;
        this.schedule();
      },
    });
  }

  private patch(idempotencyKey: string, extra: Partial<PendingOfflineReport>): void {
    const list = this.getPendingReports().map((item) =>
      item.idempotency_key === idempotencyKey ? { ...item, ...extra } : item,
    );
    this.write(list);
  }

  private removePendingReport(idempotencyKey: string): void {
    const list = this.getPendingReports().filter((i) => i.idempotency_key !== idempotencyKey);
    this.write(list);
  }

  private write(list: PendingOfflineReport[]): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    } catch {
      // Storage full: the in-memory signal still reflects the last successful write.
    }
    this.refreshCount();
  }

  private refreshCount(): void {
    this.pendingCount.set(this.getPendingReports().length);
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    const pending = this.getPendingReports();
    if (!pending.length) return;
    const attempts = Math.max(...pending.map((item) => item.attempts));
    const delay = Math.min(30000, 4000 * Math.pow(2, Math.min(attempts, 3)));
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.readOnline()) this.syncPendingReports();
      else this.schedule();
    }, delay);
  }

  getPrefilledSmsLink(summaryOrText: string): string {
    const compactText = summaryOrText.trim().substring(0, 140) || 'EMERGENCY FLOOD RESCUE NEEDED';
    const body = encodeURIComponent(`RELIEF DESK: ${compactText}`);
    return `sms:112?body=${body}`;
  }
}
