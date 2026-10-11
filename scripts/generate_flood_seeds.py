"""
Generator script for synthetic seeds (T-009)
Generates data/synthetic/flood_v1/seeds.yaml with:
- Fictional city: Riverbend
- 12 wards
- 60 landmarks with Hindi & Latin aliases
- 40 ground-truth flood incidents
"""
import yaml
from pathlib import Path

def generate_seeds():
    city = {
        "name": "Riverbend",
        "state": "Uttar Pradesh",
        "center": {"lat": 26.8500, "lng": 80.9400},
        "bbox": {
            "min_lat": 26.7800,
            "max_lat": 26.9200,
            "min_lng": 80.8800,
            "max_lng": 81.0100
        }
    }

    wards = [
        {"id": "ward_1", "number": 1, "name_en": "Sangam Vihar", "name_hi": "संगम विहार"},
        {"id": "ward_2", "number": 2, "name_en": "Gandhi Nagar", "name_hi": "गांधी नगर"},
        {"id": "ward_3", "number": 3, "name_en": "Riverfront Ghat", "name_hi": "रिवरफ्रंट घाट"},
        {"id": "ward_4", "number": 4, "name_en": "Old Bazaar", "name_hi": "पुराना बाज़ार"},
        {"id": "ward_5", "number": 5, "name_en": "Shanti Nagar", "name_hi": "शांति नगर"},
        {"id": "ward_6", "number": 6, "name_en": "Civil Lines", "name_hi": "सिविल लाइन्स"},
        {"id": "ward_7", "number": 7, "name_en": "Industrial Area Phase 1", "name_hi": "इंडस्ट्रियल एरिया फेज़ 1"},
        {"id": "ward_8", "number": 8, "name_en": "Green Park Colony", "name_hi": "ग्रीन पार्क कॉलोनी"},
        {"id": "ward_9", "number": 9, "name_en": "Subhash Nagar", "name_hi": "सुभाष नगर"},
        {"id": "ward_10", "number": 10, "name_en": "Model Town", "name_hi": "मॉडल टाउन"},
        {"id": "ward_11", "number": 11, "name_en": "Transport Nagar", "name_hi": "ट्रांसपोर्ट नगर"},
        {"id": "ward_12", "number": 12, "name_en": "Lake View Enclave", "name_hi": "लेक व्यू एन्क्लेव"}
    ]

    raw_landmarks = [
        # Ward 1: Sangam Vihar
        ("LM-01", "Sangam Primary School", "ward_1", 26.8450, 80.9320, "school", ["संगम प्राइमरी स्कूल", "संगम स्कूल"], ["sangam primary school", "sangam school"]),
        ("LM-02", "Mata Mandir Sangam Vihar", "ward_1", 26.8465, 80.9340, "temple", ["माता मंदिर संगम विहार", "माता मंदिर"], ["mata mandir sangam vihar", "mata mandir sangam"]),
        ("LM-03", "Sangam Community Hall", "ward_1", 26.8480, 80.9310, "community_hall", ["संगम कम्युनिटी हॉल", "संगम बारात घर"], ["sangam community hall", "sangam barat ghar"]),
        ("LM-04", "Sangam Vihar Health Centre", "ward_1", 26.8435, 80.9355, "hospital", ["संगम विहार स्वास्थ्य केंद्र", "संगम डिस्पेंसरी"], ["sangam health centre", "sangam dispensary"]),
        ("LM-05", "Sangam Police Chowki", "ward_1", 26.8490, 80.9330, "police_station", ["संगम पुलिस चौकी"], ["sangam police chowki", "sangam chowki"]),

        # Ward 2: Gandhi Nagar
        ("LM-06", "Gandhi High School", "ward_2", 26.8520, 80.9250, "school", ["गांधी हाई स्कूल", "गांधी स्कूल", "गांधी विद्यालय"], ["gandhi high school", "gandhi school", "gandhi vidyalaya"]),
        ("LM-07", "Gandhi Nagar Main Market", "ward_2", 26.8540, 80.9280, "market", ["गांधी नगर मुख्य बाज़ार", "गांधी नगर मार्केट"], ["gandhi nagar main market", "gandhi nagar bazaar"]),
        ("LM-08", "Shri Ram Mandir Gandhi Nagar", "ward_2", 26.8510, 80.9230, "temple", ["श्री राम मंदिर गांधी नगर", "राम मंदिर"], ["ram mandir gandhi nagar", "shri ram mandir"]),
        ("LM-09", "Gandhi Nagar Urban Shelter", "ward_2", 26.8560, 80.9270, "shelter", ["गांधी नगर रैन बसेरा", "गांधी नगर शेल्टर"], ["gandhi nagar shelter", "gandhi nagar rain basera"]),
        ("LM-10", "Gandhi Nagar Metro Station", "ward_2", 26.8505, 80.9295, "metro_station", ["गांधी नगर मेट्रो स्टेशन", "गांधी नगर मेट्रो"], ["gandhi nagar metro station", "gandhi nagar metro"]),

        # Ward 3: Riverfront Ghat
        ("LM-11", "Ram Ghat Riverfront", "ward_3", 26.8390, 80.9410, "ghat", ["राम घाट रिवरफ्रंट", "राम घाट"], ["ram ghat riverfront", "ram ghat"]),
        ("LM-12", "Hanuman Setu Bridge", "ward_3", 26.8410, 80.9440, "bridge", ["हनुमान सेतु पुल", "हनुमान सेतु ब्रिज"], ["hanuman setu bridge", "hanuman bridge"]),
        ("LM-13", "Riverfront Boat Club", "ward_3", 26.8370, 80.9390, "shelter", ["रिवरफ्रंट बोट क्लब", "बोट क्लब घाट"], ["riverfront boat club", "boat club"]),
        ("LM-14", "Ganga Darshan Viewpoint", "ward_3", 26.8420, 80.9460, "ghat", ["गंगा दर्शन व्यूप्वाइंट", "गंगा दर्शन घाट"], ["ganga darshan viewpoint", "ganga darshan ghat"]),
        ("LM-15", "Riverfront Disaster Relief Post", "ward_3", 26.8380, 80.9430, "shelter", ["रिवरफ्रंट राहत केंद्र", "फ्लड रिलीफ पोस्ट"], ["riverfront relief post", "flood relief center"]),

        # Ward 4: Old Bazaar
        ("LM-16", "Ghanta Ghar Clock Tower", "ward_4", 26.8610, 80.9150, "market", ["घंटा घर क्लॉक टॉवर", "घंटा घर"], ["ghanta ghar clock tower", "clock tower old bazaar"]),
        ("LM-17", "Jama Masjid Old Bazaar", "ward_4", 26.8630, 80.9170, "mosque", ["जामा मस्जिद पुराना बाज़ार", "बड़ी जामा मस्जिद"], ["jama masjid old bazaar", "jama masjid"]),
        ("LM-18", "Old Bazaar Govt Dispensary", "ward_4", 26.8590, 80.9130, "hospital", ["पुराना बाज़ार सरकारी डिस्पेंसरी"], ["old bazaar govt dispensary", "bazaar dispensary"]),
        ("LM-19", "Kotwali City Police Station", "ward_4", 26.8625, 80.9140, "police_station", ["कोतवाली सिटी थाना", "कोतवाली पुलिस"], ["kotwali city police station", "kotwali thana"]),
        ("LM-20", "Sarafa Cloth Market", "ward_4", 26.8605, 80.9185, "market", ["सराफा कपड़ा बाज़ार", "सराफा मार्केट"], ["sarafa cloth market", "sarafa bazaar"]),

        # Ward 5: Shanti Nagar
        ("LM-21", "Shanti Nagar Public Library", "ward_5", 26.8480, 80.9520, "community_hall", ["शांति नगर पब्लिक लाइब्रेरी", "शांति नगर पुस्तकालय"], ["shanti nagar public library", "shanti nagar library"]),
        ("LM-22", "St. Jude Mission Hospital", "ward_5", 26.8500, 80.9550, "hospital", ["सेंट ज्यूड मिशन हॉस्पिटल", "सेंट ज्यूड अस्पताल"], ["st jude mission hospital", "st jude hospital"]),
        ("LM-23", "Shanti Nagar Senior Secondary School", "ward_5", 26.8460, 80.9510, "school", ["शांति नगर सीनियर सेकेंडरी स्कूल"], ["shanti nagar senior secondary school", "shanti nagar school"]),
        ("LM-24", "Guru Nanak Gurudwara Shanti Nagar", "ward_5", 26.8515, 80.9535, "temple", ["गुरु नानक गुरुद्वारा शांति नगर", "शांति नगर गुरुद्वारा"], ["guru nanak gurudwara shanti nagar", "shanti nagar gurudwara"]),
        ("LM-25", "Shanti Nagar Park Ground", "ward_5", 26.8490, 80.9570, "shelter", ["शांति नगर पार्क ग्राउंड", "शांति पार्क"], ["shanti nagar park ground", "shanti park"]),

        # Ward 6: Civil Lines
        ("LM-26", "District Collectorate Civil Lines", "ward_6", 26.8650, 80.9350, "community_hall", ["जिला कलेक्ट्रेट सिविल लाइन्स", "कलेक्ट्रेट ऑफिस"], ["district collectorate civil lines", "collectorate office"]),
        ("LM-27", "Civil Hospital Riverbend", "ward_6", 26.8670, 80.9380, "hospital", ["सिविल हॉस्पिटल रिवरबेंड", "सरकारी सिविल अस्पताल"], ["civil hospital riverbend", "civil hospital"]),
        ("LM-28", "Civil Lines Metro Station", "ward_6", 26.8635, 80.9330, "metro_station", ["सिविल लाइन्स मेट्रो स्टेशन"], ["civil lines metro station", "civil lines metro"]),
        ("LM-29", "St. Mary Convent High School", "ward_6", 26.8690, 80.9360, "school", ["सेंट मैरी कॉन्वेंट हाई स्कूल", "सेंट मैरी स्कूल"], ["st mary convent high school", "st mary school"]),
        ("LM-30", "Civil Lines Police Headquarters", "ward_6", 26.8640, 80.9395, "police_station", ["सिविल लाइन्स पुलिस मुख्यालय"], ["civil lines police headquarters", "civil lines police station"]),

        # Ward 7: Industrial Area Phase 1
        ("LM-31", "Thermal Power Plant Colony Gate", "ward_7", 26.8250, 80.9650, "shelter", ["थर्मल पावर प्लांट कॉलोनी गेट"], ["thermal power plant colony gate", "power plant gate"]),
        ("LM-32", "Labor Welfare Hospital", "ward_7", 26.8280, 80.9680, "hospital", ["श्रम कल्याण अस्पताल", "लेबर हॉस्पिटल"], ["labor welfare hospital", "esi hospital"]),
        ("LM-33", "Industrial Workers Community Hall", "ward_7", 26.8230, 80.9620, "community_hall", ["मजदूर कल्याण भवन", "इंडस्ट्रियल कम्युनिटी हॉल"], ["industrial workers community hall", "mazdoor kalyan bhavan"]),
        ("LM-34", "Railway Freight Yard Phase 1", "ward_7", 26.8210, 80.9700, "shelter", ["रेलवे फ्रेट यार्ड फेज़ 1"], ["railway freight yard phase 1", "railway goods yard"]),
        ("LM-35", "Industrial Phase 1 Police Outpost", "ward_7", 26.8265, 80.9640, "police_station", ["इंडस्ट्रियल फेज़ 1 पुलिस चौकी"], ["industrial phase 1 police outpost", "phase 1 police chowki"]),

        # Ward 8: Green Park Colony
        ("LM-36", "Green Park Stadium Gate 3", "ward_8", 26.8720, 80.9480, "shelter", ["ग्रीन पार्क स्टेडियम गेट 3", "ग्रीन पार्क स्टेडियम"], ["green park stadium gate 3", "green park stadium"]),
        ("LM-37", "Saraswati Shishu Mandir Green Park", "ward_8", 26.8740, 80.9450, "school", ["सरस्वती शिशु मंदिर ग्रीन पार्क"], ["saraswati shishu mandir green park", "shishu mandir green park"]),
        ("LM-38", "Green Park Community Health Centre", "ward_8", 26.8710, 80.9510, "hospital", ["ग्रीन पार्क सामुदायिक स्वास्थ्य केंद्र"], ["green park chc", "green park health centre"]),
        ("LM-39", "Green Park Shopping Complex", "ward_8", 26.8755, 80.9490, "market", ["ग्रीन पार्क शॉपिंग कॉम्प्लेक्स", "ग्रीन पार्क मार्केट"], ["green park shopping complex", "green park market"]),
        ("LM-40", "Shiv Mandir Green Park", "ward_8", 26.8700, 80.9465, "temple", ["शिव मंदिर ग्रीन पार्क"], ["shiv mandir green park", "green park shiv temple"]),

        # Ward 9: Subhash Nagar
        ("LM-41", "Subhash Chowk Traffic Roundabout", "ward_9", 26.8580, 80.9750, "market", ["सुभाष चौक चौराहा", "सुभाष चौक"], ["subhash chowk traffic roundabout", "subhash chowk"]),
        ("LM-42", "Netaji Subhash Govt Inter College", "ward_9", 26.8600, 80.9780, "school", ["नेताजी सुभाष सरकारी इंटर कॉलेज", "सुभाष कॉलेज"], ["netaji subhash govt inter college", "subhash inter college"]),
        ("LM-43", "Subhash Nagar Rotary Eye Clinic", "ward_9", 26.8560, 80.9720, "hospital", ["सुभाष नगर रोटरी आई क्लिनिक"], ["subhash nagar rotary eye clinic", "subhash clinic"]),
        ("LM-44", "Subhash Nagar Barat Ghar", "ward_9", 26.8615, 80.9740, "community_hall", ["सुभाष नगर बारात घर"], ["subhash nagar barat ghar", "subhash community hall"]),
        ("LM-45", "Subhash Nagar Police Station", "ward_9", 26.8590, 80.9795, "police_station", ["सुभाष नगर पुलिस थाना"], ["subhash nagar police station", "subhash nagar thana"]),

        # Ward 10: Model Town
        ("LM-46", "Model Town Central Park", "ward_10", 26.8780, 80.9220, "shelter", ["मॉडल टाउन सेंट्रल पार्क"], ["model town central park", "model town park"]),
        ("LM-47", "Model Town Modern Academy", "ward_10", 26.8800, 80.9250, "school", ["मॉडल टाउन मॉडर्न एकेडमी", "मॉडर्न एकेडमी"], ["model town modern academy", "modern academy"]),
        ("LM-48", "Apex Multispeciality Hospital", "ward_10", 26.8760, 80.9200, "hospital", ["एपेक्स मल्टीस्पेशलिटी अस्पताल", "एपेक्स हॉस्पिटल"], ["apex multispeciality hospital", "apex hospital"]),
        ("LM-49", "Model Town Main Market", "ward_10", 26.8820, 80.9240, "market", ["मॉडल टाउन मुख्य बाज़ार", "मॉडल टाउन मार्केट"], ["model town main market", "model town market"]),
        ("LM-50", "Arya Samaj Mandir Model Town", "ward_10", 26.8795, 80.9265, "temple", ["आर्य समाज मंदिर मॉडल टाउन"], ["arya samaj mandir model town", "arya samaj temple"]),

        # Ward 11: Transport Nagar
        ("LM-51", "Interstate Bus Terminal ISBT", "ward_11", 26.8320, 80.9050, "shelter", ["अंतरराज्यीय बस टर्मिनल आईएसबीटी", "बस स्टैंड"], ["interstate bus terminal isbt", "isbt bus terminal", "bus stand"]),
        ("LM-52", "Transport Nagar Flyover", "ward_11", 26.8340, 80.9080, "bridge", ["ट्रांसपोर्ट नगर फ्लाईववर"], ["transport nagar flyover", "transport bridge"]),
        ("LM-53", "Transport Nagar Truck Union Bhawan", "ward_11", 26.8300, 80.9020, "community_hall", ["ट्रक यूनियन भवन"], ["transport nagar truck union bhawan", "truck union"]),
        ("LM-54", "Highway Trauma Care Centre", "ward_11", 26.8360, 80.9060, "hospital", ["हाईवे ट्रॉमा केयर सेंटर", "ट्रॉमा सेंटर"], ["highway trauma care centre", "trauma centre"]),
        ("LM-55", "Transport Nagar Police Station", "ward_11", 26.8315, 80.9095, "police_station", ["ट्रांसपोर्ट नगर पुलिस थाना"], ["transport nagar police station", "transport nagar thana"]),

        # Ward 12: Lake View Enclave
        ("LM-56", "Moti Jheel Lake Promenade", "ward_12", 26.8890, 80.9620, "ghat", ["मोती झील प्रोमेनेड", "मोती झील"], ["moti jheel lake promenade", "moti jheel"]),
        ("LM-57", "Lake View Govt High School", "ward_12", 26.8910, 80.9650, "school", ["लेक व्यू सरकारी हाई स्कूल"], ["lake view govt high school", "lake view school"]),
        ("LM-58", "Lake View Community Shelter", "ward_12", 26.8870, 80.9590, "shelter", ["लेक व्यू कम्युनिटी शेल्टर"], ["lake view community shelter", "lake view shelter"]),
        ("LM-59", "Moti Jheel Health Wellness Clinic", "ward_12", 26.8930, 80.9630, "hospital", ["मोती झील वेलनेस क्लिनिक"], ["moti jheel health wellness clinic", "moti jheel clinic"]),
        ("LM-60", "Lake View Police Post", "ward_12", 26.8885, 80.9665, "police_station", ["लेक व्यू पुलिस चौकी"], ["lake view police post", "moti jheel chowki"]),
    ]

    landmarks = []
    for lm in raw_landmarks:
        landmarks.append({
            "id": lm[0],
            "name": lm[1],
            "ward_id": lm[2],
            "lat": lm[3],
            "lng": lm[4],
            "category": lm[5],
            "aliases_hi": lm[6],
            "aliases_en": lm[7]
        })

    # Exactly 40 flood incidents
    incidents = [
        # 1-10: Critical rescues and medical crises (High urgency)
        {
            "id": "INC-001",
            "type": "rescue",
            "ward_id": "ward_3",
            "landmark_id": "LM-11",
            "lat": 26.8392, "lng": 80.9415,
            "people": 8,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T07:15:00Z",
            "description": "Rising water reaching second floor of residential house near Ram Ghat. 3 children and 2 elderly family members trapped on terrace.",
            "sample_reports": [
                {"lang": "hi", "text": "राम घाट के पास पानी पहली मंजिल तक आ गया है, छत पर 8 लोग फंसे हैं जिनमें 3 बच्चे और 2 बुजुर्ग हैं। तुरंत नाव भेजो!"},
                {"lang": "hinglish", "text": "Ram ghat ke pass paani 1st floor tak chad gaya hai, chhat par 8 log fase hain, bachhe aur bujurg sath hain please rescue boat bhejo."},
                {"lang": "en", "text": "Flood water entering 1st floor near Ram Ghat. 8 people including 3 children and 2 elderly stranded on rooftop, urgent boat needed."}
            ]
        },
        {
            "id": "INC-002",
            "type": "medical",
            "ward_id": "ward_1",
            "landmark_id": "LM-01",
            "lat": 26.8452, "lng": 80.9325,
            "people": 3,
            "vulnerable": {"child": False, "elderly": True, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "stranded",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T07:25:00Z",
            "description": "Diabetic elderly patient suffering acute insulin shock, house marooned with chest-deep water outside Sangam Primary School.",
            "sample_reports": [
                {"lang": "hi", "text": "संगम प्राइमरी स्कूल के पास बुजुर्ग पिता को इंसुलिन का दौरा पड़ रहा है। बाहर सीने तक पानी है, एम्बुलेंस नहीं आ सकती।"},
                {"lang": "hinglish", "text": "Sangam school ke paas father diabetic hain aur behosh ho rahe hain, bahar chest deep pani hai rescue chahiye."},
                {"lang": "en", "text": "Elderly father having severe diabetic emergency near Sangam Primary School, house surrounded by chest-deep flood water."}
            ]
        },
        {
            "id": "INC-003",
            "type": "medical",
            "ward_id": "ward_2",
            "landmark_id": "LM-06",
            "lat": 26.8523, "lng": 80.9253,
            "people": 4,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": True, "medical_need": True},
            "hazard": "stranded",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T07:40:00Z",
            "description": "Pregnant woman in active labor stranded on upper floor behind Gandhi High School, road submerged under 4 feet water.",
            "sample_reports": [
                {"lang": "hi", "text": "गांधी हाई स्कूल के पीछे मेरी पत्नी लेबर पेन में हैं, सड़क पर 4 फुट पानी है, तुरंत बोट या मेडिकल हेल्प चाहिए!"},
                {"lang": "hinglish", "text": "Gandhi high school ke peeche pregnant lady ko labor pain start ho gaya hai, road par 4 feet paani hai rescue team bhejo."},
                {"lang": "en", "text": "Pregnant woman in full labor trapped behind Gandhi High School, road inundated with 4ft water. Urgent medical boat."}
            ]
        },
        {
            "id": "INC-004",
            "type": "rescue",
            "ward_id": "ward_12",
            "landmark_id": "LM-56",
            "lat": 26.8894, "lng": 80.9625,
            "people": 12,
            "vulnerable": {"child": True, "elderly": False, "disabled": True, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T08:00:00Z",
            "description": "Lake overflowed into ground floor apartment near Moti Jheel Promenade; 1 wheelchair-bound person and 4 children trapped.",
            "sample_reports": [
                {"lang": "hi", "text": "मोती झील का पानी घरों में घुस गया है। 12 लोग फंसे हैं, एक दिव्यांग व्यक्ति व्हीलचेयर पर है और 4 बच्चे हैं।"},
                {"lang": "hinglish", "text": "Moti jheel ka bandh toot gaya, Lake view me 12 log fase hain, ek disabled bhai hain wheelchair par. Jaldi bacha lo."},
                {"lang": "en", "text": "Lake embankment breached near Moti Jheel. 12 people stranded including 1 wheelchair user and 4 small kids. Water rising rapidly."}
            ]
        },
        {
            "id": "INC-005",
            "type": "rescue",
            "ward_id": "ward_4",
            "landmark_id": "LM-16",
            "lat": 26.8612, "lng": 80.9155,
            "people": 6,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T08:15:00Z",
            "description": "Partial wall collapse near Ghanta Ghar in Old Bazaar, water gushing inside residential lane with strong current.",
            "sample_reports": [
                {"lang": "hi", "text": "घंटा घर के पास मकान की पिछली दीवार गिर गई है, तेज बहाव में 6 लोग छत पर हैं।"},
                {"lang": "hinglish", "text": "Ghanta ghar old bazaar me diwar gir gayi hai, pani tez hai 6 log fase hain terrace pe."},
                {"lang": "en", "text": "Wall collapsed near Clock Tower old bazaar due to rushing flood water, 6 people clinging to roof terrace."}
            ]
        },
        {
            "id": "INC-006",
            "type": "medical",
            "ward_id": "ward_7",
            "landmark_id": "LM-31",
            "lat": 26.8255, "lng": 80.9655,
            "people": 2,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "injury",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T08:30:00Z",
            "description": "Electric shock and deep laceration from floating debris near Thermal Power Colony Gate, heavy bleeding.",
            "sample_reports": [
                {"lang": "hi", "text": "पावर प्लांट कॉलोनी गेट के पास एक युवक को करंट और लोहे की चादर से गहरा कट लगा है, खून बहुत बह रहा है!"},
                {"lang": "hinglish", "text": "Thermal power plant gate ke paas injury hui hai, heavy bleeding ho rahi hai boat ambulance urgently chahiye."},
                {"lang": "en", "text": "Severe laceration and electrical shock near Power Plant Gate, severe bleeding, urgent paramedic boat."}
            ]
        },
        {
            "id": "INC-007",
            "type": "rescue",
            "ward_id": "ward_3",
            "landmark_id": "LM-12",
            "lat": 26.8415, "lng": 80.9442,
            "people": 5,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T08:45:00Z",
            "description": "Slum cluster beneath Hanuman Setu Bridge submerged, 5 people clinging to bridge pillars in strong river current.",
            "sample_reports": [
                {"lang": "hi", "text": "हनुमान सेतु पुल के नीचे 5 लोग खंभे से लटके हुए हैं, पानी बहुत तेज है, तुरंत मोटर बोट भेजो!"},
                {"lang": "hinglish", "text": "Hanuman setu ke neeche 5 log pillar pakad ke khade hain, paani bohot fast hai please save them."},
                {"lang": "en", "text": "5 people trapped on Hanuman Setu bridge pillars, flood current violent, urgent motorized rescue boat."}
            ]
        },
        {
            "id": "INC-008",
            "type": "medical",
            "ward_id": "ward_5",
            "landmark_id": "LM-22",
            "lat": 26.8502, "lng": 80.9554,
            "people": 7,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "stranded",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T09:00:00Z",
            "description": "Oxygen cylinder running out for elderly asthma patient stranded 200m from St. Jude Hospital, approach road cut off.",
            "sample_reports": [
                {"lang": "hi", "text": "सेंट ज्यूड अस्पताल के पास घर में बुजुर्ग मरीज का ऑक्सीजन सिलेंडर खत्म होने वाला है, सड़क डूबी है!"},
                {"lang": "hinglish", "text": "St Jude hospital ke paas oxygen cylinder khatam ho raha hai 1 ghante me, road par paani hai."},
                {"lang": "en", "text": "Oxygen running out in 1 hour for critical respiratory patient stranded near St. Jude Hospital."}
            ]
        },
        {
            "id": "INC-009",
            "type": "rescue",
            "ward_id": "ward_11",
            "landmark_id": "LM-51",
            "lat": 26.8324, "lng": 80.9055,
            "people": 15,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T09:15:00Z",
            "description": "Stranded intercity bus submerged up to windows near ISBT terminal, 15 passengers on bus roof with water still rising.",
            "sample_reports": [
                {"lang": "hi", "text": "आईएसबीटी बस स्टैंड के पास बस की छत पर 15 यात्री बैठे हैं, बस आधी डूब चुकी है!"},
                {"lang": "hinglish", "text": "ISBT bus terminal pe bus ki chhat par 15 passengers baithe hain, paani window se upar hai rescue chahiye."},
                {"lang": "en", "text": "Submerged bus near ISBT Bus Terminal, 15 passengers stranded on roof with water rising to roof level."}
            ]
        },
        {
            "id": "INC-010",
            "type": "rescue",
            "ward_id": "ward_8",
            "landmark_id": "LM-36",
            "lat": 26.8725, "lng": 80.9485,
            "people": 9,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "critical",
            "reported_at": "2026-10-12T09:30:00Z",
            "description": "Low-lying residential row behind Green Park Stadium submerged to 6 feet, family stranded on rooftop shade.",
            "sample_reports": [
                {"lang": "hi", "text": "ग्रीन पार्क स्टेडियम के पीछे 9 लोग टिन शेड पर बैठे हैं, नीचे 6 फुट पानी भर गया है।"},
                {"lang": "hinglish", "text": "Green park stadium ke peeche 9 log tin shed par baithe hain, 6 feet water, bachhe ro rahe hain."},
                {"lang": "en", "text": "Family of 9 stranded on tin roof behind Green Park Stadium, water level at 6 feet and rising."}
            ]
        },

        # 11-24: High urgency incidents (medical needs, children, rising water, food depletion)
        {
            "id": "INC-011",
            "type": "food",
            "ward_id": "ward_2",
            "landmark_id": "LM-07",
            "lat": 26.8542, "lng": 80.9284,
            "people": 18,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T09:45:00Z",
            "description": "Group of 18 shopkeepers and residents marooned on first floor above Gandhi Nagar Market, zero drinking water for 24 hours.",
            "sample_reports": [
                {"lang": "hi", "text": "गांधी नगर मार्केट की पहली मंजिल पर 18 लोग फंसे हैं, पीने का पानी खत्म हो गया है, बच्चे प्यासे हैं।"},
                {"lang": "hinglish", "text": "Gandhi nagar market me 18 log hain, 24 ghante se drinking water aur khana nahi hai, please relief packet bhejo."},
                {"lang": "en", "text": "18 people stranded on 1st floor of Gandhi Nagar market with no drinking water or food for 24 hours."}
            ]
        },
        {
            "id": "INC-012",
            "type": "medical",
            "ward_id": "ward_9",
            "landmark_id": "LM-41",
            "lat": 26.8584, "lng": 80.9753,
            "people": 4,
            "vulnerable": {"child": False, "elderly": True, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T10:00:00Z",
            "description": "Elderly cardiac patient requires daily blood pressure and heart medication, stranded in home near Subhash Chowk.",
            "sample_reports": [
                {"lang": "hi", "text": "सुभाष चौक के पास बुजुर्ग माताजी को बीपी और दिल की दवाइयां चाहिए, पानी के कारण घर से निकलना मुमकिन नहीं।"},
                {"lang": "hinglish", "text": "Subhash chowk ke paas heart patient hain, dawa khatam ho gayi hai waterlogging ki wajah se pharmacy band hai."},
                {"lang": "en", "text": "Cardiac medication needed urgently for elderly patient near Subhash Chowk, stranded due to street flooding."}
            ]
        },
        {
            "id": "INC-013",
            "type": "shelter",
            "ward_id": "ward_1",
            "landmark_id": "LM-02",
            "lat": 26.8468, "lng": 80.9344,
            "people": 22,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T10:15:00Z",
            "description": "Kachha houses inundated in Sangam Vihar, 22 displaced residents sheltered in Mata Mandir veranda with rising flood waters.",
            "sample_reports": [
                {"lang": "hi", "text": "माता मंदिर संगम विहार के बरामदे में 22 बेघर लोग बैठे हैं, मंदिर के आंगन में भी पानी आने लगा है, शेल्टर शिफ्ट करें।"},
                {"lang": "hinglish", "text": "Mata mandir sangam vihar me 22 log temporary sharan liye hain, courtyard me pani badh raha hai evacuation chahiye."},
                {"lang": "en", "text": "22 displaced flood victims sheltered in Mata Mandir veranda, compound starting to flood, need shelter transfer."}
            ]
        },
        {
            "id": "INC-014",
            "type": "rescue",
            "ward_id": "ward_6",
            "landmark_id": "LM-29",
            "lat": 26.8692, "lng": 80.9365,
            "people": 5,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": True, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "high",
            "reported_at": "2026-10-12T10:30:00Z",
            "description": "Caretaker quarters near St. Mary Convent School submerged up to 4 feet; pregnant caretaker and 2 children stranded.",
            "sample_reports": [
                {"lang": "hi", "text": "सेंट मैरी स्कूल के पास केयरटेकर क्वार्टर में 4 फुट पानी है, गर्भवती महिला और 2 बच्चे फंसे हैं।"},
                {"lang": "hinglish", "text": "St Mary school ke caretaker house me paani ghus gaya hai, pregnant lady hai boat se nikalo."},
                {"lang": "en", "text": "Quarters flooded near St. Mary Convent, pregnant mother and 2 children require boat evacuation."}
            ]
        },
        {
            "id": "INC-015",
            "type": "food",
            "ward_id": "ward_10",
            "landmark_id": "LM-46",
            "lat": 26.8782, "lng": 80.9224,
            "people": 14,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T10:45:00Z",
            "description": "Apartment ground floor flooded around Model Town Central Park, 14 residents trapped without electricity and potable water.",
            "sample_reports": [
                {"lang": "hi", "text": "मॉडल टाउन सेंट्रल पार्क के पास अपार्टमेंट में 14 लोग फंसे हैं, बिजली और पीने का पानी नहीं है।"},
                {"lang": "hinglish", "text": "Model town park ke bagal wali building me 14 log hain, no power, drinking water bottles and dry rations needed."},
                {"lang": "en", "text": "14 residents marooned in apartment near Model Town Central Park, food packets and potable water urgently requested."}
            ]
        },
        {
            "id": "INC-016",
            "type": "rescue",
            "ward_id": "ward_7",
            "landmark_id": "LM-33",
            "lat": 26.8234, "lng": 80.9625,
            "people": 11,
            "vulnerable": {"child": False, "elderly": False, "disabled": True, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "high",
            "reported_at": "2026-10-12T11:00:00Z",
            "description": "Factory workers stranded in dormitory behind Industrial Community Hall, industrial drain overflowed with foul contaminated water.",
            "sample_reports": [
                {"lang": "hi", "text": "मजदूर कल्याण भवन के पीछे नाले का केमिकल युक्त पानी 5 फुट भर गया है, 11 मजदूर फंसे हैं।"},
                {"lang": "hinglish", "text": "Industrial community hall ke peeche nala overflow hua, toxic water hai 11 log trapped hain please evacuate."},
                {"lang": "en", "text": "Contaminated floodwater inundating worker barracks near Industrial Community Hall. 11 workers require rescue."}
            ]
        },
        {
            "id": "INC-017",
            "type": "food",
            "ward_id": "ward_4",
            "landmark_id": "LM-17",
            "lat": 26.8632, "lng": 80.9174,
            "people": 30,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T11:15:00Z",
            "description": "Community kitchen in Old Bazaar flooded; 30 displaced shop workers and families taking shelter in Jama Masjid complex need food rations.",
            "sample_reports": [
                {"lang": "hi", "text": "जामा मस्जिद पुराना बाज़ार में 30 लोग शरण लिए हुए हैं, खाना-पीना खत्म हो गया है, राशन पैकेट भिजवाएं।"},
                {"lang": "hinglish", "text": "Jama masjid old bazaar me 30 log hain jinme bachhe aur bujurg hain, food and water supply immediately needed."},
                {"lang": "en", "text": "30 displaced flood victims sheltered in Jama Masjid complex in Old Bazaar require immediate dry food rations."}
            ]
        },
        {
            "id": "INC-018",
            "type": "medical",
            "ward_id": "ward_11",
            "landmark_id": "LM-53",
            "lat": 26.8304, "lng": 80.9025,
            "people": 3,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "injury",
            "urgency_band": "high",
            "reported_at": "2026-10-12T11:30:00Z",
            "description": "Mechanic suffered compound leg fracture from slipping in flood current outside Truck Union Bhawan, road inaccessible by car.",
            "sample_reports": [
                {"lang": "hi", "text": "ट्रक यूनियन भवन के पास पानी में फिसलने से मैकेनिक का पैर टूट गया है, हड्डी बाहर आ गई है, फर्स्ट एड और बोट चाहिए।"},
                {"lang": "hinglish", "text": "Truck union ke paas leg fracture hua hai bahut dard me hai, road doobi hai ambulance boat bhejiye."},
                {"lang": "en", "text": "Compound leg fracture outside Truck Union Bhawan, patient in severe shock, urgent boat transport to hospital."}
            ]
        },
        {
            "id": "INC-019",
            "type": "rescue",
            "ward_id": "ward_5",
            "landmark_id": "LM-23",
            "lat": 26.8464, "lng": 80.9515,
            "people": 8,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "high",
            "reported_at": "2026-10-12T11:45:00Z",
            "description": "School staff family and children stranded in residential quarters behind Shanti Nagar School, ground floor inundated.",
            "sample_reports": [
                {"lang": "hi", "text": "शांति नगर स्कूल के स्टाफ क्वार्टर में पानी घुस गया है, 8 लोग जिनमें 5 बच्चे हैं छत पर हैं।"},
                {"lang": "hinglish", "text": "Shanti nagar school quarters me paani ghus gaya hai, 8 people with 5 children stranded on roof."},
                {"lang": "en", "text": "Staff residential quarters flooded behind Shanti Nagar School, 8 people including 5 children need rescue."}
            ]
        },
        {
            "id": "INC-020",
            "type": "food",
            "ward_id": "ward_12",
            "landmark_id": "LM-57",
            "lat": 26.8912, "lng": 80.9654,
            "people": 25,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T12:00:00Z",
            "description": "25 villagers taking refuge on upper terrace of Lake View Govt School, water surrounding building, milk and baby food needed.",
            "sample_reports": [
                {"lang": "hi", "text": "लेक व्यू सरकारी स्कूल की छत पर 25 लोग हैं, छोटे बच्चों के लिए दूध और पीने का पानी नहीं है।"},
                {"lang": "hinglish", "text": "Lake view govt school terrace pe 25 people marooned hain, baby food and drinking water packet urgently needed."},
                {"lang": "en", "text": "25 flood refugees on terrace of Lake View High School, acute shortage of baby food and drinking water."}
            ]
        },
        {
            "id": "INC-021",
            "type": "medical",
            "ward_id": "ward_8",
            "landmark_id": "LM-38",
            "lat": 26.8714, "lng": 80.9513,
            "people": 2,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "injury",
            "urgency_band": "high",
            "reported_at": "2026-10-12T12:15:00Z",
            "description": "Child developed 104F fever and convulsions in flooded alley 300m from Green Park CHC, road impassable.",
            "sample_reports": [
                {"lang": "hi", "text": "ग्रीन पार्क अस्पताल के पास 4 साल के बच्चे को 104 बुखार और झटके आ रहे हैं, गली में कमर तक पानी है।"},
                {"lang": "hinglish", "text": "Green park chc ke paas kid has 104 fever and seizures, waist deep water please send medical boat."},
                {"lang": "en", "text": "High fever and seizure emergency for 4yo child near Green Park CHC, street flooded waist-deep."}
            ]
        },
        {
            "id": "INC-022",
            "type": "rescue",
            "ward_id": "ward_9",
            "landmark_id": "LM-42",
            "lat": 26.8603, "lng": 80.9784,
            "people": 7,
            "vulnerable": {"child": True, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "water_rising",
            "urgency_band": "high",
            "reported_at": "2026-10-12T12:30:00Z",
            "description": "Water overflowing from Subhash canal into residential block near Netaji Subhash College, water rising 3 inches per hour.",
            "sample_reports": [
                {"lang": "hi", "text": "सुभाष कॉलेज के पास नहर का पानी घरों में आ रहा है, हर घंटे पानी बढ़ रहा है, 7 लोग फंसे हैं।"},
                {"lang": "hinglish", "text": "Subhash inter college ke pass canal overflow ho gaya, water is rising 3 inches per hr, 7 people need rescue."},
                {"lang": "en", "text": "Canal overflow inundating houses near Subhash College, water rising rapidly, 7 residents need evacuation."}
            ]
        },
        {
            "id": "INC-023",
            "type": "shelter",
            "ward_id": "ward_6",
            "landmark_id": "LM-26",
            "lat": 26.8653, "lng": 80.9354,
            "people": 16,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T12:45:00Z",
            "description": "Shanties flooded behind Collectorate compound, 16 residents sheltering under plastic tarpaulins in strong rain.",
            "sample_reports": [
                {"lang": "hi", "text": "कलेक्ट्रेट ऑफिस के पीछे झुग्गियां डूब गईं, 16 लोग बारिश में भीग रहे हैं, तिरपाल और शेल्टर चाहिए।"},
                {"lang": "hinglish", "text": "Collectorate civil lines ke peeche slums flooded, 16 people without roof in rain, need shelter transfer."},
                {"lang": "en", "text": "Slum shanties flooded behind Collectorate in Civil Lines, 16 displaced people need immediate shelter."}
            ]
        },
        {
            "id": "INC-024",
            "type": "food",
            "ward_id": "ward_3",
            "landmark_id": "LM-13",
            "lat": 26.8374, "lng": 80.9395,
            "people": 20,
            "vulnerable": {"child": False, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "high",
            "reported_at": "2026-10-12T13:00:00Z",
            "description": "20 boatmen and community workers marooned at Riverfront Boat Club jetty, food packets needed.",
            "sample_reports": [
                {"lang": "hi", "text": "बोट क्लब घाट पर 20 नाविक और कर्मचारी फंसे हैं, खाना खत्म हो गया है, भोजन पैकेट भिजवाएं।"},
                {"lang": "hinglish", "text": "Riverfront boat club jetty pe 20 log cut off hain, no cooked food available since morning."},
                {"lang": "en", "text": "20 boat operators and volunteers cut off at Riverfront Boat Club jetty require cooked food packets."}
            ]
        },

        # 25-34: Medium urgency incidents (water surrounded, supplies low, safe for now)
        {
            "id": "INC-025",
            "type": "food",
            "ward_id": "ward_2",
            "landmark_id": "LM-08",
            "lat": 26.8512, "lng": 80.9234,
            "people": 6,
            "vulnerable": {"child": False, "elderly": True, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T13:15:00Z",
            "description": "Safe on first floor near Ram Mandir Gandhi Nagar, but water 2ft on road, grocery stores shut, food supplies low.",
            "sample_reports": [
                {"lang": "hi", "text": "गांधी नगर राम मंदिर के पास पहली मंजिल पर सुरक्षित हैं लेकिन नीचे 2 फुट पानी है, घर में राशन कम है।"},
                {"lang": "hinglish", "text": "Ram mandir gandhi nagar ke paas safe on 1st floor, road has 2ft water, ration needed in next 24 hours."},
                {"lang": "en", "text": "Family safe on upper floor near Ram Mandir Gandhi Nagar, road flooded 2ft, dry rations requested."}
            ]
        },
        {
            "id": "INC-026",
            "type": "shelter",
            "ward_id": "ward_8",
            "landmark_id": "LM-39",
            "lat": 26.8757, "lng": 80.9493,
            "people": 8,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T13:30:00Z",
            "description": "Ground floor water seepage in basement shops near Green Park Shopping Complex, shop owners need dry storage.",
            "sample_reports": [
                {"lang": "hi", "text": "ग्रीन पार्क मार्केट में बेसमेंट दुकानों में पानी टपक रहा है, सामान बचाने के लिए शेल्टर या तिरपाल चाहिए।"},
                {"lang": "hinglish", "text": "Green park shopping complex basement seepage, need tarpaulin sheets and dry space to keep inventory."},
                {"lang": "en", "text": "Basement seepage near Green Park Shopping Complex, traders require tarpaulin and dry storage space."}
            ]
        },
        {
            "id": "INC-027",
            "type": "info",
            "ward_id": "ward_11",
            "landmark_id": "LM-52",
            "lat": 26.8342, "lng": 80.9083,
            "people": 1,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T13:45:00Z",
            "description": "Inquiry regarding whether Transport Nagar Flyover is open for emergency traffic and light vehicles.",
            "sample_reports": [
                {"lang": "hi", "text": "क्या ट्रांसपोर्ट नगर फ्लाईववर चालू है या पानी की वजह से बंद कर दिया गया है? जानकारी चाहिए।"},
                {"lang": "hinglish", "text": "Transport nagar flyover open hai kya ambulance aur private car ke liye? Please clarify."},
                {"lang": "en", "text": "Requesting confirmation if Transport Nagar Flyover is submerged or accessible for light vehicles."}
            ]
        },
        {
            "id": "INC-028",
            "type": "food",
            "ward_id": "ward_5",
            "landmark_id": "LM-24",
            "lat": 26.8517, "lng": 80.9538,
            "people": 12,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T14:00:00Z",
            "description": "Langar kitchen at Shanti Nagar Gurudwara running low on flour and cooking gas while feeding 200 neighbors.",
            "sample_reports": [
                {"lang": "hi", "text": "शांति नगर गुरुद्वारा लंगर में आटा और एलपीजी खत्म होने वाली है, आस-पास के 200 लोगों को भोजन दे रहे हैं।"},
                {"lang": "hinglish", "text": "Shanti nagar gurudwara langar kitchen needs wheat flour and gas cylinder refill to continue food distribution."},
                {"lang": "en", "text": "Community kitchen at Shanti Nagar Gurudwara requires bulk wheat flour and cooking gas supplies."}
            ]
        },
        {
            "id": "INC-029",
            "type": "medical",
            "ward_id": "ward_10",
            "landmark_id": "LM-50",
            "lat": 26.8797, "lng": 80.9268,
            "people": 2,
            "vulnerable": {"child": False, "elderly": True, "disabled": False, "pregnant": False, "medical_need": True},
            "hazard": "none",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T14:15:00Z",
            "description": "Elderly couple near Arya Samaj Mandir needs routine prescription refill for hypertension and arthritis.",
            "sample_reports": [
                {"lang": "hi", "text": "मॉडल टाउन आर्य समाज मंदिर के पास बुजुर्गों की बीपी की दवाई खत्म है, पानी भरा होने से मेडिकल स्टोर बंद है।"},
                {"lang": "hinglish", "text": "Arya samaj mandir model town ke paas regular BP medicine delivery needed for senior citizen couple."},
                {"lang": "en", "text": "Routine medicine delivery requested for elderly couple near Arya Samaj Mandir Model Town."}
            ]
        },
        {
            "id": "INC-030",
            "type": "shelter",
            "ward_id": "ward_9",
            "landmark_id": "LM-44",
            "lat": 26.8617, "lng": 80.9743,
            "people": 10,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T14:30:00Z",
            "description": "10 construction workers displaced from temporary sheds near Subhash Nagar Barat Ghar, need blankets and dry shelter.",
            "sample_reports": [
                {"lang": "hi", "text": "सुभाष नगर बारात घर के पास मजदूरों की झुग्गियों में पानी भर गया, 10 लोग खुले में हैं, कंबल चाहिए।"},
                {"lang": "hinglish", "text": "Subhash barat ghar ke paas 10 construction laborers need dry shelter space and blankets."},
                {"lang": "en", "text": "10 construction workers need dry shelter and blankets near Subhash Nagar Barat Ghar."}
            ]
        },
        {
            "id": "INC-031",
            "type": "food",
            "ward_id": "ward_1",
            "landmark_id": "LM-03",
            "lat": 26.8483, "lng": 80.9314,
            "people": 15,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T14:45:00Z",
            "description": "Sangam Community Hall sheltering 15 people, drinking water supply running low, water cans requested.",
            "sample_reports": [
                {"lang": "hi", "text": "संगम कम्युनिटी हॉल में 15 लोग हैं, पीने के पानी के कैंपर खत्म हो गए हैं, कृपया पानी भिजवाएं।"},
                {"lang": "hinglish", "text": "Sangam community hall has 15 people sheltered, drinking water cans needed by evening."},
                {"lang": "en", "text": "Drinking water cans needed for 15 sheltered persons at Sangam Community Hall."}
            ]
        },
        {
            "id": "INC-032",
            "type": "rescue",
            "ward_id": "ward_4",
            "landmark_id": "LM-20",
            "lat": 26.8608, "lng": 80.9188,
            "people": 3,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "stranded",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T15:00:00Z",
            "description": "3 shopkeepers safe on mezzanine floor of cloth shop in Sarafa Market, water 2.5 ft in lane, request evacuation when possible.",
            "sample_reports": [
                {"lang": "hi", "text": "सराफा मार्केट में कपड़े की दुकान के मेज़ानाइन पर 3 लोग सुरक्षित हैं, जब नाव खाली हो तो निकालें।"},
                {"lang": "hinglish", "text": "Sarafa cloth market me 3 shopkeepers mezzanine pe hain, 2.5 ft water, non-urgent boat evacuation requested."},
                {"lang": "en", "text": "3 shopkeepers stranded on mezzanine in Sarafa cloth market, water 2.5ft, non-critical boat assist requested."}
            ]
        },
        {
            "id": "INC-033",
            "type": "info",
            "ward_id": "ward_6",
            "landmark_id": "LM-28",
            "lat": 26.8638, "lng": 80.9333,
            "people": 1,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T15:15:00Z",
            "description": "Civil Lines Metro station inquiry regarding operational status of trains towards East Riverbend.",
            "sample_reports": [
                {"lang": "hi", "text": "क्या सिविल लाइन्स मेट्रो स्टेशन से ट्रेनें चल रही हैं या ट्रैक पर पानी है? कृपया जानकारी दें।"},
                {"lang": "hinglish", "text": "Civil lines metro station se metro service functional hai kya East Riverbend side?"},
                {"lang": "en", "text": "Seeking information regarding Metro operations from Civil Lines station."}
            ]
        },
        {
            "id": "INC-034",
            "type": "shelter",
            "ward_id": "ward_12",
            "landmark_id": "LM-58",
            "lat": 26.8873, "lng": 80.9593,
            "people": 18,
            "vulnerable": {"child": True, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "medium",
            "reported_at": "2026-10-12T15:30:00Z",
            "description": "Lake View Community Shelter capacity reached (50/50), 18 new evacuees outside building need redirection to adjacent shelter.",
            "sample_reports": [
                {"lang": "hi", "text": "लेक व्यू शेल्टर पूरा भर गया है, बाहर 18 लोग खड़े हैं, इन्हें किस दूसरे शेल्टर में भेजें?"},
                {"lang": "hinglish", "text": "Lake view community shelter is at max capacity, 18 people waiting outside need redirection info."},
                {"lang": "en", "text": "Lake View Shelter full, 18 newly arrived evacuees need relocation to secondary facility."}
            ]
        },

        # 35-40: Low urgency incidents (info, minor inquiries, safe higher ground)
        {
            "id": "INC-035",
            "type": "info",
            "ward_id": "ward_3",
            "landmark_id": "LM-14",
            "lat": 26.8423, "lng": 80.9463,
            "people": 1,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "low",
            "reported_at": "2026-10-12T15:45:00Z",
            "description": "Resident reporting current flood gauge level at Ganga Darshan Ghat is 1.2 meters above danger mark.",
            "sample_reports": [
                {"lang": "hi", "text": "गंगा दर्शन घाट पर जलस्तर खतरे के निशान से 1.2 मीटर ऊपर है, सूचना दर्ज करें।"},
                {"lang": "hinglish", "text": "Water level gauge reading at Ganga Darshan Ghat is 1.2m above red mark, logging status."},
                {"lang": "en", "text": "Reporting water level reading at Ganga Darshan Viewpoint as 1.2m over danger mark."}
            ]
        },
        {
            "id": "INC-036",
            "type": "info",
            "ward_id": "ward_2",
            "landmark_id": "LM-10",
            "lat": 26.8508, "lng": 80.9298,
            "people": 1,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "low",
            "reported_at": "2026-10-12T16:00:00Z",
            "description": "Inquiry whether parking lot at Gandhi Nagar Metro Station is inundated.",
            "sample_reports": [
                {"lang": "hi", "text": "गांधी नगर मेट्रो स्टेशन की पार्किंग में पानी भरा है क्या? गाड़ी खड़ी कर सकते हैं?"},
                {"lang": "hinglish", "text": "Is Gandhi nagar metro station parking waterlogged?"},
                {"lang": "en", "text": "Asking if Gandhi Nagar metro parking is flooded or safe for vehicle."}
            ]
        },
        {
            "id": "INC-037",
            "type": "shelter",
            "ward_id": "ward_8",
            "landmark_id": "LM-40",
            "lat": 26.8703, "lng": 80.9468,
            "people": 4,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "low",
            "reported_at": "2026-10-12T16:15:00Z",
            "description": "Volunteers at Shiv Mandir Green Park offer hall space for up to 30 flood evacuees if needed.",
            "sample_reports": [
                {"lang": "hi", "text": "शिव मंदिर ग्रीन पार्क की धर्मशाला में 30 लोगों के रुकने की जगह खाली है, अगर जरूरत हो तो बताएं।"},
                {"lang": "hinglish", "text": "Shiv mandir green park dharamshala has capacity for 30 evacuees, offering space to administration."},
                {"lang": "en", "text": "Shiv Mandir Green Park committee offering hall space for 30 displaced people."}
            ]
        },
        {
            "id": "INC-038",
            "type": "info",
            "ward_id": "ward_7",
            "landmark_id": "LM-34",
            "lat": 26.8214, "lng": 80.9704,
            "people": 1,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "low",
            "reported_at": "2026-10-12T16:30:00Z",
            "description": "Freight train movement status inquiry around Railway Freight Yard Phase 1.",
            "sample_reports": [
                {"lang": "hi", "text": "रेलवे फ्रेट यार्ड फेज़ 1 के ट्रैक पर पानी नहीं है, मालगाड़ी खड़ी है।"},
                {"lang": "hinglish", "text": "Railway freight yard tracks are dry as of 4:30pm."},
                {"lang": "en", "text": "Railway Freight Yard Phase 1 reports tracks are currently dry."}
            ]
        },
        {
            "id": "INC-039",
            "type": "food",
            "ward_id": "ward_10",
            "landmark_id": "LM-49",
            "lat": 26.8823, "lng": 80.9244,
            "people": 5,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "low",
            "reported_at": "2026-10-12T16:45:00Z",
            "description": "Model Town grocery merchants association reports adequate wheat, rice and oil in wholesale stock.",
            "sample_reports": [
                {"lang": "hi", "text": "मॉडल टाउन मुख्य बाज़ार में किराना व्यापारियों के पास पर्याप्त राशन उपलब्ध है।"},
                {"lang": "hinglish", "text": "Model town main market has sufficient grocery wholesale stock available."},
                {"lang": "en", "text": "Model Town market association confirms sufficient grain stocks available for relief procurement."}
            ]
        },
        {
            "id": "INC-040",
            "type": "info",
            "ward_id": "ward_12",
            "landmark_id": "LM-60",
            "lat": 26.8888, "lng": 80.9668,
            "people": 1,
            "vulnerable": {"child": False, "elderly": False, "disabled": False, "pregnant": False, "medical_need": False},
            "hazard": "none",
            "urgency_band": "low",
            "reported_at": "2026-10-12T17:00:00Z",
            "description": "Lake View Police Post reports perimeter road around Moti Jheel blocked by fallen tree.",
            "sample_reports": [
                {"lang": "hi", "text": "लेक व्यू पुलिस चौकी के पास मोती झील की सड़क पर पेड़ गिर गया है, रास्ता बंद है।"},
                {"lang": "hinglish", "text": "Tree fallen on road near Lake View police post, blocking vehicle movement around Moti Jheel."},
                {"lang": "en", "text": "Fallen tree blocking roadway near Lake View Police Post, requires municipal clearance team."}
            ]
        }
    ]

    dataset = {
        "version": "1.0.0",
        "scenario_pack": "flood",
        "city": city,
        "wards": wards,
        "landmarks": landmarks,
        "incidents": incidents
    }

    out_dir = Path("data/synthetic/flood_v1")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "seeds.yaml"

    with open(out_file, "w", encoding="utf-8") as f:
        yaml.dump(dataset, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"Generated {out_file} successfully:")
    print(f"  City: {city['name']}")
    print(f"  Wards: {len(wards)}")
    print(f"  Landmarks: {len(landmarks)}")
    print(f"  Incidents: {len(incidents)}")

if __name__ == "__main__":
    generate_seeds()
