import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { LanguageService, RdTranslatePipe, StoredRequest } from '@rd/shared';

const ROWS = [
  { key: 'ux.agentIntake', indexes: [0] },
  { key: 'ux.agentParallel', indexes: [1, 2] },
  { key: 'ux.agentMatching', indexes: [3] },
  { key: 'ux.agentExplainer', indexes: [4] },
];

@Component({
  selector: 'app-analysing-card',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './analysing-card.component.html',
  styleUrl: './analysing-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AnalysingCardComponent {
  private readonly lang = inject(LanguageService);
  readonly request = input.required<StoredRequest>();
  readonly rows = ROWS;

  readonly done = computed(() => (this.request().trace || []).filter((step) => step.status === 'complete').length);
  readonly total = computed(() => Math.max(5, (this.request().trace || []).length || 5));
  readonly width = computed(() => Math.round((this.done() / this.total()) * 100));

  progress(): string {
    this.lang.currentLang();
    return this.lang.translate('ux.agentsDone')
      .replace('{done}', String(this.done()))
      .replace('{total}', String(this.total()));
  }

  stateFor(indexes: number[]): 'done' | 'running' | 'waiting' {
    const trace = this.request().trace || [];
    const states = indexes.map((index) => trace[index]?.status);
    if (states.some((status) => status === 'working')) return 'running';
    if (states.length && states.every((status) => status === 'complete')) return 'done';
    return 'waiting';
  }
}
