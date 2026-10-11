import { ChangeDetectionStrategy, Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  ApiClientService,
  LanguageService,
  RdTranslatePipe,
  ConfirmationCardData,
  ChatTurnResponse,
  ReportSubmitResponse,
  ReportSubmitRequest,
  StructuredReportFacts,
} from '@rd/shared';

import { OfflineSyncService } from '../../../core/services/offline-sync.service';
import { ConfirmationCardComponent } from '../../components/confirmation-card/confirmation-card.component';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: Date;
}

const EMPTY_VULNERABLE: Record<string, boolean> = {
  child: false,
  elderly: false,
  disabled: false,
  pregnant: false,
  medical_need: false,
};

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [CommonModule, FormsModule, RdTranslatePipe, ConfirmationCardComponent],
  templateUrl: './report.component.html',
  styleUrl: './report.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportComponent implements OnInit {
  private apiClient = inject(ApiClientService);
  private router = inject(Router);
  readonly langService = inject(LanguageService);
  readonly offlineSync = inject(OfflineSyncService);

  readonly sessionId = signal<string>(`sess_${Math.random().toString(36).substring(2, 9)}`);
  readonly mode = signal<'chat' | 'form'>('chat');
  readonly userInput = signal<string>('');
  readonly isRecording = signal<boolean>(false);
  readonly isLoading = signal<boolean>(false);
  readonly locationPin = signal<{ lat: number; lng: number }>({ lat: 26.852, lng: 80.925 });
  readonly locationText = signal<string>('Ward 7 · Auto-detected');

  readonly chatMessages = signal<ChatMessage[]>([]);
  readonly pendingCard = signal<ConfirmationCardData | null>(null);
  readonly submittedResult = signal<ReportSubmitResponse | null>(null);

  ngOnInit(): void {
    this.chatMessages.set([
      {
        id: 'msg_welcome',
        role: 'assistant',
        text: 'Namaste. Describe what happened and what help is needed. You can speak or type in Hindi, Hinglish, English, or Tamil.',
        timestamp: new Date(),
      },
    ]);
    this.tryGeolocation();
  }

  toggleMode(): void {
    const next = this.mode() === 'chat' ? 'form' : 'chat';
    if (next === 'form' && !this.pendingCard()) {
      this.pendingCard.set(this.blankCard());
    }
    this.mode.set(next);
  }

  setQuickChip(text: string): void {
    this.userInput.set(text);
    this.sendUserMessage();
  }

  selectFormType(incidentType: string): void {
    const current = this.pendingCard() ?? this.blankCard();
    this.pendingCard.set(this.withSummary({ ...current, incident_type: incidentType }));
  }

  updatePeople(value: string | number): void {
    const current = this.pendingCard() ?? this.blankCard();
    const count = Math.max(0, Math.min(99, Number(value) || 0));
    this.pendingCard.set(this.withSummary({ ...current, people_count: count }));
  }

  updatePlace(value: string): void {
    this.locationText.set(value);
    const current = this.pendingCard() ?? this.blankCard();
    this.pendingCard.set(this.withSummary({ ...current, place_text: value }));
  }

  toggleFormVulnerable(key: string): void {
    const current = this.pendingCard() ?? this.blankCard();
    const vulnerable = { ...EMPTY_VULNERABLE, ...current.vulnerable, [key]: !current.vulnerable?.[key] };
    this.pendingCard.set(this.withSummary({ ...current, vulnerable }));
  }

  onCardEdited(card: ConfirmationCardData): void {
    if (card.place_text) {
      this.locationText.set(card.place_text);
    }
    this.pendingCard.set(card);
  }

  toggleVoice(): void {
    const rec = !this.isRecording();
    this.isRecording.set(rec);
    if (rec) {
      setTimeout(() => {
        this.userInput.set('नमस्ते, हम वार्ड 7 में शिव मंदिर के पास फंसे हैं। पानी कमर तक आ गया है, घर में 4 लोग हैं, एक छोटा बच्चा और बुजुर्ग दादी हैं। कृपया जल्दी नाव भेजिए।');
        this.isRecording.set(false);
        this.sendUserMessage();
      }, 1200);
    }
  }

  sendUserMessage(): void {
    const text = this.userInput().trim();
    if (!text || this.isLoading()) {
      return;
    }

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: 'user',
      text,
      timestamp: new Date(),
    };

    this.chatMessages.update((msgs) => [...msgs, userMsg]);
    this.userInput.set('');
    this.isLoading.set(true);

    this.apiClient
      .sendChatTurn({
        session_id: this.sessionId(),
        message: text,
        scenario_id: 'flood',
        language: this.langService.currentLang(),
        location_pin: this.locationPin(),
      })
      .subscribe({
        next: (resp: ChatTurnResponse) => {
          this.isLoading.set(false);
          if (resp.confirmation_card) {
            this.pendingCard.set(resp.confirmation_card);
          }
          const assistantMsg: ChatMessage = {
            id: `ast_${Date.now()}`,
            role: 'assistant',
            text: resp.bot_message,
            timestamp: new Date(),
          };
          this.chatMessages.update((msgs) => [...msgs, assistantMsg]);
        },
        error: () => {
          this.isLoading.set(false);
          this.chatMessages.update((msgs) => [
            ...msgs,
            {
              id: `err_${Date.now()}`,
              role: 'assistant',
              text: 'Connection failed. Your message is saved locally and will auto-retry. Call 112 for urgent emergency.',
              timestamp: new Date(),
            },
          ]);
        },
      });
  }

  confirmAndSubmit(card: ConfirmationCardData): void {
    if (this.isLoading() || this.submittedResult()) {
      return;
    }

    const facts: StructuredReportFacts = {
      incident_type: card.incident_type,
      place_text: card.place_text,
      people_count: card.people_count,
      vulnerable: { ...card.vulnerable },
      hazard: card.hazard,
      summary: card.summary,
    };

    const payload: ReportSubmitRequest = {
      text: card.summary,
      channel: 'text',
      lang: this.langService.currentLang(),
      location_pin: this.locationPin(),
      scenario_id: 'flood',
      structured: facts,
    };

    if (!this.offlineSync.isOnline()) {
      const item = this.offlineSync.saveReportOffline(payload);
      this.chatMessages.update((msgs) => [
        ...msgs,
        {
          id: `off_${Date.now()}`,
          role: 'assistant',
          text: `Offline. Report queued on this phone (${item.idempotency_key}). It sends when the network returns. You can also use Send by SMS.`,
          timestamp: new Date(),
        },
      ]);
      return;
    }

    this.isLoading.set(true);
    this.apiClient.submitReport(payload).subscribe({
      next: (res: ReportSubmitResponse) => {
        this.isLoading.set(false);
        this.submittedResult.set(res);
        try {
          localStorage.setItem('rd_last_report_id', res.report_id);
          localStorage.setItem('rd_last_status_token', res.status_token);
        } catch {
          // ignore storage failures in private mode
        }
        this.router.navigate(['/status'], {
          queryParams: { id: res.report_id, token: res.status_token },
        });
      },
      error: () => {
        this.isLoading.set(false);
        const item = this.offlineSync.saveReportOffline(payload);
        this.chatMessages.update((msgs) => [
          ...msgs,
          {
            id: `err_${Date.now()}`,
            role: 'assistant',
            text: `Network error. Report queued locally (${item.idempotency_key}) and will auto-retry. Call 112 for an urgent emergency.`,
            timestamp: new Date(),
          },
        ]);
      },
    });
  }

  isVulnerableChecked(key: string): boolean {
    return !!this.pendingCard()?.vulnerable?.[key];
  }

  private blankCard(): ConfirmationCardData {
    return this.withSummary({
      incident_type: 'rescue',
      place_text: this.locationText(),
      people_count: 1,
      vulnerable: { ...EMPTY_VULNERABLE },
      hazard: 'unknown',
      summary: '',
      ready_to_submit: true,
    });
  }

  private withSummary(card: ConfirmationCardData): ConfirmationCardData {
    const count = card.people_count ?? 0;
    const vulns = Object.entries(card.vulnerable || {})
      .filter(([, on]) => on)
      .map(([key]) => key);
    const parts = [`${count} people needing ${card.incident_type}`];
    if (card.place_text) {
      parts.push(`at ${card.place_text}`);
    }
    if (vulns.length) {
      parts.push(`Vulnerable: ${vulns.join(', ')}`);
    }
    if (card.hazard && card.hazard !== 'unknown' && card.hazard !== 'none') {
      parts.push(`Hazard: ${card.hazard}`);
    }
    return { ...card, summary: parts.join(' | ') };
  }

  private tryGeolocation(): void {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        this.locationPin.set({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      },
      () => {
        // Riverbend centroid stays as the synthetic fallback.
      },
      { enableHighAccuracy: false, timeout: 2500, maximumAge: 60000 },
    );
  }
}
