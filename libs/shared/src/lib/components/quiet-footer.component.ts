import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RdTranslatePipe } from '../services/language.service';

@Component({
  selector: 'rd-quiet-footer',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<p>{{ 'safety.quiet' | rdTranslate }}</p>`,
  styles: [`p { margin:0; padding:12px 16px; text-align:center; font-size:13px; line-height:1.4; color:var(--text-2); }`],
})
export class QuietFooterComponent {}
