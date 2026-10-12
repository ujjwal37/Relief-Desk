import { AfterViewInit, ChangeDetectionStrategy, Component, ElementRef, HostListener, computed, inject, input, output, signal } from '@angular/core';
import { LanguageService, RdTranslatePipe, StoredRequest } from '@rd/shared';
import { AgentBadgeComponent } from './agent-badge.component';
import { TraceStepComponent, TraceStepView } from './trace-step.component';

const ORDER = ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'] as const;
const NAMES: Record<string, string> = {
  Intake: 'ux.agentIntake',
  Dedupe: 'ux.agentDedupe',
  Triage: 'ux.agentTriage',
  Matching: 'ux.agentMatching',
  Explainer: 'ux.agentExplainer',
};

@Component({
  selector: 'app-agent-trace-drawer',
  standalone: true,
  imports: [RdTranslatePipe, AgentBadgeComponent, TraceStepComponent],
  templateUrl: './agent-trace-drawer.component.html',
  styleUrl: './agent-trace-drawer.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentTraceDrawerComponent implements AfterViewInit {
  private readonly lang = inject(LanguageService);
  private readonly host = inject(ElementRef<HTMLElement>);
  readonly request = input.required<StoredRequest>();
  readonly mobile = input(false);
  readonly closed = output<void>();
  readonly retry = output<void>();
  readonly expanded = signal<string | null>(null);

  readonly source = computed<'gemini' | 'fallback' | 'replay' | 'local'>(() => {
    const req = this.request();
    if (req.ai?.provider === 'cache' || req.ai?.cached || req.ai_source === 'recorded') return 'replay';
    if (req.ai?.provider === 'antigravity-local' || req.ai_source === 'antigravity-local') return 'local';
    if (req.ai?.provider === 'gemini' || req.ai_source === 'gemini') return 'gemini';
    return 'fallback';
  });

  readonly steps = computed(() => {
    const byName = new Map((this.request().trace || []).map((step) => [step.agent, step]));
    return ORDER.map((agent) => this.toView(agent, byName.get(agent)));
  });

  readonly parallel = computed(() => this.steps().filter((step) => step.agent === 'Dedupe' || step.agent === 'Triage'));
  readonly solo = computed(() => this.steps().filter((step) => step.agent !== 'Dedupe' && step.agent !== 'Triage'));

  readonly totalText = computed(() => {
    this.lang.currentLang();
    const steps = this.steps();
    if (steps.some((step) => step.latencyMs == null)) return null;
    const of = (agent: string) => steps.find((step) => step.agent === agent)?.latencyMs || 0;
    const ms = of('Intake') + Math.max(of('Dedupe'), of('Triage')) + of('Matching') + of('Explainer');
    if (ms < 1000) return this.lang.translate('ux.ms').replace('{n}', String(Math.round(ms)));
    return this.lang.translate('ux.seconds').replace('{n}', (ms / 1000).toFixed(1));
  });

  ngAfterViewInit(): void {
    queueMicrotask(() => {
      const close = this.host.nativeElement.querySelector('.x') as HTMLElement | null;
      close?.focus();
    });
  }

  nameKey(agent: string): string {
    return NAMES[agent] || 'ux.notRecorded';
  }

  toggle(agent: string): void {
    this.expanded.update((current) => (current === agent ? null : agent));
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    this.closed.emit();
  }

  private toView(agent: string, raw?: NonNullable<StoredRequest['trace']>[number]): TraceStepView {
    const status = this.statusOf(raw?.status, raw);
    return {
      agent,
      status,
      output: raw?.output || null,
      model: raw?.model || null,
      provider: (raw as { provider?: string } | undefined)?.provider || null,
      latencyMs: typeof raw?.latency_ms === 'number' ? raw.latency_ms : null,
      input: raw?.input_summary || null,
      tools: (raw?.tool_calls || []).map((tool) => this.toolText(tool)),
      asked: raw?.input_summary || null,
      raw: raw?.output || null,
      note: status === 'fallback'
        ? (this.request().ai?.fallback_reason || raw?.output || null)
        : status === 'error'
          ? (raw?.output || null)
          : null,
    };
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
