# Kanat / Taşıyıcı Yüzey Geliştirme Yol Haritası (TODO)

### 🔴 Aşama 1: Kritik / Temel Özellikler
1. **[x] `.dat` / `.cor` Profil Yükleyici & Profil Kütüphanesi (10/10)**
   * UI üzerinden `.dat` formatında koordinat dosyası seçebilme.
   * UIUC resmî veritabanından Selig, Wortmann, Eppler, MH, Clark-Y profilleri entegre edildi.
   * 2D interaktif kesit tuvali ve anlık aerodinamik özellik hesaplayıcı tamamlandı.

2. **[x] Parametrik Kanat Ölçülendirme & Sürücü Grupları (Driver Groups) (9.5/10)**
   * Kanat alanı ($S$), açıklık ($b$), açıklık oranı ($AR$), sivrilme oranı ($\lambda$), kök/uç veterleri ile parametrik boyutlandırma motoru (`wing_planform_engine.py`).
   * Seçilebilir Sürücü Modları ($S+AR+\lambda$, $b+c_r+c_t$, $b+S+\lambda$, $b+AR+\lambda$, Manual).
   * Canlı formül çözümleme, oransal istasyon ölçekleme ve `driver_groups` şema senkronizasyonu tamamlandı.

3. **[x] Ok Açısı Referans Konumu (Sweep Reference Location) (9/10)**
   * Ok açısının ($\Lambda^\circ$) seçilebilir referans eksenleri:
     * `Quarter Chord (25% MAC)`
     * `Leading Edge (0%)`
     * `Half Chord (50%)`
     * `Trailing Edge (100%)`
   * Ok açısı girildiğinde istasyon hücum kenarı $X$ ofsetlerinin anlık hesaplanması.
   * Sürücü modu aktifken makro planform sütunlarının (Span $Y$, Chord, Offset $X$) otomatik kilitlenmesi, Manual modda açılması ve düzenlenebilir/hesaplanan alanların görsel olarak ayrılması.

---

### 🟡 Aşama 2: Yüksek Öncelikli Özellikler
4. **[x] 3D Kumanda Yüzeyi Kesikleri & Açısal Sapma Görselleştirme (8.5/10)**
   * Kanat geometrisinin kumanda yüzeyi açıklık ve veter sınırlarında otomatik olarak fiziksel iki parçaya (Ana Kanat Gövdesi + Kumanda Yüzeyi Flabı) ayrılması.
   * 3D menteşe hattı ekseninin otomatik hesaplanması ve $\pm \delta^\circ$ sapma açısı (deflection) ile canlı 3D döndürme motoru (Rodrigues 3D Rotation).
   * Kumanda yüzeylerine özel vurgu rengi (`control_surface_color`) ve editörde canlı `Deflection Angle (°)` parametresi eklendi.

5. **[x] Burulma Ekseni Konumu (Twist Axis Location & Washout) (8/10)**
   * Kanat ucu burulmasının (washout) dönme ekseni konumu: `Leading Edge (0%)`, `Quarter Chord (25% c)`, `Half Chord (50%)`, `Hinge Line (75%)`, `Trailing Edge (100%)`.
   * OpenVSP ile birebir aynı $X_{\text{rot}} = X_{\text{LE}} + \text{TwistLoc} \cdot c$ pivot dönme matematiği (`transforms.py` & `lifting_surface_geometry.py`).
   * Sürücü modlarında ($S+AR+\lambda$, $b+c_r+c_t$ vb.) `Tip Twist / Washout (ε)` parametresi ve lineer istasyon burulma dağılımı (`wing_planform_engine.py`).
   * `LiftingSurfaceEditor` UI arayüzünde `Twist Axis` seçimi, `Twist (°)` istasyon sütunu ve `Section Properties` canlı düzenleyicisi tamamlandı.

6. **[x] Kanat Uç ve Kök Kapakları (Wing Tip & Root Caps) (7.5/10)**
   * Kanat ucunu kapatma seçenekleri: `Flat (Düz Kapak)`, `Round (Yuvarlatılmış / Dome)`, `Sharp (Keskin Kama)`.
   * Parametrik `tip_treatment` yapısı (`type`, `length`, `offset_x`) ve çeyrek sinüs/kosinüs eliptik kavis motoru.
   * `LiftingSurfaceEditor` UI üzerinde dinamik **"End Caps (Tip Treatment)"** paneli ve canlı 3D güncelleme entegrasyonu tamamlandı.

7. **[x] 2D Gövde Kesit İnceleme & Düzenleme Ekranı (Fuselage Section 2D Inspector) (8.5/10)**
   * `FuselageSectionDialog` ve vektörel `FuselageCanvasWidget` (QPainter, anti-aliased, zoom & pan).
   * Kesit türleri (Circle, Ellipse, Rectangle, Trapezoid, Triangle, Polygon) için canlı 2D çizim.
   * Önceki/sonraki istasyon hayalet (ghost) katmanları, ızgara, koordinat eksenleri, ölçülendirme okları ve ağırlık merkezi (CG) göstergesi.
   * Canlı mühendislik metrikleri (Alan, Çevre, Genişlik, Yükseklik, Açıklık Oranı, Hidrolik Çap).

---

### 🟢 Aşama 3: İmalat & İnce Ayar Özellikleri
7. **[ ] Firar Kenarı Kalınlığı & Kırpma (TE Blunting / Thickness) (6.5/10)**
   * Üretim/imalat için firar kenarına sonlu kalınlık ($0.5 - 1.5\,\text{mm}$) verebilme.
   * Profil kalınlık ($t/c$) ve kamburluk (camber) ölçekleyicileri.

8. **[ ] Dihedral Kesit Hizalaması (Rotate Foil to Match Dihedral) (6/10)**
   * Yüksek dihedral/V-tail durumunda profilin kanat hattına dik kesilmesi veya $XZ$ düzlemine paralel kalması seçeneği.

---

### ⚪ Aşama 4: İleri Seviye / Opsiyonel
9. **[ ] Winglet / Kıvrımlı Uç Geometrisi (4.5/10)**
   * Kanat ucu kıvrımları ve winglet modelleme.

10. **[ ] CST (Class-Shape Transformation) Profil Üreteci (3.5/10)**
    * Parametrik matematiksel profil eğri optimizasyonu.
