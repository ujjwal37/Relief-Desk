import { ChangeDetectionStrategy, Component, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiClientService, LanguageService, RdTranslatePipe } from '@rd/shared';
import { TraceStepComponent, TraceStepView } from './trace-step.component';

export interface DeskCase {
  id: string;
  type: string;
  ward_id: string | null;
  ward_name: string | null;
  place_text: string | null;
  people_count: number | null;
  status: string;
  urgency_score: number;
  vulnerable: string[];
  summary: string;
}

export interface DeskAnswer {
  question: string;
  reason: string;
  total: number;
  cases: DeskCase[];
  ai: { provider: string; model: string | null; fallback_reason?: string | null };
  trace: Array<Record<string, any>>;
}

const STEP_KEYS = ['ux.deskStepUnderstand', 'ux.deskStepSearch'];

/** Coordinator question in, matching cases out. The endpoint only reads the case store. */
@Component({
  selector: 'app-ask-desk',
  standalone: true,
  imports: [FormsModule, RdTranslatePipe, TraceStepComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="ask-desk card" aria-labelledby="ask-desk-h">
      <h2 id="ask-desk-h">{{ 'ux.deskTitle' | rdTranslate }}</h2>
      <p class="hint">{{ 'ux.deskHint' | rdTranslate }}</p>
      <form class="row" (ngSubmit)="ask()">
        <input
          name="q"
          [(ngModel)]="question"
          [placeholder]="'ux.deskPlaceholder' | rdTranslate"
          [attr.aria-label]="'ux.deskTitle' | rdTranslate"
          maxlength="300"
        />
        <button type="submit" class="btn" [disabled]="busy() || !question.trim()">
          {{ (busy() ? 'ux.deskAsking' : 'ux.deskAsk') | rdTranslate }}
        </button>
      </form>
      @if (error()) {
        <p class="err" role="alert">{{ 'ux.deskError' | rdTranslate }}</p>
      }
      @if (answer(); as a) {
        <div class="answer" aria-live="polite">
          <p class="reason">
            <strong>{{ matchesText(a.total) }}</strong> · {{ a.reason }}
            <span class="via">{{ viaText(a) }}</span>
          </p>
          @if (!a.cases.length) {
            <p class="none">{{ 'ux.deskNone' | rdTranslate }}</p>
          }
          <ul class="cards">
            @for (c of a.cases; track c.id) {
              <li>
                <button type="button" class="case" (click)="picked.emit(c.id)">
                  <span class="id">{{ c.id }}</span>
                  <span class="type">{{ ('incidentType.' + c.type) | rdTranslate }}</span>
                  @if (c.ward_name) { <span class="ward">{{ c.ward_name }}</span> }
                  @if (c.people_count) { <span class="ppl">{{ peopleText(c.people_count) }}</span> }
                  <span class="sum">{{ c.summary }}</span>
                </button>
              </li>
            }
          </ul>
          <button type="button" class="link" (click)="showTrace.set(!showTrace())" [attr.aria-expanded]="showTrace()">
            {{ 'ux.deskShowTrace' | rdTranslate }}
          </button>
          @if (showTrace()) {
            <div class="trace">
              @for (s of steps(); track s.agent; let i = $index) {
                <app-trace-step [step]="s" [nameKey]="stepKey(i)" [open]="true" />
              }
            </div>
          }
        </div>
      }
    </section>
  `,
  styles: [`
    .ask-desk { padding: 12px 14px; margin-bottom: 12px; }
    h2 { font-size: 1rem; margin: 0 0 2px; }
    .hint { margin: 0 0 8px; font-size: .8rem; opacity: .75; }
    .row { display: flex; gap: 8px; }
    .row input { flex: 1; min-width: 0; padding: 8px 10px; border-radius: 8px; border: 1px solid rgba(0,0,0,.2); font: inherit; }
    .row .btn { flex-shrink: 0; }
    .reason { margin: 10px 0 6px; font-size: .9rem; }
    .via { display: block; font-size: .75rem; opacity: .7; }
    .cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; max-height: 220px; overflow-y: auto; }
    .trace { max-height: 320px; overflow-y: auto; }
    .case { width: 100%; text-align: left; display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 8px 10px;
            border-radius: 8px; border: 1px solid rgba(0,0,0,.12); background: transparent; cursor: pointer; font: inherit; }
    .case:hover, .case:focus-visible { border-color: currentColor; }
    .id { font-weight: 600; } .type, .ward, .ppl { font-size: .8rem; opacity: .8; }
    .sum { flex-basis: 100%; font-size: .82rem; }
    .link { background: none; border: 0; padding: 6px 0; text-decoration: underline; cursor: pointer; font: inherit; font-size: .8rem; }
    .err { color: #b3261e; }
  `],
})
export class AskDeskComponent {
  private readonly api = inject(ApiClientService);
  private readonly lang = inject(LanguageService);
  readonly picked = output<string>();
  readonly busy = signal(false);
  readonly error = signal(false);
  readonly answer = signal<DeskAnswer | null>(null);
  readonly showTrace = signal(false);
  question = '';

  ask(): void {
    const q = this.question.trim();
    if (!q || this.busy()) return;
    this.busy.set(true);
    this.error.set(false);
    this.api.askDesk(q, this.lang.currentLang()).subscribe({
      next: (a: DeskAnswer) => {
        this.answer.set(a);
        this.busy.set(false);
      },
      error: () => {
        this.error.set(true);
        this.busy.set(false);
      },
    });
  }

  steps(): TraceStepView[] {
    return (this.answer()?.trace || []).map((t) => ({
      agent: String(t['agent']),
      status: 'done',
      output: t['output'] ?? null,
      model: t['model'] ?? null,
      provider: t['provider'] ?? null,
      latencyMs: typeof t['latency_ms'] === 'number' ? t['latency_ms'] : null,
      input: t['input'] ?? null,
      tools: [],
      asked: null,
      raw: null,
      note: t['note'] ?? null,
    }));
  }

  stepKey(i: number): string {
    return STEP_KEYS[i] || 'ux.notRecorded';
  }

  matchesText(n: number): string {
    this.lang.currentLang();
    return this.lang.translate('ux.deskMatches').replace('{n}', String(n));
  }

  peopleText(n: number): string {
    this.lang.currentLang();
    return this.lang.translate('ux.deskPeople').replace('{n}', String(n));
  }

  viaText(a: DeskAnswer): string {
    this.lang.currentLang();
    if (a.ai.provider === 'gemini') return a.ai.model || '';
    if (a.ai.provider === 'cache') return `${a.ai.model || ''} · ${this.lang.translate('ux.badgeRecorded')}`;
    return this.lang.translate('ux.deskByRules');
  }
}
