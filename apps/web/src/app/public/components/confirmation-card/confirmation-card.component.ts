import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfirmationCardData, LanguageService, RdTranslatePipe } from '@rd/shared';
import { waitTipsFor } from '../../wait-tips';

const INCIDENT_TYPES = ['rescue', 'food', 'medical', 'shelter', 'info', 'animal_attack', 'other'];
const VULNERABLE_KEYS = ['child', 'elderly', 'disabled', 'pregnant', 'medical_need'] as const;

function cloneCard(card: ConfirmationCardData): ConfirmationCardData {
  return {
    ...card,
    vulnerable: { ...(card.vulnerable || {}) },
  };
}

@Component({
  selector: 'rd-confirmation-card',
  standalone: true,
  imports: [CommonModule, FormsModule, RdTranslatePipe],
  templateUrl: './confirmation-card.component.html',
  styleUrl: './confirmation-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmationCardComponent {
  private lang = inject(LanguageService);
  readonly waitTipsFor = waitTipsFor;
  @Input() busy = false;
  @Input() quote = '';
  @Input() showActions = true;
  @Input() smsHref = '';
  @Output() send = new EventEmitter<ConfirmationCardData>();
  @Output() cardChange = new EventEmitter<ConfirmationCardData>();

  private _card!: ConfirmationCardData;

  @Input({ required: true })
  set card(value: ConfirmationCardData) {
    this._card = value;
    if (value) {
      this.draft.set(cloneCard(value));
    }
  }

  get card(): ConfirmationCardData {
    return this._card;
  }

  readonly incidentTypes = INCIDENT_TYPES;
  readonly vulnerableKeys = VULNERABLE_KEYS;
  readonly draft = signal<ConfirmationCardData | null>(null);
  readonly editing = signal<'type' | 'location' | 'people' | null>(null);
  readonly anonymous = signal(true);

  vulnerableLabel(key: string): string {
    if (key === 'medical_need') {
      return 'confirm.medical';
    }
    return `confirm.${key}`;
  }

  isVulnerable(key: string): boolean {
    return !!this.draft()?.vulnerable?.[key];
  }

  startEdit(field: 'type' | 'location' | 'people'): void {
    this.editing.set(this.editing() === field ? null : field);
  }

  patch(partial: Partial<ConfirmationCardData>): void {
    const current = this.draft();
    if (!current) {
      return;
    }
    const next = { ...current, ...partial, vulnerable: { ...current.vulnerable, ...(partial.vulnerable || {}) } };
    next.summary = this.composeSummary(next);
    this.draft.set(next);
    this.cardChange.emit(cloneCard(next));
  }

  setType(value: string): void {
    this.patch({ incident_type: value });
  }

  setPlace(value: string): void {
    this.patch({ place_text: value });
  }

  setPeople(value: string | number): void {
    const parsed = Math.max(0, Math.min(99, Number(value) || 0));
    this.patch({ people_count: parsed });
  }

  toggleVulnerable(key: string): void {
    const current = this.draft();
    if (!current) {
      return;
    }
    this.patch({
      vulnerable: {
        ...current.vulnerable,
        [key]: !current.vulnerable?.[key],
      },
    });
  }

  onSend(): void {
    const current = this.draft();
    if (!current || this.busy) {
      return;
    }
    this.send.emit(cloneCard(current));
  }

  private composeSummary(card: ConfirmationCardData): string {
    // Unknown stays unknown: a missing count is 'not stated', never 0.
    const count = card.people_count ?? this.lang.translate('people.notStated');
    const type = this.lang.translate(`incidentType.${card.incident_type}`);
    const vulns = Object.entries(card.vulnerable || {})
      .filter(([, on]) => on)
      .map(([key]) => this.lang.translate(key === 'medical_need' ? 'confirm.medical' : `confirm.${key}`));
    const parts = [`${count} · ${type}`];
    if (card.place_text) {
      parts.push(card.place_text);
    }
    if (vulns.length) {
      parts.push(vulns.join(', '));
    }
    if (card.hazard && card.hazard !== 'none' && card.hazard !== 'unknown') {
      parts.push(this.lang.translate(`hazardKind.${card.hazard}`));
    }
    return parts.join(' · ');
  }
}
