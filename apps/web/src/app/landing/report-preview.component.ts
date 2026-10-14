import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CallPillComponent, RdTranslatePipe } from '@rd/shared';

/** Desktop "I need help" opens this in a new tab: the reporter inside a phone-width frame. */
@Component({
  selector: 'app-report-preview',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe, CallPillComponent],
  template: `
    <div class="stage">
      <header>
        <a routerLink="/" class="brand">{{ 'landing.title' | rdTranslate }}</a>
        <rd-call-pill />
      </header>
      <div class="phone">
        <iframe src="/report" [attr.title]="'ui.publicReport' | rdTranslate"></iframe>
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; min-height: 100vh; background: var(--bg); color: var(--text); }
    .stage { min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 12px 16px 24px; }
    header { width: min(100%, 840px); display: flex; justify-content: space-between; align-items: center; min-height: 56px; }
    .brand { color: var(--text); font-weight: 600; font-size: 18px; text-decoration: none; }
    .phone {
      width: 390px; max-width: 100%; height: min(844px, calc(100vh - 88px));
      border: 10px solid var(--text); border-radius: 36px; overflow: hidden; background: var(--surface); box-shadow: var(--e3);
    }
    iframe { width: 100%; height: 100%; border: 0; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportPreviewComponent {}
