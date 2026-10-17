import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';

export interface PipelineLiveStep {
  agent: string;
  status: string;
  summary?: string;
  similarity?: number;
  match_id?: string;
  tier?: string;
  score?: number;
  team?: string;
}

const ORDER = ['extract', 'dedupe', 'triage', 'matching', 'approval'] as const;

/** Compact live strip: extract → dedupe % → triage → find_teams → awaiting approval. */
@Component({
  selector: 'app-pipeline-strip',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ol class="strip" data-tour="how" data-testid="pipeline-strip" [attr.aria-label]="'xfactor.stripTitle' | rdTranslate">
      @for (row of rows(); track row.agent) {
        <li [class.on]="row.status === 'complete' || row.status === 'working'" [class.wait]="row.status === 'waiting' || row.status === 'pending'">
          <b>{{ row.label }}</b>
          @if (row.detail) { <span>{{ row.detail }}</span> }
        </li>
      }
    </ol>
  `,
  styles: [`
    .strip { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 0; padding:0; list-style:none; }
    li { display:flex; flex-direction:column; gap:1px; min-width:72px; padding:6px 8px; border-radius:8px;
      border:1px solid var(--border); background:var(--surface-2); color:var(--text-2); font-size:11px; line-height:1.25; }
    li.on { border-color: color-mix(in srgb, var(--brand) 35%, var(--border)); background:var(--brand-tint); color:var(--brand); }
    li.wait { opacity:.7; }
    b { font-size:11px; font-weight:700; }
  `],
})
export class PipelineStripComponent {
  private readonly lang = inject(LanguageService);
  readonly steps = input<PipelineLiveStep[]>([]);
  readonly analysing = input(false);

  rows(): { agent: string; label: string; detail: string; status: string }[] {
    const by = new Map(this.steps().map((step) => [step.agent, step]));
    return ORDER.map((agent) => {
      const raw = by.get(agent);
      const status = raw?.status || (this.analysing() && agent === 'extract' ? 'working' : 'pending');
      return { agent, label: this.label(agent), detail: this.detail(agent, raw), status };
    });
  }

  private label(agent: string): string {
    this.lang.currentLang();
    const key = ({
      extract: 'xfactor.stepExtract',
      dedupe: 'xfactor.stepDedupe',
      triage: 'xfactor.stepTriage',
      matching: 'flow.badgeTool',
      approval: 'flow.badgeYou',
    } as Record<string, string>)[agent];
    return key ? this.lang.translate(key) : agent;
  }

  private detail(agent: string, raw?: PipelineLiveStep): string {
    if (!raw) return '';
    if (agent === 'dedupe' && raw.similarity != null) {
      const pct = Math.round(raw.similarity * 100);
      return raw.match_id ? `${pct}% · ${raw.match_id}` : `${pct}%`;
    }
    if (agent === 'triage') return raw.tier || (raw.score != null ? String(raw.score) : '');
    if (agent === 'matching') return raw.team || 'find_teams()';
    if (agent === 'approval') return raw.status === 'waiting' ? this.lang.translate('xfactor.awaitingHuman') : '';
    return (raw.summary || '').slice(0, 42);
  }
}
