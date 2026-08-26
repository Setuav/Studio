# Code Quality Roadmap

Her ana adım ayrı tamamlanacak, doğrulanacak ve commit edilecek. Bir adım bitmeden
sonraki adıma geçilmeyecek.

## Mevcut durum

- [x] Ruff lint kuralları tanımlandı.
- [x] Mevcut Ruff lint sorunları temizlendi.
- [x] 315 test başarıyla çalışıyor.
- [x] Ruff formatı tüm kod tabanına uygulandı.

## 1. Kod tabanını formatla

- [x] `ruff format .` çalıştır.
- [x] Format kontrolünün temiz geçtiğini doğrula.
- [x] Ruff lint kontrolünü yeniden çalıştır.
- [x] Tüm testleri çalıştır.
- [x] Yalnızca formatlama değişikliklerini ayrı commit et.

## 2. Coverage altyapısını kur

- [x] Coverage ayarlarını `pyproject.toml` içine ekle.
- [x] Kaynak kod kapsam raporunu üret.
- [x] HTML ve terminal raporlarını doğrula.
- [x] Mevcut coverage oranını başlangıç değeri olarak kaydet.
- [x] İlk aşamada gerçekçi bir minimum eşik belirle.

Başlangıç branch coverage değeri `%68,8`, minimum kabul eşiği `%68` olarak
belirlendi.

## 3. Pre-commit kontrollerini ekle

- [x] `.pre-commit-config.yaml` oluştur.
- [x] Ruff lint düzeltmesini ekle.
- [x] Ruff format kontrolünü ekle.
- [x] Yapılandırma dosyaları için temel kontroller ekle.
- [x] Hook'ları tüm dosyalarda çalıştırıp doğrula.

## 4. Ruff kurallarını genişlet

- [x] Bug riski taşıyan `B` kurallarını değerlendir.
- [x] Python modernizasyonu için `UP` kurallarını değerlendir.
- [x] Sadeleştirme için `SIM` ve `C4` kurallarını değerlendir.
- [x] Ruff'a özgü `RUF` kurallarını değerlendir.
- [x] Kuralları küçük gruplar hâlinde aç ve ihlalleri ayrı commitlerle düzelt.

## 5. Statik tip kontrolü ekle

- [x] Pyright veya mypy aracını seç.
- [x] Temel yapılandırmayı ekle.
- [x] Önce model ve engine katmanlarını kapsa.
- [x] Tip hatalarını küçük gruplar hâlinde düzelt.
- [x] UI katmanını kademeli olarak kapsama al.

Pyright kapsamı, Weight & Balance solver'ın eklenmesiyle 22 saf model/engine
dosyasına ulaştı ve `basic` modda sıfır hata ile geçiyor. Son gruptaki 5 tip
hatası açık `Vector3` ve `Matrix3` dönüşümleriyle giderildi. Model ve engine
katmanlarının kademeli tip kontrolü tamamlandı.

UI kapsamı `log_buffer.py` ve `numeric_spinbox.py` ile başlatıldı. Toplam 24
dosya `basic` modda sıfır hata ile geçiyor; ilk UI grubu ek düzeltme
gerektirmedi. `icons.py` ve `buttons.py` ile kapsam 26 dosyaya çıkarıldı; ikinci
UI grubu da ek düzeltme gerektirmedi. `log_window.py` ve `main_toolbar.py` ile
kapsam 28 dosyaya çıkarıldı; üçüncü UI grubu da ek düzeltme gerektirmedi.
`property_tables.py` ile kapsam 29 dosyaya çıkarıldı ve 2 Qt flag tip hatası
giderildi. Son olarak `theme.py` kapsama alındı ve 2 QObject daraltma hatası
giderildi. Toplam 30 dosya sıfır hata ile geçiyor; UI katmanının kademeli tip
kontrolü tamamlandı.

## 6. Test gruplarını ayır

- [x] Testleri uygulama çekirdeği ve plugin dizinlerine ayır.
- [x] Hızlı aerodynamics testlerini gerçek solver entegrasyonlarından ayır.
- [x] AeroSandbox entegrasyon testlerini ayrı gruba al.
- [x] Her plugin için bağımsız çalıştırma komutu tanımla.
- [x] Tam test ve coverage komutlarını koru.

Testler `tests/<plugin>/` dizinlerinde gruplanıyor. `tests/suites.py`; `core`,
`geometry`, `aerodynamics-fast`, `aerodynamics-integration`,
`electrical-propulsion`, `flight-performance` ve `weight-balance` komutlarını
sağlıyor. Suite runner Qt'yi headless çalıştırıyor; tüm gruplar birlikte 315
test içeriyor.

## 7. Coverage eksiklerini kapat

- [x] Coverage oranı düşük modülleri listele.
- [x] Hata ve sınır durumları için testler ekle.
- [x] Plugin yükleme ve kaldırma senaryolarını güçlendir.
- [x] Proje açma, kaydetme ve bozuk veri senaryolarını güçlendir.
- [ ] Coverage eşiğini kademeli olarak artır.

Tam plugin suite'i için başlangıç coverage değeri `%68,8` olarak doğrulandı.
Önceliklendirme yalnızca düşük orana göre değil, kullanıcı akışına etkisi ve
izole test edilebilirliği dikkate alınarak yapıldı.

### Öncelikli coverage kuyruğu

1. [x] `geometry/engine/wing_driver_solver.py` — `%13,3` seviyesinden `%100`
   branch coverage'a çıkarıldı; 7 odak test ve asimetrik alan düzeltmesi eklendi.
