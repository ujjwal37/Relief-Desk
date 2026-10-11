import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { CoordinatorCommandComponent } from './coordinator-command.component';
import { ApiClientService, StoredRequest, MatchProposal, StoredResource, UrgencyWeights } from '@rd/shared';

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
      'splitCluster',
      'getScenarios',
      'getMapsConfig',
    ]);

    apiClientSpy.getRequests.and.returnValue(of(mockRequests));
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

    fixture = TestBed.createComponent(CoordinatorCommandComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
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
    expect(component.actionToast()?.text).toContain('Dispatch Approved');
    const updated = component.requests().find((r) => r.id === 'INC-001');
    expect(updated?.status).toBe('dispatched');
    expect(component.filteredRequests().some((r) => r.id === 'INC-001')).toBeFalse();
    expect(component.counts().dispatched).toBe(1);
    expect(component.teamsFree().free).toBe(0);
    component.setBandFilter('dispatched');
    expect(component.filteredRequests().map((r) => r.id)).toEqual(['INC-001']);
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
    expect(component.actionToast()?.text).toContain('Cluster split undone');
    expect(apiClientSpy.getRequests).toHaveBeenCalled();
  });

  it('should update urgency weights and re-rank queue on slider change', () => {
    const fakeEvent = { target: { value: '45' } } as unknown as Event;
    component.onWeightChange('w_vulnerability', fakeEvent);
    expect(apiClientSpy.updateUrgencyWeights).toHaveBeenCalled();
    expect(component.currentWeights().w_vulnerability).toBe(45);
  });

  it('should accurately detect original languages (Hindi, Tamil, Hinglish, English)', () => {
    expect(component.detectOriginalLanguage('पानी बहुत तेजी से बढ़ रहा है')).toBe('Hindi');
    expect(component.detectOriginalLanguage('வெள்ளத்தில் சிக்கியுள்ளோம் காப்பாற்றுங்கள்')).toBe('Tamil');
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
        ta: 'வீட்டிற்குள் தண்ணீர் புகுந்தது.',
      },
    };

    component.setTranslationLang('en');
    expect(component.getTranslationText(multiLangReq)).toBe('Water entered the house.');

    component.setTranslationLang('hi');
    expect(component.getTranslationText(multiLangReq)).toBe('घर में पानी घुस गया है।');

    component.setTranslationLang('ta');
    expect(component.getTranslationText(multiLangReq)).toBe('வீட்டிற்குள் தண்ணீர் புகுந்தது.');
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
    expect(component.selectedRequestId()).toBe('INC-001');
  });

  it('reloads the queue when the demo phone submits a report', () => {
    apiClientSpy.getRequests.calls.reset();
    component.handleDemoMessage({
      origin: window.location.origin,
      data: { type: 'rd-report-submitted', reportId: 'R-demo' },
    } as MessageEvent);
    expect(apiClientSpy.getRequests).toHaveBeenCalled();
  });
});
