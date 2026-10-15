import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { LanguageService } from '@rd/shared';
import { AskDeskComponent } from '../../agents/ask-desk.component';

/** Full-page desk chat. A case chip opens that case. Nothing is dispatched from here. */
@Component({
  selector: 'app-coordinator-agent',
  standalone: true,
  imports: [AskDeskComponent],
  template: `
    <section class="agent">
      <app-ask-desk [fullPage]="true" [seedQuestion]="seedQuestion()" (picked)="openCase($event)" />
    </section>
  `,
  styles: [`
    :host { display: block; height: 100%; min-height: 0; overflow: hidden; }
    .agent { height: 100%; max-width: 1240px; margin: 0 auto; padding: 28px; display: flex; flex-direction: column; }
    app-ask-desk { flex: 1; min-height: 0; display: block; }
    @media (max-width:700px) { .agent { padding:12px; } }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorAgentComponent {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly lang = inject(LanguageService);
  readonly seedQuestion = signal('');

  constructor() {
    this.route.queryParamMap.subscribe((params) => {
      if (params.get('ask') === 'pending') {
        this.seedQuestion.set(this.lang.translate('xfactor.askPending'));
      }
    });
  }

  openCase(id: string): void {
    void this.router.navigate(['/coordinator/command'], { queryParams: { case: id } });
  }
}
