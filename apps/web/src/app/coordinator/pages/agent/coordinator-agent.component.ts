import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AskDeskComponent } from '../../agents/ask-desk.component';

/** Full-page desk chat. A case chip opens that case. Nothing is dispatched from here. */
@Component({
  selector: 'app-coordinator-agent',
  standalone: true,
  imports: [AskDeskComponent],
  template: `
    <section class="agent">
      <app-ask-desk [fullPage]="true" (picked)="openCase($event)" />
    </section>
  `,
  styles: [`
    :host { display: block; height: 100%; min-height: 0; overflow: hidden; }
    .agent { height: 100%; max-width: 840px; margin: 0 auto; padding: 28px 24px; display: flex; flex-direction: column; }
    app-ask-desk { flex: 1; min-height: 0; display: block; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorAgentComponent {
  private readonly router = inject(Router);

  openCase(id: string): void {
    void this.router.navigate(['/coordinator/command'], { queryParams: { case: id } });
  }
}