2. [x] `core/instance.py` — `%10,9` seviyesinden `%100` branch coverage'a
   çıkarıldı; 8 odak testle görünüm, copy/mirror türetme, parent/source çözümleme,
   doğrulama, transform düzenleme ve undo/redo akışları kapsandı.
3. [x] `electrical_propulsion/creation.py` — `%12,8` seviyesinden `%100` branch
   coverage'a çıkarıldı; 12 odak testle assembly ve bileşen oluşturma, benzersiz
   kimlikler, hedef seçimi, varsayılanlar, undo ve hatalı proje durumları kapsandı.
4. [x] `geometry/creation.py` — `%20,6` seviyesinden `%100` branch coverage'a
   çıkarıldı; 10 odak testle fuselage, lifting/control surface presetleri, hedef
   seçimi, benzersiz kimlikler, undo ve hatalı proje durumları kapsandı.
5. [x] `core/settings.py` ve `geometry/settings.py` — `%23,5` / `%21,1`
   seviyelerinden `%99,1` / `%100` branch coverage'a çıkarıldı; 10 odak testle
   doğrulama, kalıcılık, plugin sayfaları ve hatalı değer geri dönüşleri kapsandı.
6. [x] `project.py` — `%72,6` seviyesinden `%100` branch coverage'a çıkarıldı;
   11 sınır testiyle açma, kaydetme, archive asset koruma, atomik yazma temizliği,
   extension yardımcıları ve bozuk veri senaryoları kapsandı.
7. [x] `plugin_system.py` — `%81,8` seviyesinden `%100` branch coverage'a
   çıkarıldı; 14 odak testle registry yaşam döngüsü, plugin discovery/activation
   hataları, callback izolasyonu, listener temizliği ve provider çözümleme kapsandı.
8. [x] `shell.py` — ana pencere akışları iki küçük headless UI grubuna bölündü.
   - [x] Proje yaşam döngüsü: validation, açma/kaydetme, unsaved-change özeti,
     recent projects ve dosya diyalogları 12 headless testle kapsandı. Core suite
     ölçümünde shell branch coverage `%42,6` seviyesinden `%56,8` seviyesine çıktı.
   - [x] Toolbar, panel, tema, settings ve workspace layout yaşam döngüsü 16
     headless testle kapsandı. İki grubun ardından core suite ölçümünde shell
     branch coverage `%94,0` seviyesine ulaştı.

İlk iki hedefin ardından tam suite branch coverage değeri `%70,2` seviyesine
ulaştı.

İkinci dalgada `geometry/viewport/widget.py`, `view2d/canvas.py` ve büyük
geometry editor diyalogları headless Qt testleriyle kapsanacak.

## 8. Kod karmaşıklığını azalt

- [x] Büyük sınıf ve fonksiyonları raporla.
- [x] Ruff `C901` kalite kapısını başlangıç eşiği `20` ile etkinleştir.
- [ ] UI, veri ve hesaplama sorumluluklarını ayır.
- [ ] Solver ve plugin servislerini küçük bileşenlere böl.
- [ ] Her refactor sonrasında mevcut davranışı testlerle doğrula.

Başlangıç ölçümünde varsayılan `10` eşiğini aşan 53, geçici `20` eşiğini aşan
13 fonksiyon bulundu. `C901` tüm kaynak kodda etkin; yalnızca aşağıdaki mevcut
13 fonksiyon noktasal `noqa` ile baseline edildi. Dosya bazlı istisna
kullanılmadığı için aynı dosyalara eklenecek yeni karmaşık fonksiyonlar kalite
kapısında yakalanacak.

### Karmaşıklık azaltma kuyruğu

1. [ ] `shell._apply_default_workspace_layout` — `53`; workspace başına layout
   handler'larına ayır.
2. [ ] `aerosandbox_engine._convert_lifting_surface` — `65` ve `analyze` — `39`;
   veri dönüşümü, çözümleme ve sonuç üretimini ayır.
3. [ ] `flight_performance.solver.run_analysis` — `45`; analiz modlarını bağımsız
   yürütücülere ayır.
4. [ ] `geometry.viewport.mesh.build_section_ring_vertices` — `36`; profil türü
   üreticilerini ayır.
5. [ ] `schema_validation.validate_project` — `30`; doğrulama kurallarını saf
   validator fonksiyonlarına ayır.
6. [ ] `geometry.viewport.scene` — `29` / `21`; scene çözümleme ve wing-root stub
   üretimini ayır.
7. [ ] `project_explorer` — `28` / `25`; tree oluşturma ve silme komutlarını UI'dan
   ayır.
8. [ ] `lifting_surface_geometry` — `27`; control-surface üretimini böl.
9. [ ] `aerodynamics.controls_dock` ve `flight_performance.charts_dock` — `21`;
   mode/chart dallarını küçük handler'lara ayır.

İlk hedef tüm noktasal istisnaları kaldırıp `20` eşiğini gerçekten sağlamak;
ardından eşik sırasıyla `15` ve `10` seviyelerine indirilecek.

## 9. Bağımlılıkları düzenle

- [ ] Kullanılmayan bağımlılıkları tespit et.
- [ ] Runtime, opsiyonel ve geliştirme bağımlılıklarını ayır.
- [ ] Sürüm aralıklarını gözden geçir.
- [ ] Güvenlik ve lisans kontrollerini ekle.

## 10. Paket smoke testleri ekle

- [ ] Wheel ve source distribution üret.
- [ ] Wheel'i temiz bir ortama kur.
- [ ] Paket import testini çalıştır.
- [ ] `setuav-studio --help` komutunu çalıştır.
- [ ] İkon, font, şema ve veri dosyalarının pakette bulunduğunu doğrula.
