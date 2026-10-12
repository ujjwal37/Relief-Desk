import { ChangeDetectionStrategy, Component, ElementRef, HostListener, OnDestroy, inject, signal, OnInit, effect, viewChild, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { timeout, TimeoutError } from 'rxjs';
import { Router, RouterLink } from '@angular/router';
import {
  ApiClientService,
  LanguageService,
  RdTranslatePipe,
  ConfirmationCardData,
  CallPillComponent,
  SettingsButtonComponent,
  SUPPORTED_LANGUAGES,
  ChatTurnResponse,
  ReportSubmitResponse,
  ReportSubmitRequest,
  StructuredReportFacts,
  ScenarioTile,
  canonicalRequestJson,
} from '@rd/shared';

import { announceReport } from '../../../core/live-report';
import { MyRequestsService } from '../../../core/services/my-requests.service';
import { OfflineSyncService } from '../../../core/services/offline-sync.service';
import { ScenarioService } from '../../../core/services/scenario.service';
import { ConfirmationCardComponent } from '../../components/confirmation-card/confirmation-card.component';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  quick?: string[];
}

const AUTO_PLACE = '__auto__';

const EMPTY_VULNERABLE: Record<string, boolean> = {
  child: false,
  elderly: false,
  disabled: false,
  pregnant: false,
  medical_need: false,
};

