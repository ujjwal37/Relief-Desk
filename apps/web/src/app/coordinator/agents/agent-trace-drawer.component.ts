import { AfterViewInit, ChangeDetectionStrategy, Component, ElementRef, HostListener, OnDestroy, computed, effect, inject, input, output, signal } from '@angular/core';
import { LanguageService, RdTranslatePipe, StoredRequest } from '@rd/shared';
import { testProviderWord } from './provider-label';
import { TraceStepComponent, TraceStepView } from './trace-step.component';

const ORDER = ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'] as const;
const NAMES: Record<string, string> = {
  Intake: 'flow.intake',
  Dedupe: 'flow.dedupe',
  Triage: 'flow.urgency',
  Matching: 'flow.matching',
  Explainer: 'flow.explain',
};

@Component({
  selector: 'app-agent-trace-drawer',
  standalone: true,
  imports: [RdTranslatePipe, TraceStepComponent],
  templateUrl: './agent-trace-drawer.component.html',
  styleUrl: './agent-trace-drawer.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentTraceDrawerComponent implements AfterViewInit, OnDestroy {
  private readonly lang = inject(LanguageService);
  private readonly host = inject(ElementRef<HTMLElement>);
  readonly request = input.required<StoredRequest>();
  readonly mobile = input(false);
  readonly closed = output<void>();
  readonly retry = output<void>();
  readonly expanded = signal<string | null>(null);
  private poll: ReturnType<typeof setInterval> | null = null;

  constructor() {
    effect(() => {
      const loading = this.runState() === 'loading';
      this.stopPoll();
      if (loading) this.poll = setInterval(() => this.retry.emit(), 1000);
    });
  }

  readonly steps = computed(() => {
    this.lang.currentLang();
    const byName = new Map((this.request().trace || []).map((step) => [step.agent, step]));
    return ORDER.map((agent) => this.toView(agent, byName.get(agent)));
  });

  readonly intakeStep = computed(() => this.steps().filter((step) => step.agent === 'Intake' && this.visible(step)));
  readonly parallel = computed(() => this.steps().filter((step) => (step.agent === 'Dedupe' || step.agent === 'Triage') && this.visible(step)));
  readonly afterParallel = computed(() => this.steps().filter((step) => (step.agent === 'Matching' || step.agent === 'Explainer') && this.visible(step)));

  readonly runState = computed(() => {
    const req = this.request();
    const steps = this.steps();
    if (!req.trace?.length) return 'empty' as const;
    const analysis = String(req.analysis_status || '');
    if (analysis === 'analysing' || steps.some((step) => step.status === 'running')) return 'loading' as const;
    if (analysis === 'failed' || analysis === 'error' || steps.some((step) => step.status === 'error')) {
      return 'failed' as const;
    }
    if (this.rulesCount() > 0) return 'fallback' as const;
    return 'done' as const;
  });

  readonly headerWord = computed(() => {
    this.lang.currentLang();
    const req = this.request();
    const intake = (req.trace || []).find((row) => row.agent === 'Intake');
    if (testProviderWord(req.ai?.provider || req.ai_source, intake?.vendor, (key) => this.lang.translate(key))) {
      return this.lang.translate('flow.badgeTest');
    }
    for (const step of this.steps()) {
      if (testProviderWord(step.provider, step.vendor, (key) => this.lang.translate(key))) {
        return this.lang.translate('flow.badgeTest');
      }
    }
    if (this.steps().some((step) => {
      const source = String(step.provider || '').toLowerCase();
      return (source === 'gemini' || source === 'llm') && step.status === 'done';
    })) {
      return this.lang.translate('flow.badgeGemini');
    }
    const src = String(req.ai?.provider || req.ai_source || '').toLowerCase();
    if (src === 'gemini' || src === 'llm') {
      return this.lang.translate('flow.badgeGemini');
    }
    return this.lang.translate('flow.badgeRules');
  });

  readonly headline = computed(() => {
    this.lang.currentLang();
    const n = this.steps().filter((step) => step.status !== 'waiting').length || this.steps().length;
    return this.lang.translate('flow.headline').replace('{n}', String(n));
  });

  readonly contextLine = computed(() => {
    this.lang.currentLang();
    const req = this.request();
    const title = (req.summary || req.place_text || req.id).slice(0, 48);
    return this.lang.translate('flow.forCase').replace('{id}', req.id).replace('{title}', title);
  });

  readonly totalText = computed(() => {
    this.lang.currentLang();
    const starts = (this.request().trace || []).map((step) => Date.parse(String((step as { started_at?: string }).started_at || ''))).filter((n) => Number.isFinite(n));
    const ends = (this.request().trace || []).map((step) => Date.parse(String((step as { ended_at?: string }).ended_at || ''))).filter((n) => Number.isFinite(n));
    if (starts.length && ends.length) {
      const ms = Math.max(0, Math.max(...ends) - Math.min(...starts));
      if (ms > 0) return this.lang.translate('ux.seconds').replace('{n}', (ms / 1000).toFixed(1));
    }
    const listed = this.steps();
    if (listed.some((step) => step.latencyMs == null)) return null;
    const of = (agent: string) => listed.find((step) => step.agent === agent)?.latencyMs || 0;
    const ms = of('Intake') + Math.max(of('Dedupe'), of('Triage')) + of('Matching') + of('Explainer');
    if (ms <= 0) return null;
    return this.lang.translate('ux.seconds').replace('{n}', (ms / 1000).toFixed(1));
  });

  fallbackText(): string {
    this.lang.currentLang();
    return this.lang.translate('flow.fallbackBanner').replace('{n}', String(this.rulesCount()));
  }

  loadingText(): string {
    this.lang.currentLang();
    const steps = this.steps();
    const done = steps.filter((step) => step.status === 'done' || step.status === 'fallback').length;
    const k = Math.min(5, done + 1);
    const time = this.totalText() || this.lang.translate('ux.seconds').replace('{n}', '0');
    return this.lang.translate('flow.loading').replace('{k}', String(k)).replace('{n}', '5').replace('{t}', time.replace(/[^\d.]/g, '') || '0');
  }

  nameKey(agent: string): string {
    return NAMES[agent] || 'flow.intake';
  }

  toggle(agent: string): void {
    this.expanded.update((current) => (current === agent ? null : agent));
  }

  ngOnDestroy(): void {
    this.stopPoll();
  }

  ngAfterViewInit(): void {
    queueMicrotask(() => {
      const close = this.host.nativeElement.querySelector('.x') as HTMLElement | null;
      close?.focus();
    });
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    this.closed.emit();
  }

  @HostListener('keydown', ['$event'])
  onTab(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return;
    const root = this.host.nativeElement.querySelector('.drawer') as HTMLElement | null;
    if (!root) return;
    const nodes = Array.from(root.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'))
      .filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null);
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  private stopPoll(): void {
    if (this.poll) {
      clearInterval(this.poll);
      this.poll = null;
    }
  }

  private rulesCount(): number {
    return this.steps().filter((step) => step.badge === 'rules').length;
  }

  private visible(step: TraceStepView): boolean {
    const listed = this.steps();
    const failedAt = listed.findIndex((row) => row.status === 'error');
    if (failedAt >= 0) {
      return listed.findIndex((row) => row.agent === step.agent) <= failedAt;
    }
    return true;
  }

  private toView(agent: string, raw?: NonNullable<StoredRequest['trace']>[number]): TraceStepView {
    const status = this.statusOf(raw?.status, raw);
    const tools = (raw?.tool_calls || []).map((tool) => this.toolText(tool)).filter((row) => this.kept(row));
    const input = this.kept(raw?.input_summary) ? String(raw?.input_summary) : null;
    const output = this.kept(raw?.output) ? String(raw?.output) : null;
    const prompt = this.kept((raw as { prompt?: string } | undefined)?.prompt) ? String((raw as { prompt?: string }).prompt) : null;
    const model = this.kept(raw?.model) ? String(raw?.model) : null;
    const latencyMs = typeof raw?.latency_ms === 'number' && raw.latency_ms > 0 ? raw.latency_ms : null;
    const note = status === 'fallback'
      ? (this.kept(this.request().ai?.fallback_reason) ? String(this.request().ai?.fallback_reason) : null)
      : status === 'error' && this.kept(raw?.output) ? String(raw?.output) : null;
    const badge = this.stepBadge(raw);
    return {
      agent,
      status,
      output,
      model,
      provider: raw?.provider || null,
      vendor: raw?.vendor || null,
      latencyMs,
      input,
      tools,
      asked: prompt,
      raw: output,
      note,
      sentence: this.sentence(agent, raw),
      linkId: agent === 'Dedupe' ? this.dupId(raw) : null,
      badge,
      hasDetails: !!(input || prompt || tools.length || output || (model && latencyMs) || note),
    };
  }

  private stepBadge(raw?: NonNullable<StoredRequest['trace']>[number]): 'gemini' | 'rules' | 'test' {
    const test = testProviderWord(raw?.provider, raw?.vendor, (key) => this.lang.translate(key));
    if (test) return 'test';
    const source = String(raw?.provider || '').toLowerCase();
    const ok = raw?.status !== 'fallback' && raw?.status !== 'error';
    if (ok && (source === 'gemini' || source === 'llm')) return 'gemini';
    return 'rules';
  }

  private sentence(agent: string, raw?: NonNullable<StoredRequest['trace']>[number]): string {
    const t = (key: string) => this.lang.translate(key);
    const req = this.request();
    const parsed = this.parse(raw?.output);
    const cap = (text: string) => (text.length > 90 ? text.slice(0, 89).trim() : text);
    if (agent === 'Intake') {
      const need = String(parsed['need'] || parsed['type'] || req.type || t('coord.queueNeedBoat'));
      const people = String(parsed['people'] || req.people_count || 1);
      return cap(t('flow.sentIntake').replace('{need}', need).replace('{people}', people));
    }
    if (agent === 'Dedupe') {
      const id = this.dupId(raw);
      if (id) {
        const mins = String(parsed['minutes'] || req.possible_duplicate?.minutes || '4');
        return cap(t('flow.sentDedupeHit').replace('{id}', id).replace('{n}', mins));
      }
      return cap(t('flow.sentDedupeClear'));
    }
    if (agent === 'Triage') {
      const band = String(parsed['band'] || (req.urgency_reason || '').split(':')[0] || 'critical');
      const reason = String(parsed['reason'] || req.urgency_reason || '');
      return cap(t('flow.sentUrgency').replace('{band}', band).replace('{reason}', reason || band));
    }
    if (agent === 'Matching') {
      const team = String(parsed['team'] || parsed['resource_name'] || req.assigned_resource_id || raw?.output || 'team');
      const km = String(parsed['km'] || parsed['distance_km'] || '—');
      const capab = String(parsed['capability'] || parsed['kind'] || req.type || '');
      const seats = String(parsed['seats'] || parsed['capacity'] || '1');
      return cap(t('flow.sentMatch').replace('{team}', team).replace('{km}', km).replace('{capability}', capab).replace('{seats}', seats));
    }
    return cap(t('flow.sentExplain'));
  }

  private dupId(raw?: NonNullable<StoredRequest['trace']>[number]): string {
    const parsed = this.parse(raw?.output);
    return String(parsed['id'] || this.request().possible_duplicate?.target_id || '');
  }

  private parse(output: unknown): Record<string, string> {
    if (!output) return {};
    if (typeof output === 'object') return output as Record<string, string>;
    const text = String(output);
    try {
      const json = JSON.parse(text);
      return json && typeof json === 'object' ? json as Record<string, string> : {};
    } catch {
      return {};
    }
  }

  private kept(value: unknown): boolean {
    if (value == null) return false;
    if (typeof value === 'number') return value > 0;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'object') return Object.keys(value as object).length > 0;
    const text = String(value).trim();
    if (!text) return false;
    const lower = text.toLowerCase();
    return lower !== 'not recorded' && lower !== 'no tools' && lower !== 'null';
  }

  private toolText(tool: unknown): string {
    if (typeof tool === 'string') return tool;
    if (tool && typeof tool === 'object' && 'name' in tool) {
      const row = tool as { name?: string; args?: unknown; result?: unknown };
      const args = row.args == null ? '' : JSON.stringify(row.args);
      const result = row.result == null ? '' : ` -> ${typeof row.result === 'string' ? row.result : JSON.stringify(row.result)}`;
      return `${row.name || ''}(${args})${result}`;
    }
    return '';
  }

  private statusOf(value: string | undefined, raw: { output?: string } | undefined): TraceStepView['status'] {
    if (value === 'error') return 'error';
    if (value === 'working') return 'running';
    if (value === 'pending' || !raw) return 'waiting';
    if (value === 'fallback') return 'fallback';
    return 'done';
  }
}
