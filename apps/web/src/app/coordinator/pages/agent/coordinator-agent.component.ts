import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';
import { RdTranslatePipe } from '@rd/shared';
import { AskDeskComponent } from '../../agents/ask-desk.component';

/** Full-page desk chat. A case chip opens that case. Nothing is dispatched from here. */
@Component({
  selector: 'app-coordinator-agent',
  standalone: true,
  imports: [RdTranslatePipe, AskDeskComponent],
  template: `
    <section class="agent">
      <h1>{{ 'coord.agent' | rdTranslate }}</h1>
      <p>{{ 'coord.agentLead' | rdTranslate }}</p>
      <app-ask-desk [fullPage]="true" (picked)="openCase($event)" />
    </section>
  `,
  styles: [`
    :host { display: block; height: 100%; overflow: auto; }
    .agent { max-width: 820px; margin: 0 auto; padding: 16px; }
    h1 { margin: 0; font-size: 22px; font-weight: 800; }
    p { margin: 4px 0 12px; color: var(--text-2); }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorAgentComponent {
  private readonly router = inject(Router);

  openCase(id: string): void {
    void this.router.navigate(['/coordinator/command'], { queryParams: { case: id } });
  }
}
