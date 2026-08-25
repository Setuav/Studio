# CI/CD Roadmap

## 1. Proje hazırlıkları

- [x] `pyproject.toml` içine geliştirme araçlarını ekle.
- [x] Ruff lint ve format ayarlarını tanımla.
- [x] `setuav-studio` komut satırı giriş noktasını ekle.
- [ ] PyInstaller bağımlılığını ve `.spec` dosyasını ekle.
- [ ] Uygulama adı, sürümü ve ikonlarını paketlemeye hazırla.
- [ ] Yerel lint, test ve build komutlarını doğrula.

## 2. CI

- [ ] `.github/workflows/ci.yml` oluştur.
- [ ] Pull request ve `main` push işlemlerinde çalıştır.
- [ ] Bağımlılıkları `uv.lock` üzerinden kur.
- [ ] Ruff lint ve format kontrolünü çalıştır.
- [ ] Qt testlerini headless ortamda çalıştır.
- [ ] Python 3.11 ve güncel Python sürümünü test et.
- [ ] Wheel ve source distribution üretimini doğrula.
- [ ] CI başarılı olmadan `main` birleştirmelerini engelle.

## 3. Masaüstü paketleme

- [ ] PyInstaller ile `onedir` paket üret.
- [ ] Paket içindeki ikon, font, şema ve veri dosyalarını doğrula.
- [ ] Paketlenmiş uygulama için başlangıç testi ekle.
- [ ] Windows `.zip` çıktısı üret.
- [ ] Linux `.tar.gz` çıktısı üret.
- [ ] macOS `.app.zip` çıktısı üret.

## 4. Release otomasyonu

- [ ] `.github/workflows/release.yml` oluştur.
- [ ] `v*` etiketiyle release sürecini başlat.
- [ ] Git etiketi ile proje sürümünün eşleşmesini kontrol et.
- [ ] Paketleri işletim sistemlerine göre paralel üret.
- [ ] SHA-256 checksum dosyalarını oluştur.
- [ ] Çıktıları GitHub Release'e yükle.
- [ ] Windows ve macOS imzalamayı sonraki aşamada ekle.

## 5. Dokümantasyon

- [ ] Kurulum ve hızlı başlangıç belgelerini tamamla.
- [ ] CI içinde doküman build kontrolü ekle.
- [ ] `.github/workflows/docs.yml` oluştur.
- [ ] Dokümantasyonu GitHub Pages üzerinde yayınla.

## 6. Bakım

- [ ] Bağımlılık güncellemelerini otomatik takip et.
- [ ] GitHub Actions bağımlılıklarını sabit sürümlere bağla.
- [ ] Haftalık güvenlik ve bağımlılık kontrolleri çalıştır.
- [ ] Release sürecini gerçek bir temiz makinede doğrula.
