"""Bulk drug templates for 1000+ row demo formulary (offline, no external download).

Each entry: cn, en, trade, atc, rxcui, form, route, [specs...]
"""
from __future__ import annotations

# ATC class -> list of (中文通用名, 英文INN, 商品名前缀, RxCUI or "")
# Specs are appended per drug in build script based on form type.

ATC_DRUG_SEED: dict[str, list[tuple[str, str, str, str]]] = {
    "B01": [  # 抗血栓
        ("利伐沙班", "rivaroxaban", "拜瑞妥", "1114195"), ("达比加群", "dabigatran", "泰毕全", "1037042"),
        ("阿哌沙班", "apixaban", "艾乐妥", "1364430"), ("依度沙班", "edoxaban", "艾多沙班", "1599537"),
        ("替格瑞洛", "ticagrelor", "倍林达", "1116632"), ("普拉格雷", "prasugrel", "Effient", "854856"),
        ("西洛他唑", "cilostazol", "Pletal", "21107"), ("双嘧达莫", "dipyridamole", "潘生丁", "3521"),
        ("贝米肝素", "bemiparin", "Badyket", "1364347"), ("达肝素", "dalteparin", "法安明", "67109"),
        ("磺达肝癸", "fondaparinux", "Arixtra", "321208"), ("阿加曲班", "argatroban", "Argatroban", "15202"),
        ("降纤酶", "defibrase", "降纤酶", ""), ("尿激酶", "urokinase", "尿激酶", "11052"),
        ("阿替普酶", "alteplase", "爱通立", "8410"), ("瑞替普酶", "reteplase", "瑞替普酶", "82122"),
    ],
    "C01": [  # 心脏治疗
        ("硝酸异山梨酯", "isosorbide dinitrate", "异舒吉", "6057"), ("单硝酸异山梨酯", "isosorbide mononitrate", "欣康", "1364433"),
        ("尼可地尔", "nicorandil", "喜格迈", "7407"), ("曲美他嗪", "trimetazidine", "万爽力", "10829"),
        ("伊伐布雷定", "ivabradine", "可兰特", "1649480"), ("雷诺嗪", "ranolazine", "Ranexa", "358274"),
        ("丙吡胺", "disopyramide", "Norpace", "3648"), ("奎尼丁", "quinidine", "奎尼丁", "9068"),
        ("普鲁卡因胺", "procainamide", "普鲁卡因胺", "8703"), ("氟卡尼", "flecainide", "Tambocor", "4441"),
        ("普罗帕酮", "propafenone", "心律平", "8754"), ("索他洛尔", "sotolol", "Betapace", "9947"),
        ("多非利特", "dofetilide", "Tikosyn", "49299"), ("决奈达隆", "dronedarone", "Multaq", "233698"),
        ("洋地黄毒苷", "digitoxin", "Digitoxin", "3406"), ("米力农", "milrinone", "Primacor", "6963"),
        ("氨力农", "amrinone", "Inocor", "738"), ("左西孟旦", "levosimendan", "Simdax", "237884"),
    ],
    "C02": [  # 抗高血压
        ("可乐定", "clonidine", "可乐定", "2599"), ("甲基多巴", "methyldopa", "Aldomet", "6876"),
        ("肼屈嗪", "hydralazine", "Apresoline", "5470"), ("米诺地尔", "minoxidil", "Rogaine", "6980"),
        ("乌拉地尔", "urapidil", "Ebrantil", "108575"), ("多沙唑嗪", "doxazosin", "Cardura", "3639"),
        ("哌唑嗪", "prazosin", "Minipress", "8629"), ("布尼洛尔", "bunolol", "Bunol", "1827"),
        ("卡维地洛", "carvedilol", "络德", "20352"), ("拉贝洛尔", "labetalol", "Trandate", "6185"),
        ("阿替洛尔", "atenolol", "Tenormin", "1202"), ("普萘洛尔", "propranolol", "心得安", "8787"),
        ("奈必洛尔", "nebivolol", "Bystolic", "31555"), ("阿齐沙坦", "azilsartan", "Edarbi", "1091643"),
        ("奥美沙坦", "olmesartan", "Benicar", "321064"), ("坎地沙坦", "candesartan", "Atacand", "214354"),
    ],
    "C03": [  # 利尿
        ("布美他尼", "bumetanide", "Bumex", "1828"), ("依他尼酸", "ethacrynic acid", "Edecrin", "4107"),
 ("托伐普坦", "tolvaptan", "Samsca", "358274"), ("氢氯噻嗪", "hydrochlorothiazide", "双氢克尿噻", "5487"),
        ("吲达帕胺", "indapamide", "寿比山", "5764"), ("美托拉宗", "metolazone", "Zaroxolyn", "6912"),
        ("氨苯蝶啶", "triamterene", "Dyrenium", "10763"), ("阿米洛利", "amiloride", "Midamor", "644"),
        ("乙酰唑胺", "acetazolamide", "Diamox", "167"), ("甘露醇", "mannitol", "甘露醇", "6623"),
        ("甘油果糖", "glycerol fructose", "甘油果糖", ""), ("托拉塞米", "torsemide", "特苏尼", "38409"),
    ],
    "C07": [  # β阻滞剂
        ("艾司洛尔", "esmolol", "Brevibloc", "4119"), ("倍他洛尔", "betaxolol", "Betoptic", "1511"),
        ("比索洛尔", "bisoprolol", "康忻", "19484"), ("卡维地洛", "carvedilol", "络德", "20352"),
        ("美托洛尔", "metoprolol", "倍他乐克", "6918"), ("普萘洛尔", "propranolol", "心得安", "8787"),
        ("阿替洛尔", "atenolol", "Tenormin", "1202"), ("拉贝洛尔", "labetalol", "Trandate", "6185"),
        ("奈必洛尔", "nebivolol", "Bystolic", "31555"), ("塞利洛尔", "celiprolol", "Celiprolol", "2145"),
    ],
    "C08": [  # 钙拮抗
        ("维拉帕米", "verapamil", "Isoptin", "11170"), ("地尔硫䓬", "diltiazem", "合心爽", "3443"),
        ("尼群地平", "nitrendipine", "尼群地平", "7408"), ("拉西地平", "lacidipine", "乐息平", "6185"),
        ("乐卡地平", "lercanidipine", "Lercan", "237884"), ("贝尼地平", "benidipine", "Coniel", "236473"),
        ("西尼地平", "cinidipine", "Atelec", ""), ("氨氯地平", "amlodipine", "络活喜", "17767"),
        ("硝苯地平", "nifedipine", "拜新同", "7417"), ("非洛地平", "felodipine", "波依定", "4316"),
    ],
    "C09": [  # RAAS
        ("雷米普利", "ramipril", "Altace", "35208"), ("福辛普利", "fosinopril", "Monopril", "4441"),
        ("依那普利", "enalapril", "Vasotec", "3827"), ("贝那普利", "benazepril", "洛汀新", "18867"),
        ("培哚普利", "perindopril", "雅施达", "54552"), ("缬沙坦", "valsartan", "代文", "69749"),
        ("厄贝沙坦", "irbesartan", "安博维", "83818"), ("替米沙坦", "telmisartan", "美卡素", "73494"),
        ("坎地沙坦", "candesartan", "Atacand", "214354"), ("奥美沙坦", "olmesartan", "Benicar", "321064"),
        ("沙库巴曲缬沙坦", "sacubitril valsartan", "诺欣妥", "1656339"), ("螺内酯", "spironolactone", "安体舒通", "9997"),
        ("依普利酮", "eplerenone", "Inspra", "298869"), ("阿利吉仑", "aliskiren", "Tekturna", "32592"),
    ],
    "C10": [  # 调脂
        ("普伐他汀", "pravastatin", "美百乐镇", "42463"), ("氟伐他汀", "fluvastatin", "来适可", "4441"),
        ("匹伐他汀", "pitavastatin", "Livalo", "861634"), ("依折麦布", "ezetimibe", "益适纯", "341248"),
        ("非诺贝特", "fenofibrate", "力平之", "8703"), ("吉非贝齐", "gemfibrozil", "Lopid", "4719"),
        ("苯扎贝特", "bezafibrate", "Bezalip", "1511"), ("ω-3脂肪酸", "omega 3 acid ethyl esters", "Omtryg", "4301"),
        ("依洛尤单抗", "evolocumab", "Repatha", "1599839"), ("阿利西尤单抗", "alirocumab", "Praluent", "1658638"),
    ],
    "A10": [  # 降糖
        ("格列吡嗪", "glipizide", "Glucotrol", "4814"), ("格列喹酮", "gliquidone", "Glurenorm", "4815"),
        ("格列美脲", "glimepiride", "Amaryl", "25789"), ("瑞格列奈", "repaglinide", "诺和龙", "73044"),
        ("那格列奈", "nateglinide", "Starlix", "236443"), ("吡格列酮", "pioglitazone", "Actos", "33738"),
        ("罗格列酮", "rosiglitazone", "Avandia", "153165"), ("阿卡波糖", "acarbose", "拜唐苹", "166"),
        ("伏格列波糖", "voglibose", "Basen", "236782"), ("米格列醇", "miglitol", "Glyset", "6963"),
        ("利格列汀", "linagliptin", "Tradjenta", "1100699"), ("沙格列汀", "saxagliptin", "Onglyza", "857974"),
        ("维格列汀", "vildagliptin", "Galvus", "596554"), ("阿格列汀", "alogliptin", "Nesina", "1368001"),
        ("恩格列净", "empagliflozin", "Jardiance", "1545653"), ("卡格列净", "canagliflozin", "Invokana", "1373458"),
        ("艾塞那肽", "exenatide", "Byetta", "60548"), ("司美格鲁肽", "semaglutide", "Ozempic", "1991302"),
        ("德谷胰岛素", "insulin degludec", "Tresiba", "1670007"), ("门冬胰岛素", "insulin aspart", "诺和锐", "51428"),
        ("赖脯胰岛素", "insulin lispro", "Humalog", "86009"), ("精蛋白锌胰岛素", "insulin nph", "万苏林", "5856"),
    ],
    "J01": [  # 抗细菌
        ("头孢唑啉", "cefazolin", "先锋V", "2180"), ("头孢拉定", "cefradine", "先锋VI", "2230"),
        ("头孢羟氨苄", "cefadroxil", "Duricef", "2179"), ("头孢孟多", "cefamandole", "Mandol", "2181"),
        ("头孢美唑", "cefmetazole", "Zefazone", "2188"), ("头孢西丁", "cefoxitin", "Mefoxin", "2192"),
        ("头孢噻肟", "cefotaxime", "Claforan", "2186"), ("头孢哌酮", "cefoperazone", "先锋必", "2185"),
        ("头孢地尼", "cefdinir", "Omnicef", "2178"), ("头孢泊肟", "cefpodoxime", "Vantin", "2190"),
        ("头孢丙烯", "cefprozil", "Cefzil", "2191"), ("利奈唑胺", "linezolid", "Zyvox", "190376"),
        ("万古霉素", "vancomycin", "稳可信", "11124"), ("替考拉宁", "teicoplanin", "Targocid", "10627"),
        ("达托霉素", "daptomycin", "Cubicin", "22299"), ("替加环素", "tigecycline", "Tygacil", "384455"),
        ("多黏菌素B", "polymyxin b", "Polymyxin B", "8536"), ("黏菌素", "colistin", "Colistin", "2709"),
        ("磷霉素", "fosfomycin", "Monurol", "4441"), ("呋喃妥因", "nitrofurantoin", "Macrodantin", "7454"),
        ("利福平", "rifampin", "Rifadin", "9384"), ("利福喷丁", "rifapentine", "Priftin", "35636"),
        ("异烟肼", "isoniazid", "Isoniazid", "6038"), ("乙胺丁醇", "ethambutol", "Myambutol", "4119"),
        ("吡嗪酰胺", "pyrazinamide", "Pyrazinamide", "8687"), ("链霉素", "streptomycin", "Streptomycin", "10109"),
    ],
    "J02": [  # 抗真菌
        ("伊曲康唑", "itraconazole", "Sporanox", "28031"), ("泊沙康唑", "posaconazole", "Noxafil", "282446"),
        ("卡泊芬净", "caspofungin", "Cancidas", "140108"), ("米卡芬净", "micafungin", "Mycamine", "280790"),
        ("两性霉素B", "amphotericin b", "Fungizone", "7833"), ("制霉素", "nystatin", "Mycostatin", "7597"),
        ("特比萘芬", "terbinafine", "Lamisil", "10603"), ("克霉唑", "clotrimazole", "Canesten", "2623"),
        ("咪康唑", "miconazole", "Monistat", "6932"), ("酮康唑", "ketoconazole", "Nizoral", "6135"),
    ],
    "J05": [  # 抗病毒
        ("更昔洛韦", "ganciclovir", "Cytovene", "4678"), ("缬更昔洛韦", "valganciclovir", "Valcyte", "275891"),
        ("阿昔洛韦", "acyclovir", "Zovirax", "281"), ("伐昔洛韦", "valacyclovir", "Valtrex", "73645"),
        ("泛昔洛韦", "famciclovir", "Famvir", "114477"), ("拉米夫定", "lamivudine", "Epivir", "68244"),
        ("恩替卡韦", "entecavir", "Baraclude", "284520"), ("替诺福韦", "tenofovir", "Viread", "259966"),
        ("索磷布韦", "sofosbuvir", "Sovaldi", "1484911"), ("达卡他韦", "daclatasvir", "Daklinza", "1597128"),
        ("奈玛特韦利托那韦", "nirmatrelvir ritonavir", "Paxlovid", "2587895"), ("瑞德西韦", "remdesivir", "Veklury", "2284718"),
    ],
    "N02": [  # 镇痛
        ("可待因", "codeine", "Codeine", "2670"), ("氢可酮", "hydrocodone", "Vicodin", "5489"),
        ("羟考酮", "oxycodone", "OxyContin", "7804"), ("哌替啶", "meperidine", "Demerol", "6754"),
        ("喷他佐辛", "pentazocine", "Talwin", "8013"), ("布托啡诺", "butorphanol", "Stadol", "1841"),
        ("纳布啡", "nalbuphine", "Nubain", "7238"), ("氟比洛芬", "flurbiprofen", "Ansaid", "4441"),
        ("酮咯酸", "ketorolac", "Toradol", "6130"), ("萘普生", "naproxen", "Aleve", "7258"),
        ("吲哚美辛", "indomethacin", "Indocin", "5781"), ("美洛昔康", "meloxicam", "Mobic", "41493"),
        ("艾瑞昔布", "imrecoxib", "恒扬", ""), ("帕瑞昔布", "parecoxib", "特耐", "279645"),
        ("加巴喷丁", "gabapentin", "Neurontin", "25480"), ("普瑞巴林", "pregabalin", "Lyrica", "187832"),
    ],
    "N03": [  # 抗癫痫
        ("苯妥英", "phenytoin", "Dilantin", "8183"), ("乙琥胺", "ethosuximide", "Zarontin", "4135"),
        ("拉莫三嗪", "lamotrigine", "Lamictal", "28439"), ("奥卡西平", "oxcarbazepine", "Trileptal", "32624"),
        ("托吡酯", "topiramate", "Topamax", "38404"), ("唑尼沙胺", "zonisamide", "Zonegran", "108575"),
        ("卢非酰胺", "rufinamide", "Banzel", "662304"), ("吡仑帕奈", "perampanel", "Fycompa", "1373478"),
        ("拉考酰胺", "lacosamide", "Vimpat", "623400"), ("艾司利卡西平", "eslicarbazepine", "Aptiom", "1040053"),
    ],
    "N05": [  # 精神
        ("氯丙嗪", "chlorpromazine", "Thorazine", "2403"), ("奋乃静", "perphenazine", "Trilafon", "8013"),
        ("氟哌啶醇", "haloperidol", "Haldol", "5093"), ("氯氮平", "clozapine", "Clozaril", "2626"),
        ("阿立哌唑", "aripiprazole", "Abilify", "89013"), ("帕利哌酮", "paliperidone", "Invega", "679314"),
        ("齐拉西酮", "ziprasidone", "Geodon", "115698"), ("氨磺必利", "amisulpride", "Solian", "46307"),
        ("丁螺环酮", "buspirone", "Buspar", "1827"), ("坦度螺酮", "tandospirone", "Sediel", ""),
        ("米氮平", "mirtazapine", "Remeron", "15996"), ("曲唑酮", "trazodone", "Desyrel", "10737"),
        ("伏硫西汀", "vortioxetine", "Trintellix", "1455099"), ("度洛西汀", "duloxetine", "Cymbalta", "72625"),
    ],
    "N06": [  # 抗抑郁
        ("帕罗西汀", "paroxetine", "Paxil", "32937"), ("氟伏沙明", "fluvoxamine", "Luvox", "4441"),
        ("西酞普兰", "citalopram", "Celexa", "2556"), ("安非他酮", "bupropion", "Wellbutrin", "1827"),
        ("阿戈美拉汀", "agomelatine", "Valdoxan", "662301"), ("米那普仑", "milnacipran", "Savella", "352372"),
    ],
    "A02": [  # 抗酸/PPI
        ("兰索拉唑", "lansoprazole", "Prevacid", "17128"), ("艾司奥美拉唑", "esomeprazole", "耐信", "283742"),
        ("右兰索拉唑", "dexlansoprazole", "Dexilant", "816346"), ("法莫替丁", "famotidine", "Pepcid", "4278"),
        ("雷尼替丁", "ranitidine", "Zantac", "9143"), ("西咪替丁", "cimetidine", "Tagamet", "25480"),
        ("枸橼酸铋钾", "bismuth potassium citrate", "丽珠得乐", ""), ("胶体果胶铋", "colloidal bismuth pectin", "胶体果胶铋", ""),
    ],
    "A03": [  # 胃肠动力
        ("莫沙必利", "mosapride", "Gasmotin", ""), ("伊托必利", "itopride", "Ganaton", ""),
        ("匹维溴铵", "pinaverium", "Dicetel", ""), ("奥替溴铵", "otilonium", "Spasmomen", ""),
    ],
    "R03": [  # 呼吸
        ("特布他林", "terbutaline", "Bricanyl", "10368"), ("异丙托溴铵", "ipratropium", "Atrovent", "7213"),
        ("噻托溴铵", "tiotropium", "Spiriva", "69120"), ("福莫特罗", "formoterol", "Foradil", "4441"),
        ("沙美特罗", "salmeterol", "Serevent", "36108"), ("茚达特罗", "indacaterol", "Arcapta", "1040053"),
        ("茶碱", "theophylline", "Theo-Dur", "10438"), ("多索茶碱", "doxofylline", "Ansimar", ""),
        ("羧甲司坦", "carbocisteine", "Mucodyne", ""), ("厄多司坦", "erdosteine", "Erdotin", ""),
        ("孟鲁司特", "montelukast", "顺尔宁", "88249"), ("扎鲁司特", "zafirlukast", "Accolate", "114979"),
    ],
    "H02": [  # 皮质类固醇
        ("氢化可的松", "hydrocortisone", "Hydrocortone", "5492"), ("曲安奈德", "triamcinolone", "Kenalog", "10759"),
        ("倍他米松", "betamethasone", "Celestone", "1511"), ("氟轻松", "fluocinolone", "Synalar", "4441"),
        ("布地奈德", "budesonide", "Pulmicort", "19831"), ("氟替卡松", "fluticasone", "Flonase", "41126"),
        ("莫米松", "mometasone", "Nasonex", "108575"), ("环索奈德", "ciclesonide", "Alvesco", "597731"),
    ],
    "L01": [  # 肿瘤
        ("卡铂", "carboplatin", "Paraplatin", "2001"), ("奥沙利铂", "oxaliplatin", "乐沙定", "32592"),
        ("多西他赛", "docetaxel", "Taxotere", "3640"), ("紫杉醇", "paclitaxel", "泰素", "56946"),
        ("吉西他滨", "gemcitabine", "Gemzar", "4719"), ("培美曲塞", "pemetrexed", "Alimta", "68446"),
        ("伊立替康", "irinotecan", "Camptosar", "236473"), ("依托泊苷", "etoposide", "VePesid", "4179"),
        ("环磷酰胺", "cyclophosphamide", "Cytoxan", "3002"), ("异环磷酰胺", "ifosfamide", "Ifex", "56946"),
        ("多柔比星", "doxorubicin", "Adriamycin", "3639"), ("表柔比星", "epirubicin", "Ellence", "3992"),
        ("博来霉素", "bleomycin", "Blenoxane", "1622"), ("长春新碱", "vincristine", "Oncovin", "11202"),
        ("来曲唑", "letrozole", "Femara", "72965"), ("阿那曲唑", "anastrozole", "Arimidex", "84857"),
        ("他莫昔芬", "tamoxifen", "Nolvadex", "10324"), ("伊马替尼", "imatinib", "Gleevec", "282388"),
    ],
    "G04": [  # 泌尿
        ("非那雄胺", "finasteride", "保列治", "25025"), ("度他雄胺", "dutasteride", "Avodart", "236473"),
        ("坦索罗辛", "tamsulosin", "哈乐", "77492"), ("多沙唑嗪", "doxazosin", "Cardura", "3639"),
        ("索利那新", "solifenacin", "卫喜康", "358274"), ("米拉贝格", "mirabegron", "Myrbetriq", "1300786"),
        ("非布司他", "febuxostat", "优立通", "73689"), ("苯溴马隆", "benzbromarone", "Benur", ""),
    ],
    "M01": [  # 肌肉骨骼
        ("萘普生", "naproxen", "Aleve", "7258"), ("吡罗昔康", "piroxicam", "Feldene", "8356"),
        ("氯诺昔康", "lornoxicam", "Xefo", ""), ("艾瑞昔布", "imrecoxib", "恒扬", ""),
        ("秋水仙碱", "colchicine", "Colcrys", "2683"), ("别嘌醇", "allopurinol", "Zyloprim", "519"),
        ("丙磺舒", "probenecid", "Benemid", "8694"), ("骨化三醇", "calcitriol", "Rocaltrol", "1894"),
        ("阿仑膦酸钠", "alendronate", "Fosamax", "4603"), ("唑来膦酸", "zoledronic acid", "Reclast", "77682"),
    ],
    "B03": [  # 血液
        ("硫酸亚铁", "ferrous sulfate", "Feosol", "4441"), ("琥珀酸亚铁", "ferrous succinate", "速力菲", ""),
        ("叶酸", "folic acid", "Folvite", "4511"), ("维生素B12", "cyanocobalamin", "Nascobal", "11248"),
        ("促红素", "epoetin alfa", "Epogen", "105694"), ("达依泊汀", "darbepoetin alfa", "Aranesp", "236473"),
        ("罗沙司他", "roxadustat", "Evrenzo", ""), ("铁蔗糖", "iron sucrose", "Venofer", "236782"),
    ],
    "V03": [  # 解毒/辅助
        ("亚甲蓝", "methylene blue", "Urolene Blue", "6876"), ("纳洛酮", "naloxone", "Narcan", "7242"),
        ("氟马西尼", "flumazenil", "Romazicon", "4441"), ("新斯的明", "neostigmine", "Prostigmin", "7514"),
        ("阿托品", "atropine", "Atropine", "1223"), ("东莨菪碱", "scopolamine", "Transderm Scop", "9947"),
        ("二巯丙磺钠", "unithiol", "Unithiol", ""), ("依地酸钙钠", "edetate calcium disodium", "Calcium EDTA", "3640"),
    ],
    "N01": [  # 麻醉
        ("七氟烷", "sevoflurane", "Sevorane", "9919"), ("异氟烷", "isoflurane", "Forane", "6026"),
        ("丙泊酚", "propofol", "Diprivan", "8782"), ("依托咪酯", "etomidate", "Amidate", "4179"),
        ("氯胺酮", "ketamine", "Ketalar", "6130"), ("罗库溴铵", "rocuronium", "Zemuron", "68139"),
        ("维库溴铵", "vecuronium", "Norcuron", "11170"), ("顺阿曲库铵", "cisatracurium", "Nimbex", "259966"),
        ("琥珀胆碱", "succinylcholine", "Anectine", "10154"), ("利多卡因", "lidocaine", "Xylocaine", "6387"),
        ("布比卡因", "bupivacaine", "Marcaine", "1815"), ("罗哌卡因", "ropivacaine", "Naropin", "35780"),
    ],
}

