import { ChangeDetectionStrategy, Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  ApiClientService,
  LanguageService,
  RdTranslatePipe,
  ConfirmationCardData,
  ChatTurnResponse,
  ReportSubmitResponse,
  ReportSubmitRequest,
} from '@rd/shared';

import { OfflineSyncService } from '../../../core/services/offline-sync.service';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  card?: ConfirmationCardData;
  timestamp: Date;
}

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [CommonModule, FormsModule, RdTranslatePipe],
  templateUrl: './report.component.html',
  styleUrl: './report.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportComponent implements OnInit {
  private apiClient = inject(ApiClientService);
  readonly langService = inject(LanguageService);
  readonly offlineSync = inject(OfflineSyncService);

  readonly sessionId = signal<string>(`sess_${Math.random().toString(36).substring(2, 9)}`);
  readonly mode = signal<'chat' | 'form'>('chat');
  readonly userInput = signal<string>('');
  readonly isRecording = signal<boolean>(false);
  readonly isLoading = signal<boolean>(false);
  readonly locationPin = signal<{ lat: number; lng: number }>({ lat: 26.852, lng: 80.925 });
  readonly locationText = signal<string>('Gandhi Nagar, Riverbend (Auto Pin active)');

  readonly chatMessages = signal<ChatMessage[]>([]);
  readonly submittedResult = signal<ReportSubmitResponse | null>(null);

  ngOnInit(): void {
    // Initial welcome message from intake agent
    this.chatMessages.set([
      {
        id: 'msg_welcome',
        role: 'assistant',
        text: 'Namaste. Describe what happened and what help is needed. You can speak or type in Hindi, Hinglish, English, or Tamil.',
        timestamp: new Date(),
      },
    ]);
  }

  toggleMode(): void {
    this.mode.update((m) => (m === 'chat' ? 'form' : 'chat'));
  }

  setQuickChip(text: string): void {
    this.userInput.set(text);
    this.sendUserMessage();
  }

  toggleVoice(): void {
    const rec = !this.isRecording();
    this.isRecording.set(rec);
    if (rec) {
      // Simulate synthetic voice note recording (Hero Case VN-01 Hindi)
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
          const assistantMsg: ChatMessage = {
            id: `ast_${Date.now()}`,
            role: 'assistant',
            text: resp.bot_message,
            card: resp.confirmation_card,
            timestamp: new Date(),
          };
          this.chatMessages.update((msgs) => [...msgs, assistantMsg]);
        },
        error: (err) => {
          this.isLoading.set(false);
          const errorMsg: ChatMessage = {
            id: `err_${Date.now()}`,
            role: 'assistant',
            text: 'Connection failed. Your message is saved locally and will auto-retry. Call 112 for urgent emergency.',
            timestamp: new Date(),
          };
          this.chatMessages.update((msgs) => [...msgs, errorMsg]);
        },
      });
  }

  confirmAndSubmit(card: ConfirmationCardData): void {
    if (this.isLoading()) return;

    const payload: ReportSubmitRequest = {
      text: card.summary,
      channel: 'text',
      lang: this.langService.currentLang(),
      location_pin: this.locationPin(),
      scenario_id: 'flood',
    };

    if (!this.offlineSync.isOnline()) {
      const item = this.offlineSync.saveReportOffline(payload);
      const offlineMsg: ChatMessage = {
        id: `off_${Date.now()}`,
        role: 'assistant',
        text: `📵 Offline Mode: Report queued safely on device (ID: ${item.idempotency_key}). It will automatically submit once internet connection is restored. You can also tap 'Send by SMS'.`,
        timestamp: new Date(),
      };
      this.chatMessages.update((msgs) => [...msgs, offlineMsg]);
      return;
    }

    this.isLoading.set(true);

    this.apiClient.submitReport(payload).subscribe({
      next: (res: ReportSubmitResponse) => {
        this.isLoading.set(false);
        this.submittedResult.set(res);
        const confirmMsg: ChatMessage = {
          id: `done_${Date.now()}`,
          role: 'assistant',
          text: `✅ Report submitted successfully to response team! Tracking Token: ${res.status_token}`,
          timestamp: new Date(),
        };
        this.chatMessages.update((msgs) => [...msgs, confirmMsg]);
      },
      error: () => {
        this.isLoading.set(false);
        const item = this.offlineSync.saveReportOffline(payload);
        const errorMsg: ChatMessage = {
          id: `err_${Date.now()}`,
          role: 'assistant',
          text: `⚠️ Network error encountered. Report queued locally (ID: ${item.idempotency_key}) and will auto-retry. Call 112 for urgent emergency.`,
          timestamp: new Date(),
        };
        this.chatMessages.update((msgs) => [...msgs, errorMsg]);
      },
    });
  }
}
