import { Injectable, inject, signal } from '@angular/core';
import { ApiClientService, ReportSubmitRequest, ReportSubmitResponse } from '@rd/shared';

export interface PendingOfflineReport {
  idempotency_key: string;
  payload: ReportSubmitRequest;
  timestamp: string;
}

const STORAGE_KEY = 'rd_offline_pending_reports';

@Injectable({
  providedIn: 'root',
})
export class OfflineSyncService {
  private apiClient = inject(ApiClientService);

  readonly isOnline = signal<boolean>(typeof navigator !== 'undefined' ? navigator.onLine : true);
  readonly pendingCount = signal<number>(0);
  readonly lastSyncedToken = signal<string | null>(null);

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.handleOnlineState(true));
      window.addEventListener('offline', () => this.handleOnlineState(false));
      this.refreshCount();
    }
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
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  saveReportOffline(payload: ReportSubmitRequest): PendingOfflineReport {
    const idempotencyKey = `idem_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const pendingItem: PendingOfflineReport = {
      idempotency_key: idempotencyKey,
      payload,
      timestamp: new Date().toISOString(),
    };

    const existing = this.getPendingReports();
    existing.push(pendingItem);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
    } catch {
      // Storage fallback
    }

    this.refreshCount();
    return pendingItem;
  }

  syncPendingReports(): void {
    const pending = this.getPendingReports();
    if (pending.length === 0) return;

    // Drain queue items one by one
    const remaining: PendingOfflineReport[] = [];

    pending.forEach((item) => {
      this.apiClient.submitReport(item.payload).subscribe({
        next: (resp: ReportSubmitResponse) => {
          this.lastSyncedToken.set(resp.status_token);
          this.removePendingReport(item.idempotency_key);
        },
        error: () => {
          // Keep in remaining queue if network still fails
        },
      });
    });
  }

  private removePendingReport(idempotencyKey: string): void {
    const list = this.getPendingReports().filter((i) => i.idempotency_key !== idempotencyKey);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    } catch {}
    this.refreshCount();
  }

  private refreshCount(): void {
    this.pendingCount.set(this.getPendingReports().length);
  }

  getPrefilledSmsLink(summaryOrText: string): string {
    const compactText = summaryOrText.trim().substring(0, 140) || 'EMERGENCY FLOOD RESCUE NEEDED';
    const body = encodeURIComponent(`RELIEF DESK: ${compactText}`);
    return `sms:112?body=${body}`;
  }
}