# Default specs per dosage form (Chinese hospital style)
FORM_SPECS: dict[str, list[str]] = {
    "片剂": ["5mg", "10mg", "20mg", "25mg", "50mg", "100mg", "200mg", "500mg"],
    "胶囊": ["0.25g", "0.5g", "0.1g", "0.3g"],
    "肠溶片": ["20mg", "40mg", "100mg"],
    "缓释片": ["25mg", "47.5mg", "100mg"],
    "控释片": ["30mg", "60mg"],
    "注射液": ["1ml", "2ml", "5ml", "10ml", "100ml"],
    "粉针": ["0.5g", "1g", "1.5g"],
    "滴眼液": ["5ml", "10ml"],
    "吸入剂": ["60吸", "120吸"],
    "气雾剂": ["200揿"],
    "软胶囊": ["0.5g", "1g"],
    "散剂": ["3g", "10g"],
    "咀嚼片": ["0.5g"],
    "鼻喷雾": ["60喷", "120喷"],
    "混悬液": ["100ml"],
    "贴膏": ["10cm×14cm"],
}

FORM_ROUTE: dict[str, str] = {
    "片剂": "PO", "胶囊": "PO", "肠溶片": "PO", "缓释片": "PO", "控释片": "PO",
    "注射液": "IV", "粉针": "IV", "滴眼液": "OPH", "吸入剂": "INH", "气雾剂": "INH",
    "软胶囊": "PO", "散剂": "PO", "咀嚼片": "PO", "鼻喷雾": "NAS", "混悬液": "PO", "贴膏": "TOP",
}

