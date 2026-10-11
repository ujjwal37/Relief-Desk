import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RdTranslatePipe, LanguageSwitcherComponent } from '@rd/shared';

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe, LanguageSwitcherComponent],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {}
