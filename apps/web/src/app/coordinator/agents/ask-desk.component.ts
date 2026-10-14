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
        <header class="workspace-bar">
          <div>
            <h2 id="ask-desk-h">{{ 'ux.deskTitle' | rdTranslate }}</h2>
            <p class="hint">{{ 'ux.deskHint' | rdTranslate }}</p>
          </div>
          <span class="scope">{{ 'ux.agentScope' | rdTranslate }}</span>
        </header>
      }
      @if (fullPage() && !thread().length) {
        <div class="empty">
          <div class="welcome">
            <span class="welcome-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor"><path d="M12 2l2.2 6.3L21 10l-6.8 1.7L12 18l-2.2-6.3L3 10l6.8-1.7z"/></svg></span>
            <p class="hello">{{ 'ux.agentHello' | rdTranslate }}</p>
            <p class="welcome-copy">{{ 'ux.agentIntro' | rdTranslate }}</p>
          </div>
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
      <div class="composer-dock">
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
        @if (fullPage()) {
          <p class="composer-note">{{ 'ux.agentFootnote' | rdTranslate }}</p>
        }
      </div>
      @if (!fullPage()) {
        <div class="suggestions">
          @for (key of suggestions; track key) {
            <button type="button" (click)="useSuggestion(key)">{{ key | rdTranslate }}</button>
          }
        </div>
      }
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
    .page {
      position:relative; display:flex; flex-direction:column; gap:24px; height:100%; min-height:0;
      margin:0; padding:24px 28px 18px; border:1px solid var(--border); border-radius:16px;
      background:var(--surface); box-shadow:var(--e1);
    }
    .workspace-bar { flex:none; display:flex; align-items:center; justify-content:space-between; gap:16px; padding-bottom:20px; border-bottom:1px solid var(--border); }
    .workspace-bar h2 { margin:0 0 4px; font:var(--t-panel); letter-spacing:var(--t-panel-ls); }
    .workspace-bar .hint { margin:0; opacity:1; color:var(--text-2); font:var(--t-label); }
    .scope { flex:none; padding:5px 10px; border:1px solid color-mix(in srgb,var(--brand) 18%,var(--border)); border-radius:7px; background:var(--brand-tint); color:var(--brand); font:500 12px/18px var(--font-sans); }
    .page .thread { display:flex; flex-direction:column; gap:18px; min-height:0; }
    .page.has-thread .thread { flex:1; overflow:auto; padding:4px 4px 12px; }
    .page .cards, .page .trace { max-height:none; }
    .empty { flex:1; min-height:0; display:grid; grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr); align-items:center; gap:48px; width:100%; margin:0; padding:12px 8px; }
    .welcome { max-width:380px; }
    .welcome-icon { display:grid; place-items:center; width:56px; height:56px; margin-bottom:24px; border-radius:16px; color:var(--brand); background:var(--brand-tint); }
    .hello { margin:0 0 16px; font:600 36px/42px var(--font-sans); letter-spacing:-.035em; text-wrap:balance; }
    .welcome-copy { max-width:32ch; margin:0; font:400 16px/25px var(--font-sans); color:var(--text-2); }
    .examples { display:grid; gap:12px; width:100%; margin:0; }
    .example { position:relative; text-align:left; border:1px solid var(--border); border-radius:12px; padding:16px 40px 16px 18px; background:var(--bg); color:inherit; cursor:pointer; font:inherit; transition:background 120ms var(--ease),border-color 120ms var(--ease); }
    .example::after { content:'\\203A'; position:absolute; top:50%; right:18px; transform:translateY(-50%); font-size:24px; font-weight:400; color:var(--brand); }
    .example:hover { border-color:var(--brand); background:var(--brand-tint); }
    .example strong { display:block; margin:6px 0 4px; font:600 15px/21px var(--font-sans); }
    .example p { margin:0; color:var(--text-2); font:400 13px/20px var(--font-sans); }
    .tag { display:inline-flex; font:500 11px/16px var(--font-sans); color:var(--brand); }
    .page .composer-dock { flex:none; margin-top:auto; }
    .page .composer { padding:8px; border:1px solid var(--border); border-radius:12px; background:var(--bg); }
    .page .composer:focus-within { border-color:var(--brand); box-shadow:0 0 0 3px color-mix(in srgb,var(--brand) 8%,transparent); }
    .page .row input { min-height:44px; border:0; outline:0; background:transparent; border-radius:8px; padding:0 10px; font:var(--t-body); }
    .page .row .btn { min-height:44px; padding:0 22px; font:600 14px/20px var(--font-sans); }
    .composer-note { margin:10px 0 0; color:var(--muted); font:400 12px/18px var(--font-sans); text-align:center; }
    .page .bubble.user { font:500 14px/22px var(--font-sans); padding:12px 16px; }
    .page .bubble.desk { padding:20px; box-shadow:var(--e1); }
    .page .case { padding:12px; background:var(--bg); border-radius:10px; }
    .page .case:hover { border-color:var(--brand); background:var(--brand-tint); }
    .page .reason { font:400 14px/22px var(--font-sans); margin-bottom:14px; }
    .page .link { margin-top:10px; color:var(--brand); }
    @media (max-width:1100px) { .empty { gap:28px; padding:8px 0; } .hello { font-size:30px; line-height:36px; } }
    @media (max-width:700px) {
      .page { padding:16px; gap:16px; overflow:auto; border-radius:12px; }
      .workspace-bar { gap:8px; padding-bottom:14px; }
      .workspace-bar .hint { font-size:12px; line-height:18px; }
      .scope { display:none; }
      .empty { display:flex; flex-direction:column; align-items:stretch; flex:none; gap:20px; padding:4px 0; }
      .welcome { max-width:none; }
      .welcome-icon { width:36px; height:36px; border-radius:10px; margin-bottom:14px; }
      .welcome-icon svg { width:22px; height:22px; }
      .hello { margin-bottom:8px; font-size:25px; line-height:31px; letter-spacing:-.025em; }
      .welcome-copy { max-width:none; font-size:14px; line-height:21px; }
      .examples { gap:8px; }
      .example { padding:12px 32px 12px 14px; }
      .example strong { margin:3px 0; font-size:14px; line-height:20px; }
      .example p { display:none; }
      .example::after { right:12px; }
      .page .composer-dock { position:sticky; bottom:-16px; background:var(--surface); padding:10px 0 14px; }
      .page .row .btn { padding:0 16px; }
      .page .bubble.desk { padding:14px; }
      .page.has-thread .thread { flex:1 0 200px; overflow:visible; }
      .composer-note { font-size:11px; line-height:16px; }
    }
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