# How many spec variants per generated drug (deterministic by hash)
SPECS_PER_DRUG = 3


def iter_generated_templates() -> list[dict]:
    """Expand ATC seed into multi-spec formulary template dicts."""
    out: list[dict] = []
    for atc_prefix, drugs in ATC_DRUG_SEED.items():
        abx = 3 if atc_prefix.startswith("J0") else 0
        for cn, en, trade, rxcui in drugs:
            en = en.lower().strip()
            # Pick form by ATC / name heuristics
            if atc_prefix in {"J01", "J02", "J05", "L01", "V03", "N01"} or "注射" in cn or en.endswith("in") and "mab" in en:
                form = "粉针" if atc_prefix in {"J01", "L01"} else "注射液"
            elif atc_prefix == "R03":
                form = "吸入剂" if "特罗" in cn or "溴铵" in cn else "片剂"
            elif atc_prefix == "A02":
                form = "肠溶片" if "拉唑" in cn else "片剂"
            else:
                form = "片剂"
            route = FORM_ROUTE.get(form, "PO")
            specs = FORM_SPECS.get(form, ["10mg", "20mg", "50mg"])
            # Deterministic pick 3 specs
            idx = abs(hash(en)) % max(1, len(specs) - 2)
            chosen = specs[idx : idx + SPECS_PER_DRUG]
            if len(chosen) < SPECS_PER_DRUG:
                chosen = specs[:SPECS_PER_DRUG]
            high = 1 if atc_prefix in {"B01", "L01", "N01", "N02"} and ("肝素" in cn or "吗啡" in cn or "铂" in cn or "胰岛素" in cn) else 0
            narcotic = 1 if atc_prefix == "N02" and any(x in en for x in ("morphine", "oxycodone", "hydrocodone", "fentanyl")) else 0
            for spec in chosen:
                out.append({
                    "cn": cn,
                    "en": en.lower().strip(),
                    "trade": trade,
                    "spec": spec,
                    "form": form,
                    "route": route,
                    "atc": f"{atc_prefix}XX01"[:7].ljust(7, "0"),
                    "rxcui": rxcui,
                    "high": high,
                    "abx": abx if atc_prefix.startswith("J") else 0,
                    "narcotic": narcotic,
                    "stock": 1,
                })
    return out
