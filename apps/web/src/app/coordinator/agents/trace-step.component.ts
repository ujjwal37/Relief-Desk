import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';

export interface TraceStepView {
  agent: string;
  status: 'done' | 'running' | 'waiting' | 'fallback' | 'error';
  output: string | null;
  model: string | null;
  provider: string | null;
  latencyMs: number | null;
  input: string | null;
  tools: string[];
  asked: string | null;
  raw: string | null;
  note: string | null;
}

@Component({
  selector: 'app-trace-step',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './trace-step.component.html',
  styleUrl: './trace-step.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TraceStepComponent {
  private readonly lang = inject(LanguageService);
  readonly step = input.required<TraceStepView>();
  readonly nameKey = input.required<string>();
  readonly open = input(false);
  readonly toggled = output<void>();
  readonly retry = output<void>();

  timeText(): string | null {
    this.lang.currentLang();
    const ms = this.step().latencyMs;
    if (ms == null || Number.isNaN(ms)) return null;
    if (ms < 1000) return this.lang.translate('ux.ms').replace('{n}', String(Math.round(ms)));
    return this.lang.translate('ux.seconds').replace('{n}', (ms / 1000).toFixed(1));
  }

  modelText(): string {
    this.lang.currentLang();
    const step = this.step();
    if (step.model) {
      return step.provider === 'cache' ? `${step.model} · ${this.lang.translate('ux.badgeRecorded')}` : step.model;
    }
    if (step.provider === 'fallback') return this.lang.translate('ux.badgeOffline');
    if (step.provider === 'tool') return this.lang.translate('ux.noModel');
    return this.lang.translate('ux.notRecorded');
  }
}
