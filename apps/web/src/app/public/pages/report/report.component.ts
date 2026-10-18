import { ChangeDetectionStrategy, Component, ElementRef, HostListener, OnDestroy, inject, signal, computed, OnInit, effect, viewChild, AfterViewChecked } from '@angular/core';
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
  getNextKuttanadDemoPoint,
  KUTTANAD_DEMO_POINTS,
} from '@rd/shared';

import { PhotoIntakeComponent } from '../../components/photo-intake/photo-intake.component';
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

const CHAT_TURN_TIMEOUT_MS = 45000;

export const REPORTER_FOLLOWUPS = false;

export interface GuidedChip {
  id: string;
  category: 'stranded' | 'breathing' | 'repeat' | 'hoax';
  text: string;
}

export const GUIDED_CHIPS: Record<'en' | 'hi' | 'ml' | 'manglish', GuidedChip[]> = {
  manglish: [
    {
      id: 'mg_stranded',
      category: 'stranded',
      text: 'Kainakary jettyde aduthu veettil vellam kayari, 3 per und, oru ammachi nadakkan pattilla',
    },
    {
      id: 'mg_breathing',
      category: 'breathing',
      text: 'Kainakary-il oraalkku swasam edukkaan pattunnilla, pettennu ambulance venam',
    },
    {
      id: 'mg_repeat',
      category: 'repeat',
      text: 'Kainakary boat jetty-il 4 aalukal trapped aanu, vellam koodunnu, vallam ayakkumo',
    },
    {
      id: 'mg_hoax',
      category: 'hoax',
      text: 'Dam ippol pottum ennu NASA warning, 10 min-il ellaavarum maaranam',
    },
  ],
  ml: [
    {
      id: 'ml_stranded',
      category: 'stranded',
      text: 'കൈനകരി പള്ളിയുടെ അടുത്ത് വീട്ടിൽ വെള്ളം കയറി, 4 പേർ കുടുങ്ങിയിട്ടുണ്ട്. ഒരു കുട്ടിയും പ്രായമായവരും ഉണ്ട്. ബോട്ട് വേണം.',
    },
    {
      id: 'ml_breathing',
      category: 'breathing',
      text: 'ശ്വാസം കിട്ടുന്നില്ല, കൈനകരി പള്ളിയുടെ അടുത്ത്, പെട്ടെന്ന് വരണം',
    },
    {
      id: 'ml_repeat',
      category: 'repeat',
      text: 'കൈനകരി ബോട്ട് ജെട്ടിയുടെ അടുത്ത് 4 പേർ കുടുങ്ങിക്കിടക്കുന്നു, വെള്ളം ഉയരുന്നു, നടക്കാൻ പറ്റാത്ത പ്രായമായ സ്ത്രീയുണ്ട്',
    },
    {
      id: 'ml_hoax',
      category: 'hoax',
      text: 'നാസ മുന്നറിയിപ്പ്: 10 മിനിറ്റിനുള്ളിൽ അണക്കെട്ട് പൊട്ടും, എല്ലാവരും ഉടൻ മാറുക',
    },
  ],
  hi: [
    {
      id: 'hi_stranded',
      category: 'stranded',
      text: 'वार्ड 7 में शिव मंदिर के पास 4 लोग फंसे हैं। पानी कमर तक है। एक बच्चा और बुजुर्ग हैं। नाव भेजिए।',
    },
    {
      id: 'hi_breathing',
      category: 'breathing',
      text: 'आपातकाल! एक व्यक्ति सांस नहीं ले पा रहा है, शिव मंदिर के पास। तुरंत एम्बुलेंस चाहिए।',
    },
    {
      id: 'hi_repeat',
      category: 'repeat',
      text: 'शिव मंदिर के पास 4 लोग छत पर फंसे हैं, पानी बढ़ रहा है, मदद चाहिए।',
    },
    {
      id: 'hi_hoax',
      category: 'hoax',
      text: 'नासा की चेतावनी: 10 मिनट में बांध टूटने वाला है, तुरंत खाली करें।',
    },
  ],
  en: [
    {
      id: 'en_stranded',
      category: 'stranded',
      text: 'Stranded family of 4 on the second floor, water rising rapidly near St. Mary Church, Kainakary. Send boat.',
    },
    {
      id: 'en_breathing',
      category: 'breathing',
      text: 'Emergency! Elderly person not breathing near Kainakary boat jetty. Need ambulance or doctor immediately.',
    },
    {
      id: 'en_repeat',
      category: 'repeat',
      text: 'Four people stuck near Kainakary boat jetty, water rising, elderly woman cannot walk',
    },
    {
      id: 'en_hoax',
      category: 'hoax',
      text: 'NASA says the dam will burst in 10 minutes, everyone evacuate, forward this',
    },
  ],
};

