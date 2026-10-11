import { RdTranslatePipe } from '@rd/shared';
import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ScenarioService } from '../services/scenario.service';

@Component({
  selector: 'app-scenario-switcher',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe],
  template: `
    <div class="scenario-switch" role="group" [attr.aria-label]="'ui.scenarioPack' | rdTranslate">
      <button
        type="button"
        *ngFor="let pack of scenarios.scenarios()"
        [class.on]="scenarios.activeId() === pack.id"
        (click)="scenarios.select(pack.id)"
      >
        {{ pack.title }}
      </button>
    </div>
  `,
  styles: [`
    .scenario-switch { display: inline-flex; gap: 4px; flex-wrap: wrap; }
    button {
      min-height: 48px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,.16);
      background: transparent;
      color: #f8fafc;
      font-weight: 700;
      padding: 8px 12px;
      cursor: pointer;
    }
    button.on { background: #0f6b5a; color: white; border-color: #14b8a6; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScenarioSwitcherComponent implements OnInit {
  readonly scenarios = inject(ScenarioService);

  ngOnInit(): void {
    this.scenarios.ensureLoaded();
  }
}
