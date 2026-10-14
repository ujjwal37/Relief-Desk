import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RdTranslatePipe } from '@rd/shared';

/** gemini | fallback | replay | local (Antigravity CLI, manual testing). Height 26. Icon plus the word. */
@Component({
  selector: 'app-agent-badge',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './agent-badge.component.html',
  styleUrl: './agent-badge.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentBadgeComponent {
  readonly source = input.required<'gemini' | 'fallback' | 'replay' | 'local'>();
  readonly labelKey = computed(() => {
    if (this.source() === 'gemini') return 'ux.badgeGemini';
    if (this.source() === 'replay') return 'ux.badgeRecorded';
    if (this.source() === 'local') return 'ux.badgeLocal';
    return 'ux.badgeOffline';
  });
}
