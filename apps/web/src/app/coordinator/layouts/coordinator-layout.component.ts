import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-coordinator-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink],
  templateUrl: './coordinator-layout.component.html',
  styleUrl: './coordinator-layout.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorLayoutComponent {}
