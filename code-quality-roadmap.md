# Code Quality Roadmap

Her ana adım ayrı tamamlanacak, doğrulanacak ve commit edilecek. Bir adım bitmeden
sonraki adıma geçilmeyecek.

## Mevcut durum

- [x] Ruff lint kuralları tanımlandı.
- [x] Mevcut Ruff lint sorunları temizlendi.
- [x] 215 test başarıyla çalışıyor.
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
- [ ] UI katmanını kademeli olarak kapsama al.

Pyright kapsamı, Weight & Balance solver'ın eklenmesiyle 22 saf model/engine
dosyasına ulaştı ve `basic` modda sıfır hata ile geçiyor. Son gruptaki 5 tip
hatası açık `Vector3` ve `Matrix3` dönüşümleriyle giderildi. Model ve engine
katmanlarının kademeli tip kontrolü tamamlandı.

UI kapsamı `log_buffer.py` ve `numeric_spinbox.py` ile başlatıldı. Toplam 24
dosya `basic` modda sıfır hata ile geçiyor; ilk UI grubu ek düzeltme
gerektirmedi. `icons.py` ve `buttons.py` ile kapsam 26 dosyaya çıkarıldı; ikinci
UI grubu da ek düzeltme gerektirmedi.

## 6. Test gruplarını ayır

- [ ] Hızlı unit testleri belirle.
- [ ] Qt GUI testlerini ayrı gruba al.
- [ ] AeroSandbox entegrasyon testlerini ayrı gruba al.
- [ ] Her grup için bağımsız çalıştırma komutu tanımla.
- [ ] Hızlı test grubunu yerel geliştirmeye uygun hâle getir.

## 7. Coverage eksiklerini kapat

- [ ] Coverage oranı düşük modülleri listele.
- [ ] Hata ve sınır durumları için testler ekle.
- [ ] Plugin yükleme ve kaldırma senaryolarını güçlendir.
- [ ] Proje açma, kaydetme ve bozuk veri senaryolarını güçlendir.
- [ ] Coverage eşiğini kademeli olarak artır.

## 8. Kod karmaşıklığını azalt

- [ ] Büyük sınıf ve fonksiyonları raporla.
- [ ] UI, veri ve hesaplama sorumluluklarını ayır.
- [ ] Solver ve plugin servislerini küçük bileşenlere böl.
- [ ] Her refactor sonrasında mevcut davranışı testlerle doğrula.

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
