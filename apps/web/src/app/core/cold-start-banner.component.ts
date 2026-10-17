import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RdTranslatePipe } from '@rd/shared';
import { ColdStartService } from './cold-start.service';

/** Non-blocking notice while a scaled-to-zero demo server is waking up. */
@Component({
  selector: 'app-cold-start-banner',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './cold-start-banner.component.html',
  styleUrl: './cold-start-banner.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ColdStartBannerComponent {
  readonly cold = inject(ColdStartService);

  retry(): void {
    this.cold.retry();
  }
}
