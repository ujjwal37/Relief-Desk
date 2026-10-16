import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ColdStartBannerComponent } from './core/cold-start-banner.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ColdStartBannerComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  protected readonly title = signal('web');
}
