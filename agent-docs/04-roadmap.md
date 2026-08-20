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

5. **Plugin deactivate / katkı sökme API'si** ✅ *karar: evet, no-op default*
   - `StudioAPI.remove_panel/workspace/action/editor/...`
   - `StudioPlugin.deactivate(self, api)` opsiyonel; yoksa no-op
   - Contract şimdi belirlenir; hot-reload backend'i sonra
   - Test: bir plugin activate → deactivate → yeniden activate
   - Bağımlılık: Faz 2.4
   - Risk: orta

6. **Plugin yükleme sırası deterministik**
   - `Contribution`'a opsiyonel `priority: int` ekle (default 100)
   - `PluginManager` toplama + priority'ye göre sırala
   - Bağımlılık: yok
   - Risk: düşük

7. **Versiyon çözümleyici genişletme**
   - PEP 440 desteği (`packaging.version` zaten standart kütüphane)
   - Pre-release, build metadata, 4 parça versiyon
   - Bağımlılık: yok
   - Risk: düşük

## Faz 3 — Editör Altyapısı (3-4 hafta, orta risk)
Amaç: Kod tekrarını ve editör büyüklüğünü kontrol etmek.

8. **Property table mixin / utility**
   - `_property_table/_set_property_value/_set_property_combo/_property_key/_fit_table_height` tek base/mixin'e
   - Tüm editörler mixin'i kullansın
   - Bağımlılık: yok
   - Risk: düşük
   - Gerekçe: 6+ dosyada neredeyse identical kopya; en yüksek duplication oranı burada

9. **`_on_run_analysis` parçalama**
   - `run_sweep / run_throttle / run_operating_point` ayrı metotlar
   - Her biri `_fallback_data()` / `_solve_rpm()` / `_render_results()` çağırsın
   - Bağımlılık: Faz 3.8
   - Risk: orta (test coverage zayıf, regression riski var)

10. **`lifting_surface.py` bölme (1802 → 4-5 modül)**
    - `profile_table.py`, `control_surface.py` (zaten ayrı dosya), `tip_cap.py`, `attachment.py`
    - Editör bu modülleri compose etsin
    - Bağımlılık: Faz 3.8
    - Risk: orta-yüksek (büyük refactor, test coverage zayıf)

11. **`airfoil_dialog.py` + `fuselage.py` test coverage**
    - UI testleri (pytest-qt ekle) veya state-mutation testleri
    - Bağımlılık: Faz 1.2
    - Risk: düşük

## Faz 4 — Şema Olgunlaşması (devam eden, paralel)
Amaç: Studio ↔ setuav-specification uyumunu güvenceye almak.

12. **Schema drift tespiti (CI gate)**
    - Studio'daki tüm string-literal key'leri topla (`segments`, `profile.type`, vb.)
    - setuav-specification şemalarıyla karşılaştır
    - PR reddet: eklenen yeni key şemada yoksa
    - Bağımlılık: yok (Faz 1.2 ile paralel)
    - Risk: orta (yanlış pozitif olabilir, sürdürülebilirlik için bir araç yatırımı)

13. **Runtime schema validation (kademeli)** ✅ *karar: hybrid + ayar*
    - Proje açılırken `setuav_validator.py` çağrılsın (subprocess veya import)
    - Kritik hata (yapısal bozuk, eksik required) → dialog "Read-only aç / İptal"
    - Uyarı (additionalProperties, deprecated) → status bar; yazmaya izin ver
    - `StudioSettings.validation_strictness: "strict" | "warn" | "off"`
    - Bağımlılık: Faz 4.12
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
- **Faz 4.13 — Şema ihlali:** Hybrid + ayar; kritik → dialog, uyarı → status bar; `validation_strictness` StudioSettings'te
- **Faz 4.14 — Tip katmanı:** Frozen dataclass (Pydantic değil); undo/redo overhead'i sebebi
- **Faz 5.15 — Solver iptal:** Evet; `isInterruptionRequested()` + Cancel button

## MVP Yaklaşımı (hızlı kazanım istersen)

İlk 30 günde sadece: **1 + 2 + 4 + 8** adımları → düşük riskli, yüksek görünürlüklü iyileştirme. Plugin sistemi görünür şekilde sağlamlaşır, editör duplication'ı düşer.