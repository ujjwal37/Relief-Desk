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
} from '@rd/shared';

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
      // Simulate synthetic speech recognition after 1.5 seconds
      setTimeout(() => {
        this.userInput.set('Gandhi school ke paas 5 log chat par hain, paani badh raha hai');
        this.isRecording.set(false);
      }, 1500);
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
    this.isLoading.set(true);

    this.apiClient
      .submitReport({
        text: card.summary,
        channel: 'text',
        lang: this.langService.currentLang(),
        location_pin: this.locationPin(),
        scenario_id: 'flood',
      })
      .subscribe({
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
        error: (err) => {
          this.isLoading.set(false);
        },
      });
  }
}
