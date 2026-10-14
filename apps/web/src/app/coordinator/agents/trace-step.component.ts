import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';

export interface TraceStepView {
  agent: string;
  status: 'done' | 'running' | 'waiting' | 'fallback' | 'error';
  output: string | null;
  model: string | null;
  provider: string | null;
  vendor?: string | null;
  latencyMs: number | null;
  input: string | null;
  tools: string[];
  asked: string | null;
  raw: string | null;
  note: string | null;
  sentence?: string;
  linkId?: string | null;
  badge?: 'gemini' | 'rules' | 'test';
  hasDetails?: boolean;
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
  readonly rawAll = signal(false);
  readonly promptAll = signal(false);
  readonly copied = signal('');

  timeText(): string | null {
    this.lang.currentLang();
    const ms = this.step().latencyMs;
    if (ms == null || Number.isNaN(ms) || ms <= 0) return null;
    if (ms < 1000) return this.lang.translate('ux.ms').replace('{n}', String(Math.round(ms)));
    return this.lang.translate('ux.seconds').replace('{n}', (ms / 1000).toFixed(1));
  }

  badgeWord(): string {
    this.lang.currentLang();
    const step = this.step();
    if (step.badge === 'test') return this.lang.translate('flow.badgeTest');
    if (step.badge === 'gemini') return this.lang.translate('flow.badgeGemini');
    if (step.badge === 'rules') return this.lang.translate('flow.badgeRules');
    const test = step.provider === 'openai_compat' || step.provider === 'antigravity-local';
    if (test) return this.lang.translate('flow.badgeTest');
    if (step.provider === 'gemini' && step.status === 'done') return this.lang.translate('flow.badgeGemini');
    return this.lang.translate('flow.badgeRules');
  }

  sentence(): string {
    return this.step().sentence || '';
  }
  beforeLink(): string {
    const id = this.step().linkId || '';
    const text = this.sentence();
    const at = text.indexOf(id);
    return at >= 0 ? text.slice(0, at) : text;
  }
  afterLink(): string {
    const id = this.step().linkId || '';
    const text = this.sentence();
    const at = text.indexOf(id);
    return at >= 0 ? text.slice(at + id.length) : '';
  }

  showDetails(): boolean {
    return !!this.step().hasDetails;
  }

  pretty(value: string | null): string {
    if (!value) return '';
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }

  clipped(value: string | null, lines: number, all: boolean): string {
    const text = this.pretty(value);
    if (all) return text;
    const parts = text.split('\n');
    return parts.length > lines ? parts.slice(0, lines).join('\n') : text;
  }

  needsClip(value: string | null, lines: number): boolean {
    return this.pretty(value).split('\n').length > lines;
  }

  copy(kind: string, value: string | null): void {
    const text = this.pretty(value);
    if (!text || typeof navigator === 'undefined' || !navigator.clipboard) return;
    void navigator.clipboard.writeText(text).then(() => {
      this.copied.set(kind);
      setTimeout(() => this.copied.set(''), 1200);
    });
  }
}
