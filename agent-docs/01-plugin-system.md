# Plugin Sistemi Analizi

## Kontrat
- `StudioPlugin` `typing.Protocol`; sadece `id: str` + `activate(api)` zorunlu (`plugin_system.py:543-546`)
- Katkılar `frozen=True` dataclass: Panel/Workspace/Tool/Action Contribution
- `provides` opsiyonel dict ile versiyon beyanı; yoksa sağlayıcı listesine girmez

## Versiyon Karşılaştırma
- Üç mod: `*` veya boş = her şey, `^X.Y.Z` = caret semantiği, geri kalanı strict eşitlik
- Sadece 3 parçalı `MAJOR.MINOR.PATCH` tuple karşılaştırma; pre-release/build metadata yok

## Keşif ve Yükleme
- İki aşamalı: `pkgutil.iter_modules` (paket içi) + `importlib.metadata.entry_points` (üçüncü parti)
- Hatalar `PluginLoadIssue(source, message)` olarak toplanır; plugin çökse bile shell ayakta kalır
- Yükleme sırası deterministik değil (explicit `order` sadece Workspace'te)

## StudioAPI Yüzeyi
- UI katkıları: `add_panel`, `add_workspace`, `add_action`, `register_tool`
- Veri/davranış: `register_component_editor/kind_editor`, `register_component_icon/kind_icon`, `register_geometry_provider`, `set_project_requirement_checker`
- Plugin'lere doğrudan Qt nesnesi (QWidget factory, QUndoStack) erişimi açık
- Event bus callback-list tabanlı: `on_project_changed`, `on_selection_changed` vb.

## Görev Alanı Ayrımı
- Yapısal "UI plugin vs hesaplama plugin" ayrımı yok; hepsi eşit statüde
- Tek plugin birden fazla katkı tipi kaydedebilir (örn. electrical_propulsion: 6 editor + 6 icon + 1 workspace + 3 panel + 1 tool)
- Plugin'ler arası iletişim: sadece event bus + paylaşılan `project.data` dict

## Yaşam Döngüsü
- `deactivate`/geri çekme public API'si yok; plugin instance bellekte kalıcı
- Pending queue pattern: workspace/action handler geç bağlansa bile birikim + flush var (panel'de yok, hata fırlatır)

## Degraded Mode
- `check_project_requirements` eksik/uyumsuz plugin'i tespit eder, `project.plugin_issues`'a yazar
- Ancak UI'da kullanıcıya gösterge yok — `check_project_requirements` çağrısı var, sonucunu render eden iz yok

## Güçlü Yönler
- Kontrat yüzeyi minimal; Protocol ile structural typing (miras gereksiz)
- İki aşamalı keşif + hata toplama → kısmi başarısızlık tolere edilir
- Editor fallback zinciri: type → kind → None
- Undo/redo deep-copy snapshot ile editörleri etkilemeden çalışır

## Gelişime Açık Yönler
- Versiyon çözümleyici PEP 440 /4-parça / build metadata desteklemiyor
- Yükleme sırası deterministik değil; panel/tool için explicit order yok
- Degraded mode UI göstergesi (banner/status bar) eksik
- `deactivate`/katkı sökme public API'si yok
- Plugin'ler arası koordinasyon için resmi mekanizma yok