/** A chat turn that takes longer than this falls back to the form. */
const CHAT_TURN_TIMEOUT_MS = 15000;

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, RdTranslatePipe, ConfirmationCardComponent, CallPillComponent, SettingsButtonComponent],
  templateUrl: './report.component.html',
  styleUrl: './report.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportComponent implements OnInit, OnDestroy, AfterViewChecked {
  private apiClient = inject(ApiClientService);
  private router = inject(Router);
  readonly langService = inject(LanguageService);
  readonly scenarioState = inject(ScenarioService);
  readonly offlineSync = inject(OfflineSyncService);
  private readonly myRequests = inject(MyRequestsService);

  readonly sessionId = signal<string>(`sess_${Math.random().toString(36).substring(2, 9)}`);
  readonly mode = signal<'chat' | 'form'>('chat');
  readonly userInput = signal<string>('');
  readonly isRecording = signal<boolean>(false);
  readonly voiceOpen = signal<boolean>(false);
  readonly transcript = signal<string>('');
  readonly slow = signal<boolean>(false);
  readonly reviewOpen = signal<boolean>(false);
  readonly kbOffset = signal<number>(0);
  private slowTimer: ReturnType<typeof setTimeout> | null = null;
  private voiceTimers: ReturnType<typeof setTimeout>[] = [];
  private threadEnd = viewChild<ElementRef<HTMLElement>>('threadEnd');
  private lastCount = 0;
  private queuedLocally = false;

  readonly suggestions = [
    { key: 'landing.chipFlood', text: 'Flood or water rising' },
    { key: 'landing.chipAnimal', text: 'Animal attack or bite' },
    { key: 'landing.chipHurt', text: 'Someone hurt or sick' },
    { key: 'landing.chipOther', text: 'Something else' },
  ];
  readonly isLoading = signal<boolean>(false);
  readonly locationPin = signal<{ lat: number; lng: number }>({ lat: 9.498, lng: 76.339 });
  readonly locationText = signal<string>(AUTO_PLACE);

  readonly chatMessages = signal<ChatMessage[]>([]);
  readonly pendingCard = signal<ConfirmationCardData | null>(null);
  readonly submittedResult = signal<ReportSubmitResponse | null>(null);
  readonly scenarioId = this.scenarioState.activeId;
  readonly tiles = signal<ScenarioTile[]>([
    { id: 'trapped_water', label_en: 'Trapped in Water', label_hi: 'पानी में फंसे हैं', incident_type: 'rescue', icon: 'water' },
    { id: 'medical_urgent', label_en: 'Medical Assistance', label_hi: 'चिकित्सा सहायता', incident_type: 'medical', icon: 'medkit' },
    { id: 'food_water_needed', label_en: 'Food & Drinking Water', label_hi: 'भोजन और पेयजल', incident_type: 'food', icon: 'nutrition' },
    { id: 'shelter_needed', label_en: 'Need Shelter', label_hi: 'आश्रय चाहिए', incident_type: 'shelter', icon: 'home' },
  ]);

  constructor() {
    effect(() => {
      const read = this.offlineSync.lastSynced;
      if (typeof read !== 'function') return;
      const synced = read();
      const reportId = synced?.response?.report_id;
      if (!this.queuedLocally || !reportId) return;
      this.queuedLocally = false;
      this.router.navigate(['/status'], {
        queryParams: { id: reportId, token: synced.response.status_token, new: 1 },
      });
    });
    effect(() => {
      const id = this.scenarioState.activeId();
      this.apiClient.getScenario(id).subscribe({
        next: (scenario) => {
          if (scenario?.tiles?.length) {
            this.tiles.set(scenario.tiles);
          }
        },
        error: () => {
          // Keep the last tiles so the form still works offline.
        },
      });
    });
  }

  ngOnInit(): void {
    this.scenarioState.ensureLoaded();
    this.chatMessages.set([]);
    this.tryGeolocation();
    if (typeof window !== 'undefined' && window.visualViewport) {
      window.visualViewport.addEventListener('resize', this.onViewport);
    }
  }

  private onViewport = (): void => {
    const vv = window.visualViewport;
    if (vv) this.kbOffset.set(Math.max(0, window.innerHeight - vv.height - vv.offsetTop));
  };

  ngOnDestroy(): void {
    window.visualViewport?.removeEventListener('resize', this.onViewport);
    this.voiceTimers.forEach(clearTimeout);
    if (this.slowTimer) clearTimeout(this.slowTimer);
  }

  ngAfterViewChecked(): void {
    const n = this.chatMessages().length + (this.isLoading() ? 1 : 0);
    if (n !== this.lastCount) {
      this.lastCount = n;
      this.threadEnd()?.nativeElement.scrollIntoView?.({ block: 'end' });
    }
  }

  pickSuggestion(key: string): void {
    this.userInput.set(this.langService.translate(key));
    this.sendUserMessage();
  }

  placeLabel(): string {
    const text = this.locationText();
    if (!text || text === AUTO_PLACE) return this.langService.translate('report.autoPlace');
    return text;
  }

  useQuick(msgId: string, text: string): void {
    this.chatMessages.update((m) => m.map((x) => (x.id === msgId ? { ...x, quick: undefined } : x)));
    const spoken: Record<string, string> = {
      '1-2': 'report.said12',
      '3-5': 'report.said35',
      '6+': 'report.said6',
      '?': 'report.saidNot',
      child: 'report.saidChild',
      elderly: 'report.saidElderly',
      sick: 'report.saidSick',
      none: 'report.saidNone',
    };
    const key = spoken[text];
    this.userInput.set(key ? this.langService.translate(key) : text);
    this.sendUserMessage();
  }

  private quickFor(resp: ChatTurnResponse): string[] | undefined {
    if (resp.confirmation_card) return undefined;
    const first = (resp.missing_fields || [])[0];
    if (first === 'people_count') return ['1-2', '3-5', '6+', '?'];
    if (first === 'vulnerable') return ['child', 'elderly', 'sick', 'none'];
    return undefined;
  }

  quickLabelKey(text: string): string {
    return ({ '1-2': 'report.qr12', '3-5': 'report.qr35', '6+': 'report.qr6', '?': 'report.qrNot', child: 'confirm.child', elderly: 'confirm.elderly', sick: 'confirm.medical', none: 'report.qrNone' } as Record<string, string>)[text] || text;
  }

  onEnter(e: Event): void {
    if ((e as KeyboardEvent).shiftKey) return;
    e.preventDefault();
    this.sendUserMessage();
  }

  autoGrow(el: HTMLTextAreaElement): void {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 5 * 24 + 24) + 'px';
  }

  langLabel(): string {
    const t = this.transcript();
    if (/[\u0900-\u097F]/.test(t)) return 'हिन्दी';
    if (/[\u0B80-\u0BFF]/.test(t)) return 'தமிழ்';
    return SUPPORTED_LANGUAGES.find((l) => l.code === this.langService.currentLang())?.label || 'English';
  }

  closeVoice(): void {
    this.voiceTimers.forEach(clearTimeout);
    this.voiceTimers = [];
    this.voiceOpen.set(false);
    this.isRecording.set(false);
  }

  typeInstead(): void {
    this.userInput.set(this.transcript());
    this.closeVoice();
  }

  finishVoice(): void {
    const text = this.transcript();
    this.closeVoice();
    if (text) {
      this.userInput.set(text);
      this.sendUserMessage();
    }
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.voiceOpen()) this.closeVoice();
  }

  tileLabel(tile: ScenarioTile): string {
    const lang = this.langService.currentLang();
    if (lang === 'hi' && tile.label_hi) {
      return tile.label_hi;
    }
    return tile.label_en;
  }

  tileIcon(icon: string): string {
    const icons: Record<string, string> = {
      water: '🌊',
      medkit: '🚑',
      nutrition: '🍲',
      home: '🏠',
    };
    return icons[icon] || '•';
  }

  requestJson(card: ConfirmationCardData): string {
    return canonicalRequestJson({
      card,
      lang: this.langService.currentLang(),
      locationPin: this.locationPin(),
      scenarioId: this.scenarioId(),
    });
  }

  toggleMode(): void {
    const next = this.mode() === 'chat' ? 'form' : 'chat';
    if (next === 'form') {
      this.openForm();
      return;
    }
    this.mode.set('chat');
  }

  openForm(): void {
    if (!this.pendingCard()) {
      this.pendingCard.set(this.blankCard());
    }
    this.mode.set('form');
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
    if (this.voiceOpen()) {
      this.closeVoice();
      return;
    }
    this.voiceOpen.set(true);
    this.isRecording.set(true);
    this.transcript.set('');
    // Simulated live transcript (existing demo behaviour), revealed word by word.
    const full = 'नमस्ते, हम वार्ड 7 में शिव मंदिर के पास फंसे हैं। पानी कमर तक आ गया है, घर में 4 लोग हैं, एक छोटा बच्चा और बुजुर्ग दादी हैं। कृपया जल्दी नाव भेजिए।';
    const words = full.split(' ');
    words.forEach((_, i) => {
      this.voiceTimers.push(setTimeout(() => this.transcript.set(words.slice(0, i + 1).join(' ')), 350 + i * 180));
    });
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

    if (!this.onlineNow()) {
      this.queueCitizenText(text);
      return;
    }

    this.isLoading.set(true);
    this.slow.set(false);
    if (this.slowTimer) clearTimeout(this.slowTimer);
    this.slowTimer = setTimeout(() => this.slow.set(true), 6000);

    this.apiClient
      .sendChatTurn({
        session_id: this.sessionId(),
        message: text,
        scenario_id: this.scenarioId(),
        language: this.langService.currentLang(),
        location_pin: this.locationPin(),
      })
      .pipe(timeout(CHAT_TURN_TIMEOUT_MS))
      .subscribe({
        next: (resp: ChatTurnResponse) => {
          this.isLoading.set(false);
          this.slow.set(false);
          if (this.slowTimer) clearTimeout(this.slowTimer);
          if (resp.confirmation_card) {
            this.pendingCard.set(resp.confirmation_card);
            this.reviewOpen.set(true);
          }
          const assistantMsg: ChatMessage = {
            id: `ast_${Date.now()}`,
            role: 'assistant',
            text: resp.bot_message,
            timestamp: new Date(),
            quick: this.quickFor(resp),
          };
          this.chatMessages.update((msgs) => [...msgs, assistantMsg]);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.slow.set(false);
          if (this.slowTimer) clearTimeout(this.slowTimer);
          if (err instanceof TimeoutError) {
            // Never leave the citizen on a spinner: offer the form with what we have.
            this.chatMessages.update((msgs) => [
              ...msgs,
              { id: `ast_${Date.now()}`, role: 'assistant', text: this.langService.translate('report.takingLonger'), timestamp: new Date() },
            ]);
            this.openForm();
            return;
          }
          this.queueCitizenText(text);
        },
      });
  }

  confirmAndSubmit(card: ConfirmationCardData): void {
    if (this.isLoading() || this.submittedResult()) {
      return;
    }

    const canonical = JSON.parse(this.requestJson(card)) as {
      vulnerable: Record<string, boolean>;
    };
    const facts: StructuredReportFacts = {
      incident_type: card.incident_type,
      place_text: card.place_text,
      people_count: card.people_count,
      vulnerable: { ...canonical.vulnerable },
      hazard: card.hazard,
      summary: card.summary,
    };

    const words = this.citizenWords() || card.summary;
    const payload: ReportSubmitRequest = {
      text: words,
      raw_text: words,
      channel: this.mode() === 'form' ? 'form' : 'text',
      lang: this.langService.currentLang(),
      location_pin: this.locationPin(),
      scenario_id: this.scenarioId(),
      structured: facts,
    };

    if (!this.onlineNow()) {
      this.offlineSync.saveReportOffline(payload);
      this.noteQueued();
      return;
    }

    this.isLoading.set(true);
    this.apiClient.submitReport(payload).subscribe({
      next: (res: ReportSubmitResponse) => {
        this.isLoading.set(false);
        this.submittedResult.set(res);
        this.myRequests.add(res.report_id, res.status_token);
        announceReport(res.report_id, res.request_id);
        this.router.navigate(['/status'], {
          queryParams: { id: res.report_id, token: res.status_token, new: 1 },
        });
      },
      error: () => {
        this.isLoading.set(false);
        this.offlineSync.saveReportOffline(payload);
        this.noteQueued();
      },
    });
  }

  isVulnerableChecked(key: string): boolean {
    return !!this.pendingCard()?.vulnerable?.[key];
  }

  private blankCard(): ConfirmationCardData {
    return this.withSummary({
      incident_type: 'rescue',
      place_text: this.placeLabel(),
      people_count: 1,
      vulnerable: { ...EMPTY_VULNERABLE },
      hazard: 'unknown',
      summary: '',
      ready_to_submit: true,
    });
  }

  private withSummary(card: ConfirmationCardData): ConfirmationCardData {
    const count = card.people_count ?? 0;
    const type = this.langService.translate(`incidentType.${card.incident_type}`);
    const vulns = Object.entries(card.vulnerable || {})
      .filter(([, on]) => on)
      .map(([key]) => this.langService.translate(key === 'medical_need' ? 'confirm.medical' : `confirm.${key}`));
    const parts = [`${count} · ${type}`];
    if (card.place_text) {
      parts.push(card.place_text);
    }
    if (vulns.length) {
      parts.push(vulns.join(', '));
    }
    if (card.hazard && card.hazard !== 'unknown' && card.hazard !== 'none') {
      parts.push(this.langService.translate(`hazardKind.${card.hazard}`));
    }
    return { ...card, summary: parts.join(' · ') };
  }

  citizenWords(): string {
    return this.chatMessages().filter((msg) => msg.role === 'user').map((msg) => msg.text).join('\n');
  }

  private onlineNow(): boolean {
    const reader = this.offlineSync.readOnline;
    if (typeof reader === 'function') return reader.call(this.offlineSync);
    return this.offlineSync.isOnline();
  }

  /** Store the citizen's words so a failed or offline send is retried, not dropped. */
  private queueCitizenText(text: string): void {
    this.offlineSync.saveReportOffline({
      text,
      raw_text: text,
      channel: 'text',
      lang: this.langService.currentLang(),
      location_pin: this.locationPin(),
      scenario_id: this.scenarioId(),
    });
    this.noteQueued();
  }

  private noteQueued(): void {
    this.queuedLocally = true;
    this.chatMessages.update((msgs) => [
      ...msgs,
      {
        id: `off_${Date.now()}`,
        role: 'assistant',
        text: this.langService.translate('report.savedPending'),
        timestamp: new Date(),
      },
    ]);
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
        // Alappuzha stays as the synthetic fallback when the phone has no GPS fix.
      },
      { enableHighAccuracy: false, timeout: 2500, maximumAge: 60000 },
    );
  }
}
