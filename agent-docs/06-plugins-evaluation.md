# Mevcut ve Gelecek Plugin Değerlendirmesi

## Mevcut Pluginler — Feature Matrisi

| Plugin | Component Editor | Icon | Panel | Workspace | Tool | Geometry Provider | DB |
|---|---|---|---|---|---|---|---|
| **core** | instance (kind) | — | 2 (explorer, properties) | — | — | — | — |
| **electrical_propulsion** | 6 (motor, propeller, rotor, esc, battery, system) | 6 | 3 (controls, results, charts) | propulsion | 1 (catalog) | — | PyThrust |
| **geometry** | 3 (fuselage, lifting-surface, control-surface) | 3 | 1 (3D viewer) | design | — | 2 | airfoils (.dat) |

**Notlar:**

- `core` minimal; sadece instance + temel paneller
- `electrical_propulsion` en geniş kapsamlı; solver + chart + editor + DB bir arada
- `geometry` UI ağırlıklı (1802 satır lifting surface editörü); hesaplama ayrı modülde

## Mevcut Pluginlerin Derinlik Değerlendirmesi

**core** (sığ)
- Sadece UI shell, instance ve properties paneli
- Tema/ayarlar var ama bileşen düzenleme yok

**electrical_propulsion** (derin)
- Tam özellik: editör + DB + solver + chart + results dock
- 400 satırlık `_on_run_analysis` UI thread'de → refactor gerek (Faz 5.15)
- Bileşenler arası ilişki (motor-ESC-pervane sistem) doğru modellenmiş

**geometry** (orta-derin)
- 3D viewer + editör + geometry provider tamam
- Airfoil preset'leri (9 profil) bundle'lı
- Lifting surface editörü 1802 satır → bölünmeli (Faz 3.10)
- Loft geometrisi güçlü, profile sampling zayıf

## Gelecek Pluginler (README.md'den)

### Yakın Vade (todo listesinde)
- **aerodinamik plugin** → `register_geometry_provider` (aerodynamic surfaces, CL/CD dağılımı)
- **ağırlık ve denge plugin** → component mass aggregation, CG hesabı, moment of inertia
- **uçuş mekaniği plugin** → performance çıktıları (stall, range, endurance); solver burada

### İleri Vade (todo listesinde)
- **VTOL roadmap** → multicopter + tiltrotor config tipleri
- **multicopter roadmap** → rotor disk analizi, frame config

### Harici Araç Entegrasyonları (uzun vade)
- **OpenVSP** → 3D model generation, panel method
- **AVL** → aerodinamik analiz (Athena Vortex Lattice)
- **Gazebo** → fizik simülasyonu, ROS entegrasyonu
- **JSBSim** → uçuş dinamiği simülasyonu
- **OpenFOAM / SU2** → CFD analiz

## Uyum ve Tutarlılık Değerlendirmesi

**Güçlü yönler**
- Hepsi aynı `StudioPlugin` protokolünü izliyor
- `geometry provider` deseni diğer pluginler için de tekrarlanabilir
- `id` namespace'leri tutarlı (`org.setuav.studio.*`)

**Zayıf yönler / Riskler**
- `electrical_propulsion` 400+ satır UI thread solver → yeni solver pluginleri bunu tekrarlamamalı (Faz 5.15'i bekle)
- Plugin sınırı belirsiz: solver kodu plugin içinde mi, ayrı paket mi?
- Açık kaynak / kapalı kaynak plugin ayrımı için sözleşme yok → 3rd party pluginler ile koordinasyon eksik
- 9 airfoil preset bundle'lı; aerodynamic plugin için aynı set yeterli mi yoksa genişletilecek mi?

## Önerilen Plugin Geliştirme Sırası

1. **aerodinamik** (todo 1. sıra) → mevcut geometry_provider deseni üzerine
2. **ağırlık/denge** (todo 2.) → component aggregation kolay, geometry'ye bağımlı değil
3. **uçuş mekaniği** (todo 3.) → aerodinamik + ağırlık verisini tüketir; en kapsamlı
4. **VTOL / multicopter** → sabit kanat altyapısı oturduktan sonra
5. **Harici araçlar (OpenVSP/AVL/Gazebo/JSBSim/CFD)** → API kontratı netleşmeli, subprocess yönetimi gerekir

## Açık Sorular

- **aerodinamik plugin** → UI sürücüsü mü yoksa sadece `geometry_provider` mı?
- **ağırlık/denge** → CG hesabı runtime mi (her değişiklikte), yoksa talep üzerine mi?
- **uçuş mekaniği** → solver kodu plugin içinde mi yoksa `setuav-pythrust` benzeri ayrı pakette mi?
- **VTOL config tipi** → ayrı component tipi mi (`org.setuav.core:vtol-config`), yoksa lifting-surface parametrelerine mi yayılır?
- **Harici araçlar** → subprocess ile mi çağrılacak, yoksa in-process import mu?
- **Açık/kapalı kaynak ayrımı** → hangi pluginler OSS, hangileri ücretli? (kullanıcı kararı)