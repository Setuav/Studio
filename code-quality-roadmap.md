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

- [ ] `.pre-commit-config.yaml` oluştur.
- [ ] Ruff lint düzeltmesini ekle.
- [ ] Ruff format kontrolünü ekle.
- [ ] Yapılandırma dosyaları için temel kontroller ekle.
- [ ] Hook'ları tüm dosyalarda çalıştırıp doğrula.

## 4. Ruff kurallarını genişlet

- [ ] Bug riski taşıyan `B` kurallarını değerlendir.
- [ ] Python modernizasyonu için `UP` kurallarını değerlendir.
- [ ] Sadeleştirme için `SIM` ve `C4` kurallarını değerlendir.
- [ ] Ruff'a özgü `RUF` kurallarını değerlendir.
- [ ] Kuralları küçük gruplar hâlinde aç ve ihlalleri ayrı commitlerle düzelt.

## 5. Statik tip kontrolü ekle

- [ ] Pyright veya mypy aracını seç.
- [ ] Temel yapılandırmayı ekle.
- [ ] Önce model ve engine katmanlarını kapsa.
- [ ] Tip hatalarını küçük gruplar hâlinde düzelt.
- [ ] UI katmanını kademeli olarak kapsama al.

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
