import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ApiClientService, ReportStatusResponse, RdTranslatePipe } from '@rd/shared';
import { MyRequestsService } from '../../../core/services/my-requests.service';

@Component({
  selector: 'app-status',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, RdTranslatePipe],
  templateUrl: './status.component.html',
  styleUrls: ['./status.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusComponent implements OnInit, OnDestroy {
  private api = inject(ApiClientService);
  private route = inject(ActivatedRoute);
  private store = inject(MyRequestsService);

  reportIdInput = signal('');
  tokenInput = signal('');
  isLoading = signal(false);
  errorMessage = signal<string | null>(null);
  statusData = signal<ReportStatusResponse | null>(null);
  copied = signal<'' | 'id' | 'link'>('');
  /** Find form shows when nothing is saved, or when asked for (?find=1). */
  showFind = signal(false);
  invalidInput = signal(false);
  isNew = signal(false);
  private currentToken = '';
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    const q = this.route.snapshot.queryParams;
    const qId = q['id'] || q['report_id'];
    this.isNew.set(q['new'] === '1');
    if (qId) {
      this.reportIdInput.set(qId);
      this.tokenInput.set(q['token'] || '');
      this.fetchStatus(qId, q['token']);
    } else if (q['find']) {
      this.showFind.set(true);
    } else {
      const saved = this.store.latest();
      if (saved) {
        this.reportIdInput.set(saved.id);
        this.tokenInput.set(saved.token);
        this.fetchStatus(saved.id, saved.token || undefined);
      } else {
        this.showFind.set(true);
      }
    }
  }

  ngOnDestroy(): void {
    this.stopPoll();
  }

  /** Keep asking until a coordinator finishes the request, so the phone updates on its own. */
  stillWaiting(status: string | undefined): boolean {
    return status !== 'completed' && status !== 'resolved' && status !== 'closed';
  }

  fetchStatus(reportId: string, token?: string): void {
    const cleanId = reportId.trim();
    if (!cleanId) return;
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.currentToken = token?.trim() || '';
    this.api.getReportStatus(cleanId, token?.trim()).subscribe({
      next: (data) => {
        this.statusData.set(data);
        this.showFind.set(false);
        this.isLoading.set(false);
        this.store.add(data.report_id || cleanId, this.currentToken);
        if (this.stillWaiting(data.status)) this.startPoll();
        else this.stopPoll();
      },
      error: () => {
        this.statusData.set(null);
        this.errorMessage.set('not-found');
        this.showFind.set(true);
        this.isLoading.set(false);
      },
    });
  }

  private startPoll(): void {
    if (this.pollTimer) return;
    this.pollTimer = setInterval(() => {
      const data = this.statusData();
      const id = data?.report_id || this.reportIdInput().trim();
      if (!id || !this.stillWaiting(data?.status)) {
        this.stopPoll();
        return;
      }
      this.fetchStatus(id, this.currentToken);
    }, 4000);
  }

  private stopPoll(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /** Accepts a request ID, or a pasted status link that carries id and token. */
  onIdInput(value: string): void {
    this.reportIdInput.set(value);
    this.invalidInput.set(false);
    try {
      const url = new URL(value.trim());
      const id = url.searchParams.get('id') || url.searchParams.get('report_id');
      if (id) {
        this.reportIdInput.set(id);
        const tok = url.searchParams.get('token');
        if (tok) this.tokenInput.set(tok);
      }
    } catch { /* plain ID */ }
  }

  async pasteFromClipboard(): Promise<void> {
    try {
      const text = await navigator.clipboard.readText();
      if (text) this.onIdInput(text);
    } catch { /* permission denied: user can paste manually */ }
  }

  onTrackSubmit(): void {
    const id = this.reportIdInput().trim();
    if (!id) {
      this.invalidInput.set(true);
      return;
    }
    this.fetchStatus(id, this.tokenInput() || undefined);
  }

  statusLink(id: string): string {
    const tok = this.currentToken || this.tokenInput();
    return `${location.origin}/status?id=${encodeURIComponent(id)}${tok ? '&token=' + encodeURIComponent(tok) : ''}`;
  }

  private flash(kind: 'id' | 'link'): void {
    this.copied.set(kind);
    setTimeout(() => this.copied.set(''), 1600);
  }

  localTime(value: string | null | undefined): string {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  copyId(id: string): void {
    navigator.clipboard?.writeText(id).then(() => this.flash('id'));
  }

  copyLink(id: string): void {
    navigator.clipboard?.writeText(this.statusLink(id)).then(() => this.flash('link'));
  }

  share(id: string): void {
    const url = this.statusLink(id);
    if (navigator.share) {
      navigator.share({ title: 'Relief Desk', url }).catch(() => undefined);
    } else {
      this.copyLink(id);
    }
  }
}
