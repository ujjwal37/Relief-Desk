import { ChangeDetectionStrategy, Component, HostListener, inject, input, output, signal } from '@angular/core';
import { ApiClientService, LanguageService, RdTranslatePipe } from '@rd/shared';

export interface MergeReportView {
  id: string;
  text: string | null;
  at: string | null;
  channel: string | null;
  lang: string | null;
}

@Component({
  selector: 'app-merged-chip',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './merged-chip.component.html',
  styleUrl: './merged-chip.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MergedChipComponent {
  private readonly api = inject(ApiClientService);
  private readonly lang = inject(LanguageService);
  readonly count = input.required<number>();
  readonly requestId = input.required<string>();
  readonly mobile = input(false);
  readonly undo = output<void>();
  readonly open = signal(false);
  readonly anchor = signal({ top: 0, left: 0 });
  readonly why = signal<string | null>(null);
  readonly reports = signal<MergeReportView[]>([]);

  label(): string {
    this.lang.currentLang();
    const n = this.count();
    if (n === 1) return this.lang.translate('ux.reportsOne');
    return this.lang.translate('ux.reportsMany').replace('{n}', String(n));
  }

  shown(): MergeReportView[] {
    return this.reports().slice(0, 5);
  }

  extra(): number {
    return Math.max(0, this.reports().length - 5);
  }

  moreLabel(): string {
    return this.lang.translate('ux.more').replace('{n}', String(this.extra()));
  }

  toggle(event: Event): void {
    event.stopPropagation();
    const el = event.currentTarget as HTMLElement | null;
    if (el) {
      const rect = el.getBoundingClientRect();
      const width = Math.min(420, window.innerWidth - 16);
      const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
      const top = rect.bottom + 8 + 280 > window.innerHeight ? Math.max(8, rect.top - 280) : rect.bottom + 8;
      this.anchor.set({ top, left });
    }
    if (this.open()) {
      this.open.set(false);
      return;
    }
    this.open.set(true);
    this.api.getMerge(this.requestId()).subscribe({
      next: (body) => {
        this.why.set(body?.why ?? null);
        this.reports.set(Array.isArray(body?.reports) ? body.reports : []);
      },
      error: () => {
        this.why.set(null);
        this.reports.set([]);
      },
    });
  }

  close(event?: Event): void {
    event?.stopPropagation();
    this.open.set(false);
  }

  onUndo(event: Event): void {
    event.stopPropagation();
    this.open.set(false);
    this.undo.emit();
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.open()) this.open.set(false);
  }

  clock(value: string | null): string | null {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
}
