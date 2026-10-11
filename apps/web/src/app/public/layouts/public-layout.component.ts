import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { RdTranslatePipe, LanguageSwitcherComponent } from '@rd/shared';
import { ScenarioSwitcherComponent } from '../../core/components/scenario-switcher.component';

@Component({
  selector: 'app-public-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RdTranslatePipe, LanguageSwitcherComponent, ScenarioSwitcherComponent],
  templateUrl: './public-layout.component.html',
  styleUrl: './public-layout.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PublicLayoutComponent {}
