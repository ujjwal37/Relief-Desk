import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { CoordinatorCommandComponent } from './coordinator-command.component';
import { LanguageService, ApiClientService, StoredRequest, MatchProposal, StoredResource, UrgencyWeights } from '@rd/shared';
import { MapProviderComponent } from '../../../core/maps/map-provider.component';

describe('CoordinatorCommandComponent', () => {
  let component: CoordinatorCommandComponent;
  let fixture: ComponentFixture<CoordinatorCommandComponent>;
  let apiClientSpy: jasmine.SpyObj<ApiClientService>;

  const mockRequests: StoredRequest[] = [
    {
      id: 'INC-001',
      type: 'rescue',
      place_text: 'Ward 7 · Gandhi School lane',
      ward_id: 'ward_7',
      lat: 26.852,
      lng: 80.925,
      people_count: 5,
      vulnerable: {
        child: true,
        elderly: true,
        disabled: false,
        pregnant: false,
        medical_need: false,
      },
      hazard: 'water_rising',
      urgency_score: 94,
      urgency_reason: '5 people with child and elderly',
      status: 'new',
      raw_text: 'Gandhi school ke paas ghar mein paani aa gaya. Ab 5 log hain, 1 bachcha aur dadi bimaar.',
      ai_translation: 'Water has entered the house near Gandhi school. Now 5 people, 1 child and a sick grandmother.',
      merged_count: 3,
      update_count: 1,
      cluster_id: 'cl_seed_INC-001',
      confidence: {
        type: 0.96,
        place: 0.88,
        people: 0.82,
        vulnerable: 0.91,
        urgency: 0.94,
      },
    },
    {
      id: 'INC-002',
      type: 'medical',
      place_text: 'Ward 4 · Canal Road',
      ward_id: 'ward_4',
      lat: 26.845,
      lng: 80.932,
      people_count: 3,
      vulnerable: {
        child: false,
        elderly: true,
        disabled: false,
        pregnant: false,
        medical_need: true,
      },
      hazard: 'stranded',
      urgency_score: 88,
      urgency_reason: 'Diabetic medical emergency',
      status: 'new',
      raw_text: 'Sangam school ke paas father diabetic hain',
      ai_translation: 'Father is diabetic and losing consciousness near Sangam school',
      merged_count: 1,
      update_count: 0,
      confidence: {
        type: 0.95,
        place: 0.86,
        people: 0.80,
        vulnerable: 0.90,
        urgency: 0.88,
      },
    },
  ];

  const mockProposal: MatchProposal = {
    match_id: 'match_001',
    request_id: 'INC-001',
    resource_id: 'res_boat_02',
    resource_name: 'Motorized Rescue Boat #02',
    resource_kind: 'boat',
    resource_ward: 'ward_6',
    capacity_total: 10,
    capacity_remaining: 6,
    score: 91.5,
    breakdown: {
      distance_km: 1.2,
      distance_score: 28.5,
      capacity_fit_score: 24.0,
      urgency_score: 23.5,
      vulnerability_fit_score: 15.5,
      total_score: 91.5,
    },
    explanation: 'Rescue Boat #02 is located 1.2 km away and has 6 remaining seats for 5 people.',
    explanation_hi: 'रेस्क्यू बोट #02 1.2 किमी दूर स्थित है और इसमें 5 लोगों के लिए 6 सीटें उपलब्ध हैं।',
    state: 'proposed',
    overcommit_warning: false,
  };

  const mockResources: StoredResource[] = [
    {
      id: 'res_boat_02',
      kind: 'boat',
      name: 'Motorized Rescue Boat #02',
      ward_id: 'ward_6',
      lat: 26.85,
      lng: 80.93,
      capacity_total: 10,
      capacity_remaining: 6,
      status: 'available',
    },
  ];

  const mockWeights: UrgencyWeights = {
    version: 1,
    w_vulnerability: 35,
    w_people: 25,
    w_hazard: 20,
    w_wait_time: 15,
    confidence_discount_factor: 0.15,
  };

  beforeEach(async () => {
    apiClientSpy = jasmine.createSpyObj('ApiClientService', [
      'getRequests',
      'getRequestMatches',
      'getResources',
      'getUrgencyWeights',
      'updateUrgencyWeights',
      'approveMatch',
      'markArrived',
      'completeRequest',
      'rejectMatch',
      'mergeRequests',
      'keepSeparate',
      'splitCluster',
      'getScenarios',
      'getMapsConfig',
      'getAssistProposals',
      'planAssist',
      'resetDemo',
      'loadFullScenario',
      'getRecentReports',
      'submitSampleReport',
    ]);

    mockResources[0].location_updated_at = new Date().toISOString();
    mockRequests[0].trace = ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'].map((agent) => ({ agent, status: 'complete', provider: 'tool', output: 'Python checks completed', tool_calls: [] }));
    apiClientSpy.getRequests.and.returnValue(of(mockRequests));
    apiClientSpy.getRecentReports.and.returnValue(of([]));
    apiClientSpy.submitSampleReport.and.returnValue(of({
      report_id: 'rpt_s', request_id: 'INC-S', status_token: 'tok', summary: 'ok',
      urgency_score: 80, dedupe_decision: 'new', flags: [], safety_line: 'Call 112',
    }));
    apiClientSpy.getAssistProposals.and.returnValue(of({ proposals: [], shortages: [] }));
    apiClientSpy.planAssist.and.returnValue(of({ proposals: [], shortages: [] }));
    apiClientSpy.resetDemo.and.returnValue(of({ seed: 'small', incidents: 2 }));
    apiClientSpy.loadFullScenario.and.returnValue(of({ seed: 'full', incidents: 40 }));
    apiClientSpy.getMapsConfig.and.returnValue(of({ enabled: false, apiKey: null }));
    apiClientSpy.getScenarios.and.returnValue(of([
      { id: 'flood', title: 'Urban Flood Relief', description: '', incident_types: ['rescue'], tiles: [], follow_up_questions: {}, urgency_rules: {}, resource_types: [], safety_line_ids: [] },
      { id: 'dog_attack', title: 'Dog attack', description: '', incident_types: ['animal_attack'], tiles: [], follow_up_questions: {}, urgency_rules: {}, resource_types: [], safety_line_ids: ['dog_bite_first_aid'] },
    ]));
    apiClientSpy.getRequestMatches.and.returnValue(of([mockProposal]));
    apiClientSpy.getResources.and.returnValue(of(mockResources));
    apiClientSpy.getUrgencyWeights.and.returnValue(of(mockWeights));
    apiClientSpy.updateUrgencyWeights.and.returnValue(of(mockWeights));
    apiClientSpy.approveMatch.and.returnValue(of({ ...mockProposal, state: 'approved' }));
    apiClientSpy.splitCluster.and.returnValue(of({ undone: true, cluster_id: 'cl_seed_INC-001' }));

    await TestBed.configureTestingModule({
      imports: [CoordinatorCommandComponent],
      providers: [provideRouter([]), { provide: ApiClientService, useValue: apiClientSpy }],
    }).compileComponents();

    TestBed.inject(LanguageService).setLanguage('en');
    fixture = TestBed.createComponent(CoordinatorCommandComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('lands on an open case when the highest score is already dispatched', () => {
    const dispatched = { ...mockRequests[0], id: 'INC-DISP', status: 'dispatched' as const, urgency_score: 99 };
    (component as unknown as { initialSelectDone: boolean }).initialSelectDone = false;
    component.applyQueue([dispatched, mockRequests[0], mockRequests[1]], false);
    expect(component.selectedRequestId()).toBe('INC-001');
    fixture.detectChanges();
    const opener = fixture.nativeElement.querySelector('.how-decided-btn') as HTMLButtonElement | null;
    expect(opener?.textContent).toContain('How it decided');
  });

  it('should create and load ranked requests and resources', () => {
    expect(component).toBeTruthy();
    expect(component.requests().length).toBe(2);
    expect(component.criticalCount()).toBe(2);
    expect(component.selectedRequest()?.id).toBe('INC-001');
  });

  it('should correctly compute SVG stroke-dasharray for radial score gauges', () => {
    const dash94 = component.getRadialDasharray(94);
    expect(dash94).toContain('131.9');
    expect(parseFloat(dash94.split(' ')[0])).toBeCloseTo(124.0, 1);
  });

  it('should select request and load corresponding match proposals', () => {
    component.selectRequest('INC-002');
    expect(component.selectedRequestId()).toBe('INC-002');
    expect(apiClientSpy.getRequestMatches).toHaveBeenCalledWith('INC-002', 5);
  });

  it('should approve match, update request status, and display confirmation toast', () => {
    component.approveMatch(mockProposal);
    expect(apiClientSpy.approveMatch).toHaveBeenCalledWith('match_001', false);
    expect(component.actionToast()?.text).toMatch(/Dispatch approved|Motorized Rescue Boat/);
    const updated = component.requests().find((r) => r.id === 'INC-001');
    expect(updated?.status).toBe('dispatched');
    expect(component.filteredRequests().some((r) => r.id === 'INC-001')).toBeFalse();
    expect(component.counts().dispatched).toBe(1);
    expect(component.teamsFree().free).toBe(0);
    component.setBandFilter('dispatched');
    expect(component.filteredRequests().map((r) => r.id)).toEqual(['INC-001']);
  });

  it('marks the assigned team at the scene', () => {
    component.approveMatch(mockProposal);
    apiClientSpy.markArrived.and.returnValue(of({ ...mockRequests[0], status: 'in_progress' }));
    const dispatched = component.requests().find((r) => r.id === 'INC-001')!;
    component.markArrived(dispatched);
    expect(component.resources().find((r) => r.id === 'res_boat_02')?.status).toBe('on_scene');
    expect(component.resources().find((r) => r.id === 'res_boat_02')?.simulated).toBeFalse();
  });

  it('should complete a dispatched case and free the team', () => {
    component.approveMatch(mockProposal);
    apiClientSpy.completeRequest.and.returnValue(of({ ...mockRequests[0], status: 'completed' }));
    const dispatched = component.requests().find((r) => r.id === 'INC-001')!;
    component.markCompleted(dispatched);
    expect(apiClientSpy.completeRequest).toHaveBeenCalledWith('INC-001');
    expect(component.requests().find((r) => r.id === 'INC-001')?.status).toBe('completed');
    expect(component.teamsFree().free).toBe(1);
    expect(component.counts().completed).toBe(1);
    expect(component.counts().critical).toBe(1);
  });

  it('counts every team in the free tile, including shelter and food', () => {
    component.resources.set([
      { ...mockResources[0], id: 'boat', kind: 'boat', status: 'available', capacity_remaining: 6 },
      { ...mockResources[0], id: 'shelter', kind: 'shelter', status: 'available', capacity_remaining: 40 },
      { ...mockResources[0], id: 'food', kind: 'food', status: 'busy', capacity_remaining: 10 },
      { ...mockResources[0], id: 'med', kind: 'medical', status: 'available', capacity_remaining: 0 },
    ]);
    expect(component.teamsFree()).toEqual({ free: 2, busy: 2, notUpdated: 0, total: 4 });
  });

  it('tab counts follow the type, area and time filters, and areas use place names', () => {
    expect(component.counts().total).toBe(2);
    component.setFilterType('medical');
    expect(component.counts().total).toBe(1);
    expect(component.counts().critical).toBe(1);
    component.setArea('ward_7');
    expect(component.counts().total).toBe(0);
    component.setFilterType('all');
    component.setArea('all');
    component.setTime('hour');
    expect(component.counts().total).toBe(0);
    component.clearFilters();
    expect(component.placeName('ward_7')).toBe('Chalakudy');
    expect(component.placeName('ward_4')).toBe('Aluva');
    expect(component.placeName('ward_12')).toBe('Kalpetta');
    expect(/ward\s*\d+/i.test(component.placeName('ward_7'))).toBeFalse();
  });

  it('keeps type, area and time filters and can clear them', () => {
    component.setFilterType('medical');
    component.setArea('ward_4');
    expect(component.filteredRequests().map((r) => r.id)).toEqual(['INC-002']);
    component.setTime('hour');
    expect(component.filteredRequests().length).toBe(0);
    component.clearFilters();
    expect(component.filteredRequests().length).toBe(2);
    expect(component.timeFilter()).toBe('all');
  });

  it('should split cluster and reload requests when undo merge is clicked', () => {
    component.splitCluster('INC-001');
    expect(apiClientSpy.splitCluster).toHaveBeenCalledWith('INC-001');
    expect(component.actionToast()?.text).toContain('separate cases');
    expect(apiClientSpy.getRequests).toHaveBeenCalled();
  });

  it('should update urgency weights and re-rank queue on slider change', () => {
    const fakeEvent = { target: { value: '45' } } as unknown as Event;
    component.onWeightChange('w_vulnerability', fakeEvent);
    expect(apiClientSpy.updateUrgencyWeights).toHaveBeenCalled();
    expect(component.currentWeights().w_vulnerability).toBe(45);
  });

  it('should accurately detect original languages (Hindi, Malayalam, Hinglish, English)', () => {
    expect(component.detectOriginalLanguage('पानी बहुत तेजी से बढ़ रहा है')).toBe('Hindi');
    expect(component.detectOriginalLanguage('വെള്ളം ഉയരുന്നു, സഹായം വേണം')).toBe('Malayalam');
    expect(component.detectOriginalLanguage('paani badh raha hai bachao jaldi')).toBe('Hinglish');
    expect(component.detectOriginalLanguage('Flood water rising rapidly please send boat')).toBe('English');
  });

  it('should identify low translation confidence and display percentage', () => {
    const normalReq: StoredRequest = {
      ...mockRequests[0],
      translation_confidence: 0.94,
      flags: [],
    };
    const lowConfReq: StoredRequest = {
      ...mockRequests[0],
      translation_confidence: 0.42,
      flags: ['low_translation_confidence'],
    };

    expect(component.isLowTranslationConfidence(normalReq)).toBeFalse();
    expect(component.isLowTranslationConfidence(lowConfReq)).toBeTrue();
    expect(component.getTranslationConfidencePercent(lowConfReq)).toBe(42);
  });

  it('should switch translation language and retrieve localized translation text', () => {
    const multiLangReq: StoredRequest = {
      ...mockRequests[0],
      ai_translation: 'Water entered the house.',
      translations: {
        en: 'Water entered the house.',
        hi: 'घर में पानी घुस गया है।',
      },
    };

    component.setTranslationLang('en');
    expect(component.getTranslationText(multiLangReq)).toBe('Water entered the house.');

    component.setTranslationLang('hi');
    expect(component.getTranslationText(multiLangReq)).toBe('घर में पानी घुस गया है।');
  });

  it('titles a case still being analysed with its summary, never the scoring note', () => {
    component.setTranslationLang('en');
    const analysing: StoredRequest = {
      ...mockRequests[0],
      ai_translation: null,
      translations: {},
      urgency_reason: 'Vulnerable flags: child, elderly (Urgency score: 44.7)',
      summary: '5 people needing rescue | at Gandhi School | Vulnerable: child | Hazard: water_rising',
      analysis_status: 'analysing',
    };
    expect(component.getTranslationText(analysing)).toBe('Gemini is reading this report…');
    expect(component.getTranslationText({ ...analysing, summary: null })).toBe('Gemini is reading this report…');
    expect(component.getTranslationText({ ...analysing, analysis_status: 'complete', summary: null, raw_text: 'Vulnerable flags: child (Urgency score: 44.7)' }))
      .toBe(analysing.place_text as string);
  });

  it('builds a queue need line from flags and the needed team, never a scoring note', () => {
    const line = component.queueNeedLine(mockRequests[0]);
    expect(line.toLowerCase()).toContain('children');
    expect(line.toLowerCase()).toContain('elderly');
    expect(line.toLowerCase()).toMatch(/boat/);
    expect(line).not.toMatch(/urgency score/i);
    const onlyChild = component.queueNeedLine({
      ...mockRequests[0],
      people_count: 3,
      vulnerable: { child: true, elderly: false, disabled: false, pregnant: false, medical_need: false },
    });
    expect(onlyChild.toLowerCase()).toMatch(/3 children/);
    expect(onlyChild.toLowerCase()).toMatch(/boat/);
  });

  it('formats waiting time from wait_minutes or created_at', () => {
    expect(component.waitTime({ ...mockRequests[0], wait_minutes: 12 })).toMatch(/12/);
    const hourAgo = new Date(Date.now() - 70 * 60_000).toISOString();
    expect(component.waitTime({ ...mockRequests[0], wait_minutes: 0, created_at: hourAgo })).toMatch(/1 h/);
  });

  it('shows a slim queue card and a Send card with one Why line', () => {
    const card = fixture.nativeElement.querySelector('button.case-card-compact') as HTMLElement;
    expect(card.querySelector('.card-place-title')?.textContent).toContain('Ward 7');
    expect(card.querySelector('[data-testid="ai-english"]')?.textContent).toContain('Water has entered');
    expect(card.textContent).toContain('Critical');
    const panel = fixture.nativeElement.querySelector('.decision-panel') as HTMLElement;
    expect(panel.textContent).toContain('Best team for this');
    expect(panel.textContent).toContain('1.2 km');
    expect(panel.querySelector('[data-testid="team-why"]')?.textContent).toContain('Rescue Boat #02');
    expect(panel.querySelector('.more-block')).toBeNull();
    expect(component.sendTeamLabel('Boat 2')).toBe('Send');
    expect(component.whyLine(mockProposal)).toContain('Closest free team');
    const reading = {
      ...mockRequests[0],
      id: 'INC-READ',
      analysis_status: 'analysing' as const,
      place_text: 'Alappuzha',
      summary: '1 person(s) needing other at Alappuzha',
      ai_translation: null,
    };
    expect(component.caseTitle(reading)).toBe('Gemini is reading this report…');
    expect(component.getTranslationText(reading)).not.toContain('person(s) needing');
    const dashed = { ...mockProposal, explanation: '5 boat free: — km' };
    expect(component.teamWhy(dashed)).toContain('km');
    expect(component.teamWhy(dashed)).not.toContain('—');
  });

  it('keeps Ward N on the queue location line', () => {
    expect(component.locationLine(mockRequests[0])).toMatch(/^Ward 7 ·/);
    expect(component.locationLine({ ...mockRequests[0], ward_id: 'ward_12', place_text: 'Canal Road' }))
      .toBe('Ward 12 · Canal Road');
  });

  it('merges a new report into the open queue and keeps the selected case', () => {
    expect(component.selectedRequestId()).toBe('INC-001');
    const live = {
      ...mockRequests[0],
      id: 'INC-LIVE',
      urgency_score: 96,
      place_text: 'Just reported',
      updated_at: '2026-10-11T15:00:00+00:00',
    };
    component.applyQueue([live], true);
    expect(component.requests().some((row) => row.id === 'INC-LIVE')).toBeTrue();
    expect(component.freshIds().has('INC-LIVE')).toBeTrue();
    expect(component.flashIds().has('INC-LIVE')).toBeTrue();
    expect(component.selectedRequestId()).toBe('INC-001');
    component.openReported('INC-LIVE');
    expect(component.selectedRequestId()).toBe('INC-LIVE');
  });

  it('shows Gemini or Offline fallback on the AI reading', () => {
    const rows = component.requests().map((row) => ({ ...row }));
    rows[0] = { ...rows[0], ai_source: 'gemini' };
    rows[1] = { ...rows[1], ai_source: 'offline_fallback' };
    component.requests.set(rows);
    component.selectRequest('INC-001');
    fixture.detectChanges();
    const gemini = fixture.nativeElement.textContent as string;
    expect(gemini).toContain('Gemini');
    component.selectRequest('INC-002');
    fixture.detectChanges();
    const offline = fixture.nativeElement.textContent as string;
    expect(offline).toContain('Gemini unavailable, built-in rules used');
    expect(offline).not.toContain('Offline fallback');
    rows[0] = {
      ...rows[0],
      ai_source: 'recorded',
      ai: { provider: 'cache', model: 'gemini-3.8-flash', latency_ms: 4, tokens: 12, cached: true, fallback_reason: null },
    };
    component.requests.set(rows);
    component.selectRequest('INC-001');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent as string).toContain('Recorded (Gemini)');
  });

  it('says there is no nearby team instead of an hours-long ETA', () => {
    const far: MatchProposal = {
      ...mockProposal,
      eta_minutes: 5995,
      no_nearby: true,
      breakdown: { ...mockProposal.breakdown, distance_km: 1998 },
    };
    expect(component.etaText(far)).toBe('No nearby team');
    expect(component.etaText(far)).not.toContain('5995');
    const near: MatchProposal = {
      ...mockProposal,
      eta_minutes: 4,
      breakdown: { ...mockProposal.breakdown, distance_km: 1.2 },
    };
    expect(component.etaText(near)).toBe('about 4 min');
    const freeClose: MatchProposal = {
      ...mockProposal,
      eta_minutes: undefined,
      no_nearby: true,
      breakdown: { ...mockProposal.breakdown, distance_km: 12 },
    };
    expect(component.etaText(freeClose)).toBe('about 36 min');
    expect(component.etaText(freeClose)).not.toContain('No nearby team');
  });

  it('fits open cases and labels the four Kerala districts without a river', () => {
    component.matches.set([]);
    component.requests.set([
      { ...mockRequests[0], id: 'south', lat: 9.43, lng: 76.4, status: 'new' },
      { ...mockRequests[0], id: 'north', lat: 11.6, lng: 76.08, status: 'new' },
      { ...mockRequests[0], id: 'done', lat: 26.8, lng: 80.9, status: 'completed' },
    ]);
    fixture.detectChanges();
    const frame = component.mapFrame();
    expect(frame.minLa).toBeLessThan(9.43);
    expect(frame.maxLa).toBeGreaterThan(11.6);
    expect(frame.maxLa).toBeLessThan(20);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Alappuzha');
    expect(text).toContain('Ernakulam');
    expect(text).toContain('Thrissur');
    expect(text).toContain('Wayanad');
    expect(fixture.nativeElement.querySelectorAll('polygon.district').length).toBe(4);
    expect(fixture.nativeElement.querySelector('path[stroke="var(--map-water)"]')).toBeNull();
    const pins = component.svgPins().filter((pin) => pin.kind === 'req');
    expect(pins.map((pin) => pin.id).sort()).toEqual(['north', 'south']);
    for (const pin of pins) {
      expect(pin.x).toBeGreaterThan(20);
      expect(pin.x).toBeLessThan(580);
      expect(pin.y).toBeGreaterThan(20);
      expect(pin.y).toBeLessThan(460);
    }
  });

  it('focuses the selected case, labels team lines, and lists only the kinds on the map', () => {
    component.resources.set([
      ...mockResources,
      { ...mockResources[0], id: 'res_shelter', kind: 'shelter', name: 'School hall', lat: 26.86, lng: 80.94 },
    ]);
    fixture.detectChanges();
    const pins = component.drawnPins();
    expect(pins.find((pin) => pin.id === 'INC-001')?.dim).toBeFalse();
    expect(pins.find((pin) => pin.id === 'INC-002')?.dim).toBeTrue();
    expect(pins.find((pin) => pin.id === 'res_boat_02')?.suggested).toBeTrue();
    expect(pins.find((pin) => pin.id === 'res_shelter')?.dim).toBeTrue();
    expect(component.focusLegs().map((leg) => leg.label)).toEqual(['1.2 km · about 4 min']);
    expect(component.mapLegs().map((leg) => leg.title)).toEqual(['1.2 km · about 4 min']);
    expect(component.mapLegs()[0].suggested).toBeTrue();
    const provider = fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(provider.legs.map((leg) => leg.title)).toEqual(['1.2 km · about 4 min']);
    expect(provider.legs[0].suggested).toBeTrue();
    expect(provider.fitAll).toBeFalse();
    const frame = component.mapFrame();
    expect(frame.minLa).toBeLessThan(26.85);
    expect(frame.maxLa).toBeGreaterThan(26.852);
    expect(frame.minLo).toBeLessThan(80.925);
    expect(frame.maxLo).toBeGreaterThan(80.93);
    for (const leg of component.focusLegs()) {
      for (const value of [leg.x1, leg.x2, leg.lx]) {
        expect(value).toBeGreaterThan(20);
        expect(value).toBeLessThan(580);
      }
      for (const value of [leg.y1, leg.y2, leg.ly]) {
        expect(value).toBeGreaterThan(10);
        expect(value).toBeLessThan(470);
      }
    }
    expect(component.legendBands()).toEqual(['critical']);
    expect(component.legendKinds()).toEqual(['boat']);
    const legend = fixture.nativeElement.querySelector('.map-legend-overlay') as HTMLElement;
    expect(legend.textContent).toContain('Critical');
    expect(legend.textContent).toContain('Urgent');
    expect(legend.textContent).toContain('Teams free');
    expect(legend.textContent).not.toContain('Shelter');
    const boat = component.mapPins().find((pin) => pin.id === 'res_boat_02');
    expect(boat?.vehicle).toBe('boat');
    expect(boat?.marker).toBe('team');
    const svg = fixture.nativeElement.querySelector('.svgmap') as HTMLElement | null;
    if (svg) {
      expect(svg.textContent).toContain('1.2 km · about 4 min');
      expect(svg.querySelector('.pin rect')).not.toBeNull();
    }
    component.highlightId.set('res_boat_02');
    fixture.detectChanges();
    expect(provider.highlightId).toBe('res_boat_02');
    expect(provider.legs.map((leg) => leg.title)).toEqual(['1.2 km · about 4 min']);
  });

  it('draws one recommended line and changes it when inspecting a different team', () => {
    const extra = [1, 2, 3].map((n) => ({
      ...mockProposal,
      match_id: `m${n}`,
      resource_id: `res_${n}`,
      resource_name: `Team ${n}`,
      breakdown: { ...mockProposal.breakdown, distance_km: n },
      eta_minutes: n * 3,
    }));
    component.resources.set([
      ...mockResources,
      ...extra.map((prop, n) => ({ ...mockResources[0], id: prop.resource_id, name: prop.resource_name, lat: 26.86 + n / 100, lng: 80.94 })),
    ]);
    component.matches.set([mockProposal, ...extra]);
    fixture.detectChanges();
    expect(component.mapLegs().length).toBe(1);
    expect(component.focusLegs().length).toBe(1);
    expect(component.mapLegs().map((leg) => leg.id)).not.toContain('res_3');
    expect(component.candidateMatches().length).toBe(3);
    component.highlightId.set('res_2');
    expect(component.mapLegs().map((leg) => leg.id)).toEqual(['res_2']);
    component.highlightId.set(null);
    expect(component.mapLegs().map((leg) => leg.id)).toEqual(['res_boat_02']);
  });

  it('reloads the queue when the demo phone submits a report', () => {
    apiClientSpy.getRequests.calls.reset();
    component.handleDemoMessage({
      origin: window.location.origin,
      data: { type: 'rd-report-submitted', reportId: 'R-demo' },
    } as MessageEvent);
    expect(apiClientSpy.getRequests).toHaveBeenCalled();
  });

  it('opens the phone report on the queue and ignores a watermark', () => {
    expect(component.selectedRequestId()).toBe('INC-001');
    const live = {
      ...mockRequests[0],
      id: 'req_phone',
      place_text: 'Temple Road',
      urgency_score: 90,
      updated_at: '2026-10-12T18:00:00+00:00',
    };
    apiClientSpy.getRequests.and.returnValue(of([...mockRequests, live]));
    apiClientSpy.getRequests.calls.reset();
    component.onLiveReport({ type: 'rd-report-submitted', requestId: 'req_phone' });
    const args = apiClientSpy.getRequests.calls.mostRecent().args;
    expect(args[2]).toBeUndefined();
    expect(component.requests().some((row) => row.id === 'req_phone')).toBeTrue();
    expect(component.selectedRequestId()).toBe('req_phone');
  });

  it('Reset demo and Load full scenario replace the whole queue', () => {
    spyOn(window, 'confirm').and.returnValue(true);
    apiClientSpy.getRequests.and.returnValue(of([mockRequests[0]]));
    component.resetDemo();
    expect(apiClientSpy.resetDemo).toHaveBeenCalled();
    expect(component.requests().map((row) => row.id)).toEqual(['INC-001']);
    mockResources[0].location_updated_at = new Date().toISOString();
    mockRequests[0].trace = ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'].map((agent) => ({ agent, status: 'complete', provider: 'tool', output: 'Python checks completed', tool_calls: [] }));
    apiClientSpy.getRequests.and.returnValue(of(mockRequests));
    component.loadFullScenario();
    expect(apiClientSpy.loadFullScenario).toHaveBeenCalled();
    expect(component.requests().map((row) => row.id)).toEqual(['INC-001', 'INC-002']);
  });

  it('filters the open queue from the top search box', () => {
    component.searchQuery.set('Gandhi');
    fixture.detectChanges();
    expect(component.filteredRequests().map((row) => row.id)).toEqual(['INC-001']);
    expect(component.counts().total).toBe(1);
    component.searchQuery.set('Canal Road');
    fixture.detectChanges();
    expect(component.filteredRequests().map((row) => row.id)).toEqual(['INC-002']);
    expect(component.counts().total).toBe(1);
  });

  it('dispatched and completed chips count the same rows the list shows', () => {
    const dispatched = { ...mockRequests[0], id: 'INC-D', status: 'dispatched' as const, place_text: 'Boat yard', raw_text: 'Boat yard', ai_translation: 'Boat yard' };
    const completed = { ...mockRequests[1], id: 'INC-C', status: 'completed' as const, place_text: 'School hall', raw_text: 'School hall', ai_translation: 'School hall' };
    const open = { ...mockRequests[0], id: 'INC-O', status: 'new' as const, place_text: 'Temple road', raw_text: 'Temple road', ai_translation: 'Temple road' };
    component.applyQueue([dispatched, completed, open], false);

    expect(component.counts().dispatched).toBe(1);
    expect(component.counts().completed).toBe(1);
    component.setBandFilter('dispatched');
    expect(component.filteredRequests().map((row) => row.id)).toEqual(['INC-D']);
    expect(component.filteredRequests().length).toBe(component.counts().dispatched);

    component.searchQuery.set('zzzz-no-such-case');
    expect(component.counts().dispatched).toBe(0);
    expect(component.filteredRequests().length).toBe(0);

    component.searchQuery.set('Boat');
    expect(component.counts().dispatched).toBe(1);
    expect(component.filteredRequests().map((row) => row.id)).toEqual(['INC-D']);

    component.setBandFilter('completed');
    expect(component.filteredRequests().length).toBe(0);
    expect(component.counts().completed).toBe(0);
    component.searchQuery.set('');
    expect(component.filteredRequests().map((row) => row.id)).toEqual(['INC-C']);
    expect(component.filteredRequests().length).toBe(component.counts().completed);

    component.searchQuery.set('zzzz-no-such-case');
    component.setBandFilter('dispatched');
    component.clearFilters();
    expect(component.searchQuery()).toBe('');
    expect(component.bandFilter()).toBe('all');
    expect(component.counts().dispatched).toBe(1);
    expect(component.filteredRequests().map((row) => row.id)).toEqual(['INC-O']);
  });

  it('opens five agents from the selected case and keeps assist behind a review tap', () => {
    const opener = fixture.nativeElement.querySelector('.how-decided-btn') as HTMLButtonElement;
    opener.click();
    fixture.detectChanges();
    const trace = fixture.nativeElement.textContent as string;
    expect(trace).toContain('Understood the report');
    expect(trace).toContain('Checked for duplicates');
    expect(trace).toContain('Rated urgency');
    expect(trace).toContain('Found the closest team');
    expect(trace).toContain('Explained the choice');
    expect(trace).toContain('Google Maps');
    component.closeTrace();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent as string).not.toContain('Nothing is dispatched until you approve');
    component.assist.set({
      proposals: [{
        match_id: 'm1',
        request_id: 'INC-001',
        title: 'Lane',
        team_name: 'Boat 2',
        team_kind: 'boat',
        why: 'Nearest free boat',
        expires_at: null,
        expired: false,
      }],
      shortages: [{ kind: 'boat', have: 2, need: 3, explanation: 'Not enough teams' }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent as string).toContain('Staff low: dispatcher suggests 1 assignment');
    (fixture.nativeElement.querySelector('app-assist-banner button') as HTMLButtonElement).click();
    fixture.detectChanges();
    const panel = fixture.nativeElement.textContent as string;
    expect(panel).toContain('Nothing is dispatched until you approve');
    expect(panel).toContain('Why only 2 of 3?');
    expect(panel).toContain('Not enough teams');
  });

  it('shows an analysing card in place and a done chip after the trace completes', () => {
    const live = { ...mockRequests[0], id: 'INC-NEW', analysis_status: 'analysing' as const, urgency_score: 99, trace: [{ agent: 'Intake', status: 'complete' as const, output: 'rescue' }] };
    component.applyQueue([live], true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="ai-analysing"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent as string).toContain('AI analysing…');
    expect(fixture.nativeElement.querySelector('button.case')).not.toBeNull();
    expect(component.selectedRequestId()).toBe('INC-001');
    component.applyQueue([{
      ...live,
      analysis_status: 'complete',
      trace: ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'].map((agent, index) => ({
        agent,
        status: 'complete' as const,
        output: 'done',
        model: 'gemini-3.8-flash',
        latency_ms: 100 * (index + 1),
      })),
    }], true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="ai-analysing"]')).toBeNull();
    expect(fixture.nativeElement.textContent as string).toContain('Analysed by 5 agents in');
  });

  it('shows conflicting counts, each report, and merge or keep-separate', () => {
    apiClientSpy.mergeRequests.and.returnValue(of({ cluster_id: 'c1' }));
    apiClientSpy.keepSeparate.and.returnValue(of({ id: 'INC-DUP' }));
    const dup: StoredRequest = {
      ...mockRequests[0],
      id: 'INC-DUP',
      people_count: 5,
      count_spans: ['2-3', '4-5'],
      count_note: 'Counts differ: 2-3 vs 4-5',
      report_quotes: [
        { report_id: 'r1', text: '2-3 people at Oakbend' },
        { report_id: 'r2', text: '4-5 people at Oakbend' },
      ],
      possible_duplicate: {
        target_id: 'INC-001',
        confidence: 0.6,
        similarity: 0.55,
        distance_km: 0.8,
        minutes: 12,
        note: 'Possible duplicate, review',
      },
    };
    component.applyQueue([dup], false);
    component.selectRequest('INC-DUP');
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Counts differ: 2-3 vs 4-5');
    expect(text).toContain('AI found this matches INC-001 (55% similar)');
    expect(text).not.toContain('ux.none');
    expect(fixture.nativeElement.querySelector('[data-testid="dup-review"]')).not.toBeNull();
    (fixture.nativeElement.querySelector('[data-testid="merge-dup"]') as HTMLButtonElement).click();
    expect(apiClientSpy.mergeRequests).toHaveBeenCalledWith('INC-001', 'INC-DUP', jasmine.any(Array));
    (fixture.nativeElement.querySelector('[data-testid="keep-dup"]') as HTMLButtonElement).click();
    expect(apiClientSpy.keepSeparate).toHaveBeenCalledWith('INC-DUP');
  });

  it('keeps a counts note visible after the reports have already merged', () => {
    const merged: StoredRequest = {
      ...mockRequests[0],
      id: 'INC-MERGED',
      people_count: 5,
      merged_count: 2,
      count_note: 'Counts differ: 2-3 vs 4-5',
      dedupe_decision: 'duplicate',
    } as StoredRequest;
    component.applyQueue([merged], false);
    component.selectRequest('INC-MERGED');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="counts-differ"]')?.textContent).toContain('Counts differ: 2-3 vs 4-5');
    expect(fixture.nativeElement.querySelector('[data-testid="dup-review"]')).toBeNull();
  });
});
