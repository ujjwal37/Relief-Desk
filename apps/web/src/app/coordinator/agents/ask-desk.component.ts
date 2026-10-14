import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiClientService, LanguageService, RdTranslatePipe } from '@rd/shared';
import { testProviderWord } from './provider-label';
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
  ai: { provider: string; model: string | null; vendor?: string | null; fallback_reason?: string | null };
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
    <section class="ask-desk card" [class.page]="fullPage()" [class.has-thread]="thread().length > 0" aria-labelledby="ask-desk-h">
      @if (!fullPage()) {
        <h2 id="ask-desk-h">{{ 'ux.deskTitle' | rdTranslate }}</h2>
        <p class="hint">{{ 'ux.deskHint' | rdTranslate }}</p>
      } @else {
        <h2 id="ask-desk-h" class="sr">{{ 'ux.deskTitle' | rdTranslate }}</h2>
      }
      @if (fullPage() && !thread().length) {
        <div class="empty">
          <p class="hello">{{ 'ux.agentHello' | rdTranslate }}</p>
          <div class="examples">
            @for (ex of examples; track ex.q) {
              <button type="button" class="example" (click)="useSuggestion(ex.q)">
                <span class="tag">{{ 'ux.exampleLabel' | rdTranslate }}</span>
                <strong>{{ ex.q | rdTranslate }}</strong>
                <p>{{ ex.a | rdTranslate }}</p>
              </button>
            }
          </div>
        </div>
      }
      <div class="thread">
        @for (turn of thread(); track $index; let last = $last) {
          <p class="bubble user">{{ turn.question }}</p>
          <div class="bubble desk">
            <p class="reason">
              <strong>{{ turn.answer.reason }}</strong>
            </p>
            @if (!turn.answer.cases.length) {
              <p class="none">{{ 'ux.deskNone' | rdTranslate }}</p>
            }
            <ul class="cards">
              @for (c of turn.answer.cases; track c.id) {
                <li>
                  <button type="button" class="case case-link" (click)="picked.emit(c.id)">
                    <span class="id">{{ c.id }}</span>
                    <span class="type">{{ ('incidentType.' + c.type) | rdTranslate }}</span>
                    @if (c.ward_name) { <span class="ward">{{ c.ward_name }}</span> }
                    @if (c.people_count) { <span class="ppl">{{ peopleText(c.people_count) }}</span> }
                    <span class="sum">{{ c.summary }}</span>
                  </button>
                </li>
              }
            </ul>
            @if (last) {
              <button type="button" class="link" (click)="showTrace.set(!showTrace())" [attr.aria-expanded]="showTrace()">
                {{ howAnswered(turn.answer) }}
              </button>
              @if (showTrace()) {
                <div class="trace">
                  @for (s of steps(); track s.agent; let i = $index) {
                    <app-trace-step [step]="s" [nameKey]="stepKey(i)" [open]="true" />
                  }
                </div>
              }
            }
          </div>
        }
      </div>
      @if (error()) {
        <p class="err" role="alert">{{ 'ux.deskError' | rdTranslate }}</p>
      }
      <form class="row composer" (ngSubmit)="ask()">
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
      <div class="suggestions">
        @for (key of suggestions; track key) {
          <button type="button" (click)="useSuggestion(key)">{{ key | rdTranslate }}</button>
        }
      </div>
    </section>
  `,
  styles: [`
    :host { display: block; height: 100%; }
    .ask-desk { padding: 12px 14px; margin-bottom: 12px; }
    h2 { font-size: 1rem; margin: 0 0 2px; }
    .sr { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
    .hint { margin: 0 0 8px; font-size: .8rem; opacity: .75; }
    .row { display: flex; gap: 8px; }
    .row input { flex: 1; min-width: 0; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border, rgba(0,0,0,.2)); background: var(--surface, #fff); color: inherit; font: inherit; }
    .row .btn { flex-shrink: 0; min-height: 44px; padding: 0 16px; border-radius: var(--r2); border: 0; background: var(--brand); color: var(--on-brand); font: 600 14px inherit; cursor: pointer; }
    .row .btn:disabled { opacity: .55; cursor: default; }
    .reason { margin: 0 0 6px; font-size: 14px; } .reason strong { font-weight: 600; }
    .via { display: block; font-size: .75rem; opacity: .7; }
    .cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; max-height: 220px; overflow-y: auto; }
    .trace { max-height: 320px; overflow-y: auto; }
    .case { width: 100%; text-align: left; display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 8px 10px;
            border-radius: 8px; border: 1px solid var(--border, rgba(0,0,0,.12)); background: transparent; color: inherit; cursor: pointer; font: inherit; }
    .case:hover, .case:focus-visible { border-color: currentColor; }
    .id { font-weight: 600; } .type, .ward, .ppl { font-size: .8rem; opacity: .8; }
    .sum { flex-basis: 100%; font-size: .82rem; }
    .link { background: none; border: 0; padding: 6px 0; text-decoration: underline; cursor: pointer; font: inherit; font-size: .8rem; color: inherit; }
    .err { color: var(--sev-crit); }
    .suggestions { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 0; }
    .suggestions button { min-height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--border, rgba(0,0,0,.2)); background: var(--surface, transparent); color: inherit; cursor: pointer; font: inherit; }
    .bubble.user { margin: 0; align-self: flex-end; max-width: 85%; padding: 10px 14px; border-radius: var(--r3) var(--r3) var(--r1) var(--r3); background: var(--brand-tint); font-weight: 600; }
    .bubble.desk { align-self: stretch; padding: 12px 14px; border-radius: var(--r3); border: 1px solid var(--border); background: var(--surface); }
    .thread { display: flex; flex-direction: column; gap: 10px; }
    .page { position: relative; display: flex; flex-direction: column; justify-content: center; height: 100%; min-height: 0; margin: 0; padding: 8px 0 12px; background: transparent; border: 0; box-shadow: none; }
    .page .thread { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
    .page.has-thread { justify-content: flex-start; }
    .page.has-thread .thread { flex: 1; overflow: auto; }
    .page .composer, .page .suggestions { flex: none; }
    .page .composer { padding:12px; border:1px solid var(--border); border-radius:16px; background:var(--surface); box-shadow:var(--e1); }
    .page .cards, .page .trace { max-height: none; }
    .page .row input { min-height: 52px; border-radius: 12px; padding: 0 16px; font-size: 14px; }
    .page .suggestions { justify-content: center; }
    .hello { margin: 0 0 16px; text-align: center; font-size: 32px; font-weight: 600; line-height: 1.25; }
    .empty { width: min(720px, 100%); margin: 0 auto 12px; }
    .examples { display: grid; gap: 10px; width: min(560px, 100%); margin: 0 auto; }
    .example { text-align: left; border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; background: var(--surface); color: inherit; cursor: pointer; font: inherit; box-shadow: var(--e1); }
    .example:hover { border-color:var(--brand); background:color-mix(in srgb,var(--brand) 3.5%,var(--surface)); }
    .example strong { display: block; margin: 4px 0; color:var(--brand); }
    .example p { margin: 0; color: var(--text-2); font-size: 14px; }
    .tag { font-size: 12px; font-weight: 600; letter-spacing:0; text-transform:none; color: var(--text-2); }
  `],
})
export class AskDeskComponent {
  private readonly api = inject(ApiClientService);
  private readonly lang = inject(LanguageService);
  readonly fullPage = input(false);
  readonly picked = output<string>();
  readonly suggestions = ['ux.suggestWaiting', 'ux.suggestElderly', 'ux.suggestBoats'];
  readonly examples = [
    { q: 'ux.suggestWaiting', a: 'ux.exampleA1' },
    { q: 'ux.suggestElderly', a: 'ux.exampleA2' },
    { q: 'ux.suggestBoats', a: 'ux.exampleA3' },
  ];
  readonly busy = signal(false);
  readonly error = signal(false);
  readonly answer = signal<DeskAnswer | null>(null);
  readonly thread = signal<{ question: string; answer: DeskAnswer }[]>([]);
  readonly showTrace = signal(false);
  question = '';

  useSuggestion(key: string): void {
    this.question = this.lang.translate(key);
    this.ask();
  }

  ask(): void {
    const q = this.question.trim();
    if (!q || this.busy()) return;
    this.busy.set(true);
    this.error.set(false);
    this.api.askDesk(q, this.lang.currentLang()).subscribe({
      next: (a: DeskAnswer) => {
        this.answer.set(a);
        this.thread.update((rows) => [...rows, { question: q, answer: a }]);
        this.question = '';
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
      vendor: t['vendor'] ?? null,
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

  howAnswered(a: DeskAnswer): string {
    this.lang.currentLang();
    const n = a.trace?.length || 2;
    return this.lang.translate('ux.deskHowAnswered').replace('{n}', String(n));
  }

  viaText(a: DeskAnswer): string {
    this.lang.currentLang();
    if (a.ai.provider === 'gemini') return a.ai.model || '';
    const test = testProviderWord(a.ai.provider, a.ai.vendor, (key) => this.lang.translate(key));
    if (test) return `${a.ai.model || ''} · ${test}`;
    if (a.ai.provider === 'cache') return `${a.ai.model || ''} · ${this.lang.translate('ux.badgeRecorded')}`;
    return this.lang.translate('ux.deskByRules');
  }
}
