# Kanat / Taşıyıcı Yüzey Geliştirme Yol Haritası (TODO)

### 🔴 Aşama 1: Kritik / Temel Özellikler
1. **`.dat` / `.cor` Profil Yükleyici & Profil Kütüphanesi (10/10)**
   * UI üzerinden `.dat` formatında koordinat dosyası seçebilme.
   * Hazır popüler İHA/uçak profilleri kütüphanesi (Selig, Wortmann, Eppler, MH, Clark-Y).

2. **Parametrik Kanat Ölçülendirme & Sürücü Grupları (Driver Groups) (9.5/10)**
   * Kanat alanı ($S$), açıklık ($b$), açıklık oranı ($AR$), sivrilme oranı ($\lambda$), kök/uç veterleri ile otomatik boyutlandırma.
   * Bir parametre değiştiğinde diğerlerinin otomatik güncellenmesi.

3. **Ok Açısı Referans Konumu (Sweep Reference Location) (9/10)**
   * Ok açısının ($\Lambda$) hücum kenarı ($\%0$), çeyrek veter ($\%25 \text{ MAC}$) veya firar kenarından ($\%100$) tanımlanabilmesi.

---

### 🟡 Aşama 2: Yüksek Öncelikli Özellikler
4. **3D Kumanda Yüzeyi Kesikleri & Açısal Sapma Görselleştirme (8.5/10)**
   * Menteşe hattında kanat yüzeyinden ayrık kontrol yüzeyi (aileron, flap, rudder, elevator).
   * 3D sahnede $\pm \delta^\circ$ sapma açısı ile hareket ettirme.

5. **Burulma Ekseni Konumu (Twist Axis Location & Washout) (8/10)**
   * Kanat ucu burulmasının (washout) dönme ekseni konumu ($\%25$ veter, hücum kenarı vb.).
   * Bağıl (relative) ve mutlak (absolute) burulma seçenekleri.

6. **Kanat Uç ve Kök Kapakları (Wing Tip & Root Caps) (7.5/10)**
   * Kanat ucunu kapatma seçenekleri: `Round (Yuvarlatılmış)`, `Flat (Düz Kapalı)`, `Sharp (Keskin)`.

---

### 🟢 Aşama 3: İmalat & İnce Ayar Özellikleri
7. **Firar Kenarı Kalınlığı & Kırpma (TE Blunting / Thickness) (6.5/10)**
   * Üretim/imalat için firar kenarına sonlu kalınlık ($0.5 - 1.5\,\text{mm}$) verebilme.
   * Profil kalınlık ($t/c$) ve kamburluk (camber) ölçekleyicileri.

8. **Dihedral Kesit Hizalaması (Rotate Foil to Match Dihedral) (6/10)**
   * Yüksek dihedral/V-tail durumunda profilin kanat hattına dik kesilmesi veya $XZ$ düzlemine paralel kalması seçeneği.

---

### ⚪ Aşama 4: İleri Seviye / Opsiyonel
9. **Winglet / Kıvrımlı Uç Geometrisi (4.5/10)**
   * Kanat ucu kıvrımları ve winglet modelleme.

10. **CST (Class-Shape Transformation) Profil Üreteci (3.5/10)**
    * Parametrik matematiksel profil eğri optimizasyonu.
