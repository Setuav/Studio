# CI/CD Roadmap

## 1. Proje hazırlıkları

- [x] `pyproject.toml` içine geliştirme araçlarını ekle.
- [x] Ruff lint ve format ayarlarını tanımla.
- [x] `setuav-studio` komut satırı giriş noktasını ekle.
- [x] PyInstaller bağımlılığını ve `.spec` dosyasını ekle.
- [x] Uygulama adı, sürümü ve ikonlarını paketlemeye hazırla.
- [x] Yerel lint, test ve build komutlarını doğrula.

## 2. CI

- [x] `.github/workflows/ci.yml` oluştur.
- [x] Pull request ve `main` push işlemlerinde çalıştır.
- [x] Bağımlılıkları `uv.lock` üzerinden kur.
- [x] Ruff lint ve format kontrolünü çalıştır.
- [x] Qt testlerini headless ortamda çalıştır.
- [x] Python 3.11 ve güncel Python sürümünü test et.
- [x] Wheel ve source distribution üretimini doğrula.
- [ ] CI başarılı olmadan `main` birleştirmelerini engelle.

## 3. Masaüstü paketleme

- [x] PyInstaller ile `onedir` paket üret.
- [x] Paket içindeki ikon, font, şema ve veri dosyalarını doğrula.
- [x] Paketlenmiş uygulama için başlangıç testi ekle.
- [x] Windows `.zip` çıktısı üret.
- [x] Linux `.tar.gz` çıktısı üret.
- [x] macOS `.app.zip` çıktısı üret.

## 4. Release otomasyonu

- [x] `.github/workflows/release.yml` oluştur.
- [x] `v*` etiketiyle release sürecini başlat.
- [x] Git etiketi ile proje sürümünün eşleşmesini kontrol et.
- [x] Paketleri işletim sistemlerine göre paralel üret.
- [x] SHA-256 checksum dosyalarını oluştur.
- [x] Çıktıları GitHub Release'e yükle.
- [ ] Windows ve macOS imzalamayı sonraki aşamada ekle.

## 5. Dokümantasyon

- [ ] Kurulum ve hızlı başlangıç belgelerini tamamla.
- [ ] CI içinde doküman build kontrolü ekle.
- [ ] `.github/workflows/docs.yml` oluştur.
- [ ] Dokümantasyonu GitHub Pages üzerinde yayınla.

## 6. Bakım

- [x] Bağımlılık güncellemelerini otomatik takip et.
- [x] GitHub Actions bağımlılıklarını sabit sürümlere bağla.
- [x] Haftalık güvenlik ve bağımlılık kontrolleri çalıştır.
- [ ] Release sürecini gerçek bir temiz makinede doğrula.
