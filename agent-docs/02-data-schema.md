# Veri Şeması Olgunlaşması Analizi

## Şema Tanımı
- Studio: tüm varlıklar raw `dict[str, Any]`; tek tip adacımı `GeometryData/LoftGeometry/Section` (frozen+slots dataclass)
- Komşu repo `../setuav-specification/`: JSON Schema 2020-12 + `$ref` registry + `setuav_validator.py`
- `ProjectDocument.data: dict[str, Any]` JSON olarak yazılıyor

## Tip Güvenliği
- Düz dict yaygın: editörlerin hepsi (`ProjectExplorer`, `BatteryEditor`, `FuselageEditor`...) string literal key kullanıyor
- Tutarsızlık: `transform.position` core'da `{x,y,z}` (fuselage), `roll/pitch/yaw` (lifting-surface); editörler arası key seti karışık
- Schema drift riski yüksek: rename edilirse eski projeler sessizce boş profile/yüklenemeyen geometri olarak açılır

## Validation Katmanı
- `open_project()` sadece JSON decode + dict kontrolü yapıyor; JSON Schema çağrısı yok
- `setuav_validator.py` studio tarafından import edilmiyor, sadece bağımsız CLI
- Studio'nun kendi validasyonu sadece `check_project_requirements` (plugin id/version eşleşmesi)
- Şema ihlalleri sessizce yutuluyor; degraded mode sadece plugin eksikliğinde tetikleniyor

## Komşu Repo İlişkisi
- Doğrudan bağımlılık yok; `pyproject.toml`'da sadece PySide6/qtawesome/setuav-pythrust
- Tüketim: import yok, subprocess yok; testler hardcoded path ile örneklere erişiyor
- Versiyon senkronizasyonu yok → şema değişiklikleri manuel yansıyor

## Çakışma Noktaları
- Editörler `mass`/`name`/`manufacturer` gibi alanları hem bileşene hem `parameters`'a yazıyor; şema `additionalProperties: false` ise validator kırar
- `assembly.members.battery` şemada scalar id, diğerleri liste → Studio doğru tutuyor ama boş üye fallback'i şemayı kırabilir
- Transform key seti tutarsız (fuselage vs lifting-surface)

## Persistence
- `project.py`'de manuel `json.dump`/`loads`; tutarlı (`utf-8`, `ensure_ascii=False`, `indent=2`)
- Atomik yazma: `tempfile.NamedTemporaryFile` + `os.replace` hem JSON hem ZIP için
- Asset: klasör modunda yerinde; arşiv modunda `rglob("*")` ile `.suav`'a kopyalanıyor
- Airfoil preset'leri dört gösterim kabul ediyor (preset adı / NACA string / dosya yolu / obj) → tip ayrımı runtime'da

## Güçlü Yönler
- `GeometryData` katmanı frozen+slots dataclass ile izole, renderer-agnostic
- Persistence atomik ve sağlam (yarım dosya riski yok)
- Plugin mimarisinde basit versiyon eşleştirme ile degraded mode çalışıyor
- Undo/Redo deep-copy snapshot tüm editörleri kapsıyor
- Editör şablonu (`BaseComponentEditor` + `ParameterField`) tutarlı

## Gelişime Açık Yönler
- JSON Schema runtime'da hiç kullanılmıyor; şema-dokümantasyon işlevinde
- Bileşen/assembly anahtarları string literal olarak dağınık; yeni tip için çok dosyada manuel eşleme gerekiyor
- Editörler hesaplanan alanları çift yazıyor (bileşen + parameters) → validator'da potansiyel kırılma
- `parameters` için Pydantic/dataclass model yok; `isinstance(..., dict)` zincirleri artıyor
- Asset yolu çözümlemesi tutarsız; NACA fallback sessiz hata yutuyor