interface SpeechRec {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript?: string }>> }) => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, RdTranslatePipe, ConfirmationCardComponent, CallPillComponent, SettingsButtonComponent, PhotoIntakeComponent],
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
  /** Sample buttons are demo tools: shown with ?demo=1 or after 'Try the desk', never to real reporters. */
  readonly demoTools = typeof window !== 'undefined' && (new URLSearchParams(window.location.search).has('demo') || window.localStorage?.getItem('rd.demo') === '1');
  readonly userInput = signal<string>('');
  readonly isRecording = signal<boolean>(false);
  readonly voiceOpen = signal<boolean>(false);
  readonly transcript = signal<string>('');
  readonly slow = signal<boolean>(false);
  readonly reviewOpen = signal<boolean>(false);
  readonly photoUsed = signal(false);
  readonly sampleBusy = signal(false);
  readonly kbOffset = signal<number>(0);
  private slowTimer: ReturnType<typeof setTimeout> | null = null;
  private voiceTimers: ReturnType<typeof setTimeout>[] = [];
  private recognition: { stop: () => void } | null = null;
  private threadEnd = viewChild<ElementRef<HTMLElement>>('threadEnd');
  private lastCount = 0;
  private queuedLocally = false;

  readonly suggestions = [
    { key: 'landing.chipFlood', text: 'Flood or water rising' },
    { key: 'landing.chipHurt', text: 'Someone hurt or sick' },
    { key: 'landing.chipOther', text: 'Something else' },
  ];
  readonly isLoading = signal<boolean>(false);
  readonly locationPin = signal<{ lat: number; lng: number } | null>(null);
  readonly locationText = signal<string>(AUTO_PLACE);

  readonly chatMessages = signal<ChatMessage[]>([]);
  readonly pendingCard = signal<ConfirmationCardData | null>(null);
  readonly lifeCard = signal(false);
  readonly submittedResult = signal<ReportSubmitResponse | null>(null);
  readonly scenarioId = this.scenarioState.activeId;
  readonly tiles = signal<ScenarioTile[]>([
    { id: 'trapped_water', label_en: 'Trapped in Water', label_hi: 'पानी में फंसे हैं', incident_type: 'rescue', icon: 'water' },
    { id: 'medical_urgent', label_en: 'Medical Assistance', label_hi: 'चिकित्सा सहायता', incident_type: 'medical', icon: 'medkit' },
    { id: 'food_water_needed', label_en: 'Food & Drinking Water', label_hi: 'भोजन और पेयजल', incident_type: 'food', icon: 'nutrition' },
    { id: 'shelter_needed', label_en: 'Need Shelter', label_hi: 'आश्रय चाहिए', incident_type: 'shelter', icon: 'home' },
  ]);

  readonly selectedChipLang = signal<'manglish' | 'ml' | 'hi' | 'en'>('manglish');
  readonly guidedChips = computed(() => GUIDED_CHIPS[this.selectedChipLang()]);

  readonly isSharingGps = signal(false);
  readonly gpsShared = signal(false);
  readonly locationAccuracy = signal<number | null>(null);
  readonly locationSource = signal<string | null>(null);
  readonly isDemoLocation = signal(false);
  /** Name of the demo point in use, shown on the location line. */
  readonly demoPlaceName = signal<string | null>(null);
  /** True while the location is the automatic default, not one the reporter chose. */
  private autoLocation = false;

  readonly attachedPhoto = signal<string | null>(null);
  readonly isCompressingPhoto = signal(false);

  readonly isOfflineQueued = signal(false);
  draftIdempotencyKey = `idemp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

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
    this.applyDefaultLocation();
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
    this.closeVoice();
    if (this.slowTimer) clearTimeout(this.slowTimer);
    if (this.autoRetryTimer) {
      clearTimeout(this.autoRetryTimer);
      this.autoRetryTimer = null;
    }
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
    if (!text || text === AUTO_PLACE) return this.demoPlaceName() || this.langService.translate('report.autoPlace');
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

  /** BCP-47 locale for the mic and the text box. English and Hindi are the primary pair. */
  /** Speech language picked in the voice sheet (Malayalam reports work without a Malayalam UI). */
  readonly voiceLocale = signal<string | null>(null);
  pickVoiceLocale(locale: string): void {
    this.voiceLocale.set(locale);
    if (this.recognition) {
      try { this.recognition.stop(); } catch { /* ignore */ }
      this.recognition = null;
      this.transcript.set('');
      if (!this.startRecognition()) this.playSampleUtterance();
    }
  }

  inputLocale(): string {
    const picked = this.voiceLocale();
    if (picked) return picked;
    const lang = this.langService.currentLang();
    if (lang === 'hi' || lang === 'hinglish') return 'hi-IN';
    if (lang === 'ml') return 'ml-IN';
    return 'en-IN';
  }

  /** Canned line used when the browser has no speech recogniser. Matches the chosen language. */
  sampleUtterance(): string {
    const lang = this.langService.currentLang();
    if (lang === 'hi') {
      return 'वार्ड 7 में शिव मंदिर के पास 4 लोग फंसे हैं। पानी कमर तक है। एक बच्चा और बुजुर्ग हैं। नाव भेजिए।';
    }
    if (lang === 'hinglish') {
      return 'Ward 7 Shiv Mandir ke paas 4 log fanse hain, paani kamar tak hai, ek bachcha hai, boat bhejo.';
    }
    if (lang === 'ml') {
      return 'വാർഡ് 7 ശിവ ക്ഷേത്രത്തിന് സമീപം 4 പേർ കുടുങ്ങി. വെള്ളം ഉയരുന്നു. ബോട്ട് വേണം.';
    }
    return '4 people are trapped near Shiva Temple in Ward 7. The water is at waist level. There is a child and an elderly person. Please send a boat.';
  }

  langLabel(): string {
    const t = this.transcript();
    if (/[\u0900-\u097F]/.test(t)) return 'हिंदी';
    if (/[\u0D00-\u0D7F]/.test(t)) return 'മലയാളം';
    return SUPPORTED_LANGUAGES.find((l) => l.code === this.langService.currentLang())?.label || 'English';
  }

  closeVoice(): void {
    this.voiceTimers.forEach(clearTimeout);
    this.voiceTimers = [];
    try {
      this.recognition?.stop();
    } catch {
      // The recogniser may already have stopped.
    }
    this.recognition = null;
    this.voiceOpen.set(false);
    this.isRecording.set(false);
  }

  typeInstead(): void {
    this.userInput.set(this.transcript());
    this.closeVoice();
  }

  prefillExample(kind: 'manglish' | 'not_breathing' | 'reworded'): void {
    const examples: Record<string, string> = {
      manglish: 'Kainakary-il vellam keri, veedinte mukalil 4 aalukal trapped aanu, oru kuttiyum undu. Vallam venam.',
      not_breathing: 'കൈനക്കരിയിൽ ഒരാൾക്ക് ശ്വാസമെടുക്കാൻ പറ്റുന്നില്ല. വേഗം ആംബുലൻസ് അല്ലെങ്കിൽ ഡോക്ടർ വേണം.',
      reworded: 'Champakulam church-nte aduthu vellam koodi, aalukal ottappettu, sahayam ethikkumo.',
    };
    this.userInput.set(examples[kind] || '');
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
      locationPin: this.locationPin() ?? undefined,
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
    if (value !== this.placeLabel()) this.clearAutoLocation();
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
      if (card.place_text !== this.placeLabel()) this.clearAutoLocation();
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
    if (this.startRecognition()) return;
    this.playSampleUtterance();
  }

  private startRecognition(): boolean {
    const host = window as Window & {
      SpeechRecognition?: new () => SpeechRec;
      webkitSpeechRecognition?: new () => SpeechRec;
    };
    const Ctor = host.SpeechRecognition || host.webkitSpeechRecognition;
    if (!Ctor) return false;
    try {
      const rec = new Ctor();
      rec.lang = this.inputLocale();
      rec.interimResults = true;
      rec.continuous = false;
      rec.onresult = (event) => {
        let text = '';
        for (let i = 0; i < event.results.length; i++) {
          text += event.results[i][0]?.transcript || '';
        }
        this.transcript.set(text.trim());
      };
      rec.onerror = () => this.playSampleUtterance();
      rec.start();
      this.recognition = rec;
      return true;
    } catch {
      this.recognition = null;
      return false;
    }
  }

  private playSampleUtterance(): void {
    const words = this.sampleUtterance().split(' ');
    words.forEach((_, i) => {
      this.voiceTimers.push(setTimeout(() => this.transcript.set(words.slice(0, i + 1).join(' ')), 350 + i * 180));
    });
  }

  sendSample(kind: 'hindi' | 'voice' | 'photo' | 'duplicate'): void {
    if (this.sampleBusy() || this.isLoading()) return;
    this.sampleBusy.set(true);
    this.apiClient.submitSampleReport(kind).subscribe({
      next: (res: ReportSubmitResponse) => {
        this.sampleBusy.set(false);
        this.myRequests.add(res.report_id, res.status_token, kind);
        announceReport(res.report_id, res.request_id);
        this.router.navigate(['/status'], {
          queryParams: { id: res.report_id, token: res.status_token, new: 1 },
        });
      },
      error: () => this.sampleBusy.set(false),
    });
  }

  usePhotoObservation(text: string): void {
    this.userInput.set([this.userInput().trim(), text].filter(Boolean).join('\n'));
    this.pendingCard.set(null);
    this.reviewOpen.set(false);
    this.photoUsed.set(true);
  }

  pickGuidedChip(text: string): void {
    this.userInput.set(text);
  }

  shareGpsLocation(): void {
    const pt = getNextKuttanadDemoPoint();
    this.autoLocation = false;
    this.demoPlaceName.set(pt.name);
    this.locationPin.set({ lat: pt.lat, lng: pt.lng });
    this.locationAccuracy.set(25);
    this.locationSource.set('demo_pin');
    this.gpsShared.set(true);
    this.isDemoLocation.set(true);
  }

  setDemoLocation(): void {
    const pt = getNextKuttanadDemoPoint();
    this.autoLocation = false;
    this.demoPlaceName.set(pt.name);
    this.locationPin.set({ lat: pt.lat, lng: pt.lng });
    this.locationAccuracy.set(25);
    this.locationSource.set('demo_pin');
    this.gpsShared.set(true);
    this.isDemoLocation.set(true);
  }

  /** Kerala-only pilot: a report with no chosen location gets a random fixed Kuttanad demo point, as with Demo location. */
  private applyDefaultLocation(): void {
    if (this.locationPin() || (this.locationText() && this.locationText() !== AUTO_PLACE)) return;
    const pt = KUTTANAD_DEMO_POINTS[Math.floor(Math.random() * KUTTANAD_DEMO_POINTS.length)];
    this.locationPin.set({ lat: pt.lat, lng: pt.lng });
    this.locationAccuracy.set(25);
    this.locationSource.set('demo_pin');
    this.gpsShared.set(true);
    this.isDemoLocation.set(true);
    this.demoPlaceName.set(pt.name);
    this.autoLocation = true;
  }

  /** The reporter typed a place: drop the automatic pin so their place is used. */
  private clearAutoLocation(): void {
    if (!this.autoLocation) return;
    this.autoLocation = false;
    this.locationPin.set(null);
    this.locationAccuracy.set(null);
    this.locationSource.set(null);
    this.gpsShared.set(false);
    this.isDemoLocation.set(false);
    this.demoPlaceName.set(null);
  }

  async onPhotoSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    this.isCompressingPhoto.set(true);
    try {
      const b64 = await this.compressImage(file);
      this.attachedPhoto.set(b64);
    } catch {
      // ignore
    } finally {
      this.isCompressingPhoto.set(false);
      input.value = '';
    }
  }

  removePhoto(): void {
    this.attachedPhoto.set(null);
  }

  async compressImage(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          let { width, height } = img;
          const maxDim = 1280;
          if (width > maxDim || height > maxDim) {
            if (width > height) {
              height = Math.round((height * maxDim) / width);
              width = maxDim;
            } else {
              width = Math.round((width * maxDim) / height);
              height = maxDim;
            }
          }
          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            resolve(e.target?.result as string);
            return;
          }
          ctx.drawImage(img, 0, 0, width, height);
          resolve(canvas.toDataURL('image/jpeg', 0.8));
        };
        img.onerror = reject;
        img.src = e.target?.result as string;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  private autoRetryTimer: ReturnType<typeof setTimeout> | null = null;

  retryOffline(): void {
    if (this.autoRetryTimer) {
      clearTimeout(this.autoRetryTimer);
      this.autoRetryTimer = null;
    }
    this.sendReport();
  }

  @HostListener('window:online')
  onWindowOnline(): void {
    if (this.isOfflineQueued()) {
      if (this.autoRetryTimer) clearTimeout(this.autoRetryTimer);
      this.autoRetryTimer = setTimeout(() => {
        if (this.isOfflineQueued()) {
          this.sendReport();
        }
      }, 2000);
    }
  }

  sendReport(): void {
    const text = this.userInput().trim();
    const photo = this.attachedPhoto();
    if ((!text && !photo) || this.isLoading()) {
      return;
    }

    this.applyDefaultLocation();
    if (REPORTER_FOLLOWUPS) {
      this.sendOldFollowUp();
      return;
    }

    const payload: ReportSubmitRequest = {
      text,
      raw_text: text,
      channel: 'text',
      lang: this.langService.currentLang(),
      location_pin: this.locationPin() ?? undefined,
      location_accuracy: this.locationAccuracy() ?? undefined,
      location_source: this.locationSource() ?? undefined,
      photo_base64: photo ?? undefined,
      scenario_id: this.scenarioId(),
      idempotency_key: this.draftIdempotencyKey,
    };

    if (!this.onlineNow()) {
      this.offlineSync.saveReportOffline(payload);
      this.isOfflineQueued.set(true);
      return;
    }

    this.isLoading.set(true);
    this.apiClient.submitReport(payload).subscribe({
      next: (res: ReportSubmitResponse) => {
        this.isLoading.set(false);
        this.isOfflineQueued.set(false);
        if (this.autoRetryTimer) {
          clearTimeout(this.autoRetryTimer);
          this.autoRetryTimer = null;
        }
        if (res.is_case === false) {
          // Greeting or gibberish gate: show assistant response in thread, no case
          if (text) {
            this.chatMessages.update((msgs) => [
              ...msgs,
              { id: `usr_${Date.now()}`, role: 'user', text, timestamp: new Date() },
            ]);
          }
          if (res.gate_reply) {
            this.chatMessages.update((msgs) => [
              ...msgs,
              { id: `ast_${Date.now()}`, role: 'assistant', text: res.gate_reply!, timestamp: new Date() },
            ]);
          }
          this.userInput.set('');
          this.attachedPhoto.set(null);
          this.draftIdempotencyKey = `idemp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
          return;
        }

        this.submittedResult.set(res);
        this.myRequests.add(res.report_id, res.status_token, 'rescue');
        announceReport(res.report_id, res.request_id, res.public_code);
        this.router.navigate(['/status'], {
          queryParams: { id: res.report_id, token: res.status_token, new: 1 },
        });
      },
      error: () => {
        this.isLoading.set(false);
        this.offlineSync.saveReportOffline(payload);
        this.isOfflineQueued.set(true);
      },
    });
  }

  sendUserMessage(): void {
    this.sendReport();
  }

  private sendOldFollowUp(): void {
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
        location_pin: this.locationPin() ?? undefined,
      })
      .pipe(timeout(CHAT_TURN_TIMEOUT_MS))
      .subscribe({
        next: (resp: ChatTurnResponse) => {
          this.isLoading.set(false);
          this.slow.set(false);
          if (this.slowTimer) clearTimeout(this.slowTimer);
          if (resp.confirmation_card) {
            this.pendingCard.set(resp.confirmation_card);
            if (resp.confirmation_card.life_threat) this.lifeCard.set(true);
            else this.reviewOpen.set(true);
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
    // Slow reply: the bubble says the reporter can send as is, so the card stays sendable.
    if ((this.isLoading() && !this.slow()) || this.submittedResult()) {
      return;
    }

    this.applyDefaultLocation();
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

    const words = [this.citizenWords(), this.photoUsed() ? this.userInput().trim() : ''].filter(Boolean).join('\n') || card.summary;
    // The desk quotes the reporter's first sentence; chat answers travel separately.
    const said = this.chatMessages().filter((msg) => msg.role === 'user').map((msg) => msg.text);
    const original = card.original_text || said[0] || words;
    const answers = card.answers ?? said.slice(1);
    const payload: ReportSubmitRequest = {
      text: words,
      raw_text: this.photoUsed() ? words : original,
      chat_answers: this.photoUsed() ? [] : answers,
      channel: this.mode() === 'form' ? 'form' : 'text',
      lang: this.langService.currentLang(),
      location_pin: this.locationPin() ?? undefined,
      location_accuracy: this.locationAccuracy() ?? undefined,
      location_source: this.locationSource() ?? undefined,
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
        this.myRequests.add(res.report_id, res.status_token, card.incident_type);
        announceReport(res.report_id, res.request_id, res.public_code);
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
    // Unknown stays unknown: a missing count is 'not stated', never 0.
    const count = card.people_count ?? this.langService.translate('people.notStated');
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
      location_pin: this.locationPin() ?? undefined,
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
        // The automatic Kuttanad point stays; only the reporter's own choice replaces it.
        if (this.autoLocation) return;
        this.locationPin.set({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      },
      () => {
        // Alappuzha stays as the synthetic fallback when the phone has no GPS fix.
      },
      { enableHighAccuracy: false, timeout: 2500, maximumAge: 60000 },
    );
  }
}
