# Kalan Analiz Alanları

## Plugin Author Guide & Şablon (Faz 1.3 detayı)
- Üçüncü parti geliştiriciler için eksiksiz rehber şart (açık kaynak + kapalı kaynak plugin ayrımı)
- Rehber içeriği: kontrat, `provides` semantiği, contribution tipleri, event bus kullanımı, undo/redo entegrasyonu
- Çalışan minimal plugin şablonu (`src/setuav_studio/plugins/_template/`) → isim değiştirip başla
- Şablonda olması gerekenler: `PLUGIN` instance, `activate(api)`, en az 1 panel + 1 editor + 1 icon kaydı
- README + pyproject entry_points örneği şablona dahil
- Bağımlılık: yok (Faz 1.1 ile paralel)
- Risk: düşük

## PyThrust Entegrasyonu
- Mevcut kullanım: motor/prop veritabanı `electrical_propulsion/database.py` üzerinden okunuyor
- İncelenmesi gerekenler:
  - DB erişim pattern'i (sync/async, retry, lock)
  - Önbellek invalidation stratejisi (`_MOTOR_DB`/`_PROP_DB` cache reset edilemiyor)
  - Path resolution (hardcoded `/home/huseyin/dev/setware/PyThrust/data` → konfig edilebilir)
  - Versiyon senkronizasyonu (PyThrust sürümü ile uyum)
- Tek soru: motor/prop editörleri PyThrust'u live mı kullanıyor, yoksa cache snapshot mu?
- Bağımlılık: Faz 5.17 (hardcoded yol temizliği) ile bağlantılı

## Cross-Platform Test
- Qt davranışı Windows/Mac/Linux farkları (font rendering, dock float davranışı, file dialog)
- PySide6 sürüm kilidi: `>=6.8,<7` → sürüm yükseltmesi breaking change riski
- PyThrust ve diğer native bağımlılıkların platform-specific build durumu
- Packaging: PyInstaller/uv/bundling kararı verilmemiş (todo'da CI/CD ile bağlantılı)
- Test altyapısı: GitHub Actions matrix (`ubuntu-latest`, `windows-latest`, `macos-latest`) kurulumu
- Bağımlılık: Faz 1.2 (fixture) sonrası

## Runtime / Performans Profili
- Mevcut darboğaz adayı: `_on_run_analysis` UI thread (Faz 5.15)
- Profiling aracı kararı: `cProfile`, `py-spy`, veya `Scalene` → seçim yapılmamış
- Ölçülmesi gereken metrikler:
  - Solver iterasyon süresi (sweep/throttle/operating_point modları)
  - Geometry build (`build_project_geometry` 130 satır, 5 nested if)
  - Undo/redo deep-copy maliyeti (her editör çağrısında)
  - Plugin discovery cold-start süresi
- Baseline alınmalı, sonra her refactor'da regression kontrolü
- Bağımlılık: Faz 5.15 (thread migration) öncesi baseline şart

## CI/CD Yapısı (todo'da)
- todo.md'de "ci-cd" maddesi var, kapsamı netleşmemiş
- Pipeline önerisi:
  - Lint (ruff) + tip kontrol (mypy)
  - Unit + integration testler (pytest)
  - Cross-platform build matrix
  - Plugin author guide lint (yeni plugin PR'lerinde şablon uyumu)
- Schema drift gate (Faz 4.12) buraya entegre edilmeli
- Release artifact: wheel + sıkıştırılmış bundle (PyInstaller?)
- Bağımlılık: Faz 1.2 (conftest) + Faz 4.12 (drift detector)

## Yeni Plugin Yol Haritası (todo'dan)
Henüz kod yok, mimari rehberlik gerekiyor:
- **aerodinamik plugin** → `register_geometry_provider` + hesaplama motoru; OpenVSP/AVL/XFLR5 entegrasyonu kararı
- **ağırlık ve denge plugin** → component mass toplama, CG hesabı, moment of inertia
- **uçuş mekaniği plugin** → performance çıktısı (stall speed, range, endurance); solver'ı kapsar
- **VTOL roadmap** → multicopter + tiltrotor config tipleri
- **multicopter roadmap** → motor frame, ESC, pervane düzeni (rotor disk analizi)

Her biri için Faz 1.3 plugin şablonundan türetilebilir; ortak `register_geometry_provider` deseni kullanmalı.

## Dokümantasyon Açıkları
- README.md minimal (sadece plugin-based tanım + todo listesi)
- Modül/sınıf docstring'leri karışık (Faz 3 kod kalitesi bulgusu)
- Plugin API reference dokümanı yok (Faz 1.3 rehber kapsamında olmalı)
- Architecture diagram yok (CLAUDE.md / docs/architecture.md önerisi)
- Contributing guide yok (3rd party plugin geliştirici için)

## Güvenlik
- Proje dosyaları `.suav` (zip) → zip-bomb / path traversal kontrolü yok (`project.py:147-164`)
- Plugin yükleme entry_points → import side-effect riski (kullanıcı güveni gerekli)
- Externe process çağrısı (Faz 4.13 validator) → subprocess sandbox kararı
- Mevcut kodda auth/secrets yok (local-only uygulama, network yüzeyi minimum)

## Gözlem: Yeni Plugin'ler İçin Öncelik
- aerodinamik → ilk sırada (todo + solver bağımlılığı)
- ağırlık/denge → ikinci (CG uçuş mekaniği için girdi)
- uçuş mekaniği → üçüncü (aerodinamik + ağırlık verisini tüketir)
- VTOL/multicopter → ileri (mevcut sabit kanat altyapısı oturduktan sonra)

## Bağımlılıklar (diğer dökümanlarla)

```
Faz 1.3 (plugin guide) ──► yeni plugin geliştirme (aerodinamik, vb.)
Faz 1.2 (fixture) ──► cross-platform test
Faz 5.15 (solver thread) ──► runtime profiling baseline
Faz 4.12 (drift detector) ──► CI/CD pipeline
```