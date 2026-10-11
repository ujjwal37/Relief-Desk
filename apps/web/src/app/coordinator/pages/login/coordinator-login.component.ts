import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

@Component({
  selector: 'app-coordinator-login',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './coordinator-login.component.html',
  styleUrl: './coordinator-login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorLoginComponent {
  constructor(private router: Router) {}

  loginDemo(): void {
    // Navigates to command view for demo coordinator
    this.router.navigate(['/coordinator/command']);
  }
}
