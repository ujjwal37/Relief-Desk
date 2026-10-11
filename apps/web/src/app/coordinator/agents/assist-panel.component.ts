import { ChangeDetectionStrategy, Component, HostListener, inject, input, output, signal } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';

export interface AssistProposalView {
  match_id: string;
  request_id: string;
  title: string | null;
  team_name: string | null;
  team_kind: string | null;
  why: string | null;
  expires_at: string | null;
  expired: boolean;
  phase?: 'open' | 'approved' | 'failed';
}

export interface AssistShortageView {
  kind: string;
  have: number;
  need: number;
  explanation: string | null;
}

@Component({
  selector: 'app-assist-panel',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './assist-panel.component.html',
  styleUrl: './assist-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssistPanelComponent {
  private readonly lang = inject(LanguageService);
  readonly proposals = input.required<AssistProposalView[]>();
  readonly shortages = input<AssistShortageView[]>([]);
  readonly mobile = input(false);
  readonly closed = output<void>();
  readonly approve = output<AssistProposalView>();
  readonly reject = output<AssistProposalView>();
  readonly approveAll = output<void>();
  readonly refresh = output<void>();
  readonly now = signal(Date.now());
  private timer = setInterval(() => this.now.set(Date.now()), 1000);

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    this.closed.emit();
  }

  openCount(): number {
    return this.proposals().filter((row) => !row.expired && row.phase !== 'approved').length;
  }

  holdText(row: AssistProposalView): string {
    this.lang.currentLang();
    this.now();
    if (!row.expires_at) return this.lang.translate('ux.notRecorded');
    const end = Date.parse(row.expires_at);
    if (Number.isNaN(end)) return this.lang.translate('ux.notRecorded');
    const left = Math.max(0, Math.ceil((end - this.now()) / 1000));
    const text = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    return this.lang.translate('ux.holdLeft').replace('{time}', text);
  }

  whyOnly(row: AssistShortageView): string {
    this.lang.currentLang();
    return this.lang.translate('ux.whyOnly')
      .replace('{have}', String(row.have))
      .replace('{need}', String(row.need));
  }

  approvedText(row: AssistProposalView): string {
    this.lang.currentLang();
    return this.lang.translate('ux.approved').replace('{team}', row.team_name || this.lang.translate('ux.notRecorded'));
  }

  allLabel(): string {
    this.lang.currentLang();
    return this.lang.translate('ux.approveAll').replace('{n}', String(this.openCount()));
  }
}
