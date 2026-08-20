# Refactor/Geliştirme Hareket Planı

## Faz 1 — Temel Altyapı (1-2 hafta, düşük risk) ✅ *tamamlandı*
Amaç: Sonraki tüm fazların hızını ve güvenliğini artırmak.

1. **Logging stratejisi kur**
   - Kök logger yapılandırması (`logging.basicConfig` + dosya handler'ı)
   - Plugin discovery, undo/redo, solver run, project open/save → INFO/WARNING
   - `workspace.py`'deki tek logger'ı örnek al
   - Bağımlılık: yok
   - Risk: düşük

2. **Test conftest + fixture temizliği**
   - `conftest.py` ile `TEST_PROJECT_PATH` fixture'a taşınsın
   - `setUp`/`setUpClass` QApplication pattern'i ortak fixture
   - Bağımlılık: yok
   - Risk: düşük

3. **Plugin yazar rehberi dokümanı**
   - `docs/plugin_author_guide.md` → kontrat, provides, contributes, örnekler
   - Bağımlılık: yok
   - Risk: düşük
   - Gerekçe: Açık kaynak + kapalı kaynak plugin ayrımı için zorunlu; üçüncü parti geliştirici net API bekliyor

## Faz 2 — Plugin Sistemi Sağlamlaştırma (2-3 hafta, orta risk)
Amaç: Plugin davranış sınırlarını netleştirmek.

4. **Degraded mode UI göstergesi** ✅ *tamamlandı*
   - Status bar'a kalıcı "⚠ Degraded mode" badge (tıklanabilir, tooltip = eksik pluginler)
   - Tıklama → detay dialog (QMessageBox.warning)
   - `_show_degraded_details` + test (test_main.py)

5. **Plugin deactivate / katkı sökme API'si** ✅ *tamamlandı*
   - `StudioAPI.remove_panel/workspace/action/component_editor/kind_editor/icon/kind_icon/geometry_provider`
   - `StudioPlugin.deactivate(api)` opsiyonel; yoksa no-op (sadece manager kayıtları sökülür)
   - `PluginManager.deactivate(plugin_id)` + `_plugin_providers` takibi (yeniden activate edilebilir)
   - Shell: `_remove_panel`/`_remove_workspace` (bağlı panelleri de söker)/`_remove_action`
   - 3 test: reversible plugin round-trip, no-op davranış, shell üzerinden panel/workspace sökme

6. **Plugin yükleme sırası deterministik** ✅ *tamamlandı*
   - `StudioPlugin.priority: int` (default 100, düşük = önce)
   - Keşif iki aşamalı: candidate topla → `(priority, id)` sırala → tek tek activate
   - Bundled + entry-points aynı sıralama; hata toplama korundu
   - `_candidate_sort_key` + test

7. **Versiyon çözümleyici genişletme** ✅ *tamamlandı*
   - `packaging.version.Version` (PEP 440) → pre-release, build metadata, 4 parça destekleniyor
   - `packaging>=23.0` pyproject.toml'a eklendi
   - Caret semantiği korundu (major/minor/patch kuralları)
   - Geçersiz versiyon → `None` (uyumsuz sayılır)
   - 12 durumluk test

## Faz 3 — Editör Altyapısı (3-4 hafta, orta risk)
Amaç: Kod tekrarını ve editör büyüklüğünü kontrol etmek.

8. **Property table mixin / utility** ✅ *tamamlandı*
   - `src/setuav_studio/ui/property_tables.py` → `PropertyTableMixin` (attribute tabanlı varyasyonlar)
   - 8 sınıf mixin'i kullanıyor: BaseComponentEditor, BatteryEditor, ElectricPropulsionSystemEditor, PropulsionControlsDock, PropulsionResultsDock, FuselageEditor, LiftingSurfaceEditor, ControlSurfaceEditor
   - Ek olarak `ui/` paketi kuruldu; `theme.py` ve `numeric_spinbox.py` `plugins/core`'dan `ui/`'ye taşındı (core plugin artık diğer pluginlere UI bağımlılığı taşımıyor)
   - Bağımlılık: yok
   - Risk: düşük

9. **`_on_run_analysis` parçalama** ✅ *tamamlandı*
   - `_on_run_analysis` → orkestratör: `_build_analysis_context()` + mode dispatch + `_show_feasibility_alert()`
   - Ayrı metotlar: `run_sweep` / `run_throttle` / `run_operating_point` (her biri `_solve_point` → `_solve_rpm` kullanır, `_render_results` ile dock'ları günceller)
   - `_fallback_propeller` (DB fallback verisi), `_solve_rpm` (brentq + rpm_max fallback), `_render_results` (charts + results dock)
   - Bağımlılık: Faz 3.8
   - Risk: orta — integration test (`run_button.click()`) + 3 mod smoke testi doğrulandı

10. **`lifting_surface.py` bölme (2178 → 6 modül)** ✅ *tamamlandı*
    - 5 mixin modülü: `lifting_surface_attachment.py` (AttachmentMixin), `lifting_surface_planform.py` (PlanformMixin), `lifting_surface_profiles.py` (ProfilesMixin + airfoil shaping), `lifting_surface_tip_caps.py` (TipCapsMixin), `lifting_surface_control_surfaces.py` (ControlSurfacesMixin)
    - Ana dosya ~600 satıra indi: `__init__`, genel section, loading, mutations, helpers; MRO: `LiftingSurfaceEditor(PropertyTableMixin, AttachmentMixin, PlanformMixin, ProfilesMixin, TipCapsMixin, ControlSurfacesMixin, QWidget)`
    - Ölü importlar temizlendi (`math`, `QFont`); `CONTROL_SURFACE_TYPES` CS mixin'ine taşındı
    - Bağımlılık: Faz 3.8
    - Risk: orta — 74 test + smoke (attachment/mirror/shaping/tip/parent mutasyonları) doğrulandı

11. **`airfoil_dialog.py` + `fuselage.py` test coverage** ✅ *tamamlandı*
    - 5 AirfoilDialog testi: initial selection (preset adı / NACA kodu / dict spec), preset seçimi + canvas/metrics, 4/5-digit NACA üretimi + radio swap, .dat import (QFileDialog mock + geçici dosya), kategori filtresi + apply/apply-all semantiği
    - 5 FuselageEditor testi: population (general/segments/sections/transform), segment actions (add/duplicate/move/delete), section actions (add/duplicate/move/delete + x interpolasyonu), profile/transform/polygon vertex mutasyonları, general name/mass + segment tag/loft edits
    - Bonus bug: `_update_general` mass spinbox `on_changed` yanlış satır index'i (fuselage row 3→2, lifting_surface row 1→3) — mass düzenleme artık çalışıyor
    - Test sayısı: 74 → 84
    - Bağımlılık: Faz 1.2
    - Risk: düşük

## Faz 4 — Şema Olgunlaşması (devam eden, paralel)
Amaç: Studio ↔ setuav-specification uyumunu güvenceye almak.

12. **Schema drift tespiti (CI gate)** ✅ *tamamlandı — veri-seviyesi gate*
    - Karar: kod-seviyesi AST key toplama çok gürültülü (166/246 yanlış pozitif: Qt ikonları, panel ID'leri, preset adları, analiz çıktıları) → gate veri-seviyesinde kuruldu
    - Şema repoya vendored: `src/setuav_studio/schemas/` (core + org.setuav.core plugin; wheel'e dahil — doğrulandı)
    - Validator vendored: `setuav_studio/schema_validation.py` (`setuav_validator.py`'den adapte; `get_catalog()` paket şemalarından yükler, `validate_project()` kullanılır); `jsonschema>=4.19` + `referencing>=0.30` dependency
    - Örnek proje repoya taşındı: `tests/fixtures/fixed-wing/`; `tests/_common.py` artık repo-içi yol kullanıyor (hardcoded mutlak yol temizlendi)
    - Fixture tüm core component tiplerini kapsıyor: `payload` (point-mass) + `rotor-lift` (rotor) eklendi (9/9 tip)
    - Şema ↔ editör eşitlemesi: lifting-surface şemasına `tip_treatment` (flat/round/sharp/winglet + length, offset_x, winglet_height, cant_angle, winglet_sweep, toe_angle, root_chord_scale, tip_chord_scale), `section_align` (xz/normal), `airfoil_shaping` (te_thickness, thickness_scale, camber_scale), `twist_location` (0-1) ve airfoil coordinates `name` eklendi — fixture'ın 4 drift hatası çözüldü
    - Gate: `tests/test_schema_drift.py` (6 test) — fixture temiz doğrulanmalı, tip kapsama, editor-yazılan key'ler yasal, bilinmeyen key + geçersiz enum reddedilmeli, bilinmeyen plugin tipi sessizce atlanmalı
    - Test sayısı: 84 → 90
    - Bağımlılık: yok (Faz 1.2 ile paralel)
    - Risk: orta (yanlış pozitif olabilir, sürdürülebilirlik için bir araç yatırımı)

13. **Runtime schema validation (kademeli)** ✅ *karar: hybrid + ayar*
    - Proje açılırken `setuav_studio.schema_validation.validate_project` çağrılsın (Faz 4.12 ile vendored, import yeterli — subprocess gerek yok)
    - Kritik hata (yapısal bozuk, eksik required) → dialog "Read-only aç / İptal"
    - Uyarı (additionalProperties, deprecated) → status bar; yazmaya izin ver
    - `StudioSettings.validation_strictness: "strict" | "warn" | "off"`
    - Bağımlılık: Faz 4.12 ✅
    - Risk: orta

14. **Component dataclass modelleri (kademeli)** ✅ *karar: frozen dataclass (Pydantic değil)*
    - `Motor`, `Battery`, `Propeller`, `Fuselage`, `LiftingSurface` → `@dataclass(frozen=True, slots=True)`
    - Validation `__post_init__` veya descriptor ile
    - Editörler dict ↔ dataclass çevirisi yapsın; persistence formatı (JSON) korunsun
    - Bağımlılık: Faz 4.13
    - Risk: yüksek (büyük yüzey, ama uzun vadede zorunlu)
    - Gerekçe: undo/redo her adımda deepcopy → Pydantic overhead gereksiz

## Faz 5 — Performans ve UX (Faz 3 sonrası)
Amaç: Kullanıcı deneyimini iyileştirmek.

15. **Solver'ı UI thread'inden çıkar** ✅ *karar: iptal edilebilir*
    - `QRunnable` + `QThreadPool` pattern'i kur
    - İlk hedef: `_on_run_analysis` (Faz 3.9 ile bağlantılı)
    - `isInterruptionRequested()` ile cancellation token
    - Progress dialog'da "Cancel" butonu; parametre tabloları etkilenmesin
    - İlk versiyonda iptal edildi mesajı; kısmi sonuç opsiyonel (sonra)
    - Bağımlılık: Faz 3.9
    - Risk: orta

16. **Hata yutma noktalarını sıkılaştır**
    - `icons.py:59`, `airfoil.py:479,504`, `controls_dock.py:569`
    - Her birine specific exception + log
    - Bağımlılık: Faz 1.1
    - Risk: düşük

17. **Hardcoded yol temizliği (prod)**
    - `database.py:20` PyThrust yolu → config/settings
    - Bağımlılık: Faz 1.1
    - Risk: düşük

## Bağımlılık Grafiği (özet)

```
Faz 1.1 (log) ──► Faz 2.4, Faz 3.9, Faz 5.16, Faz 5.17
Faz 1.2 (fixture) ──► Faz 2.x, Faz 3.11
Faz 2.4 ──► Faz 2.5
Faz 3.8 ──► Faz 3.9, Faz 3.10
Faz 4.12 ──► Faz 4.13 ──► Faz 4.14
```

## Kararlar (4 açık soru çözüldü)

- **Faz 2.5 — Plugin deactivate:** Evet; contract şimdi, no-op default, hot-reload backend'i sonra
- **Faz 4.12 — Spec plugin namespace:** Tek `org.setuav.core` korunuyor (domain'e bölme yapılmıyor); spec plugin'i = şema dağıtım birimi, Studio plugin'i = kod/UI birimi — ikisi farklı granülerlik
- **Faz 4.13 — Şema ihlali:** Hybrid + ayar; kritik → dialog, uyarı → status bar; `validation_strictness` StudioSettings'te
- **Faz 4.14 — Tip katmanı:** Frozen dataclass (Pydantic değil); undo/redo overhead'i sebebi
- **Faz 5.15 — Solver iptal:** Evet; `isInterruptionRequested()` + Cancel button

## MVP Yaklaşımı (hızlı kazanım istersen)

İlk 30 günde sadece: **1 + 2 + 4 + 8** adımları → düşük riskli, yüksek görünürlüklü iyileştirme. Plugin sistemi görünür şekilde sağlamlaşır, editör duplication'ı düşer.