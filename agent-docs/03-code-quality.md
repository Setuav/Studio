# Kod Kalitesi Analizi

## İyi Pratikler (somut)
- **Tip ipucu:** `Literal[...]` proje tipinde (`project.py:21`); `Callable[[dict], QWidget]` factory imzaları; `Protocol` kontrat
- **Dataclass:** Tüm contribution `@dataclass(frozen=True)`; renderer geometrisi `@dataclass(frozen=True, slots=True)`
- **Undo/Redo:** `_ComponentEditCommand`/`_ProjectEditCommand` deep-copy snapshot ile `cleanChanged` senkronize
- **QSettings:** window geometry, workspace perspective, recent projects anahtarları temiz
- **qtawesome soyutlama:** `get_icon(name)` → logical/QtAwesome spec/Path/QIcon; plugin'ler sadece isim kullanıyor
- **Atomic yazım:** `tempfile` + `os.replace` ile yarım dosya bırakmıyor

## Modül Düzeyinde Global Mutable State
- `_active_palette` (`geometry/palettes.py:40-51`) thread-unsafe
- `_MOTOR_DB`/`_PROP_DB` (`electrical_propulsion/database.py:30-31`) reset edilemiyor
- `_inter_family`, `_dock_resize_style` cache flag'leri (`plugins/core/theme.py`)
- `_ICON_MAP` `icons.py:6-31` salt okunur → registry'e taşınabilir

## UI Thread Sorunu
- `_on_run_analysis` (~400 satır, `controls_dock.py:439-835`) sweep döngüsünde `solve_point` + `root_scalar` senkron çalışıyor
- Fallback RPM listesi `[2000,3000,...,15000]` × 11 = 330 data noktası UI thread'inde
- `grep "QThread"` → boş; QRunnable/sinyal pattern'i yok → önemli iyileştirme fırsatı

## Hata Yutma (somut yerler)
- `icons.py:59` `except Exception: return QIcon()` → bozuk ikon sessiz
- `airfoil.py:479,504` dosya parse → 0012 fallback sessiz
- `controls_dock.py:569` solver exception → `rpm_max` fallback (yanlış "feasible" sonuç)
- `plugin_system.py:248-430` RuntimeError listener cleanup deseni 6 kez tekrarlanıyor → helper'a çıkarılabilir

## Magic Number/String Kümeleri
- `controls_dock.py:508` fallback RPM listesi literal
- `shell.py:117-144` accent rengi rgba token sisteminde yok
- `shell.py:94` `_LAYOUT_VERSION = 6` migration desteklenmeden artırılıyor
- Dock object-name string'leri constants'a alınmamış
- `charts_dock.py:113-118` token sistemine paralel ikinci renk seti

## Uzun Fonksiyonlar / İç İçe Yapı
- `_on_run_analysis` ~400 satır, 3 mod tek metoda gömülü
- `_refresh_assemblies` ~80 satır (`controls_dock.py:345-422`)
- `build_project_geometry` ~130 satır, 5 seviye nested if (`scene.py:20-147`)
- `lifting_surface.py` 1802 satır monolitik editör → bölünebilir

## Tip Güvensiz Dict Erişimi
- `controls_dock.py:416-418` `pack.get(...) or params.get(...) or params.get(..., 1)` → `0` falsy, `1`'e fallback
- `component_editor.py:159` `mass = component.get("mass", params.get("mass", 0))` aynı sorun
- `controls_dock.py:471-474` `d_raw > 2.0` birim kestirimi (mm mi m mi) heuristic
- `controls_dock.py:540-545` `findChild(...) or next(... __class__.__name__ == "...")` class adı string match

## Hardcoded Yollar
- `database.py:20` `/home/huseyin/dev/setware/PyThrust/data` kullanıcı-spesifik
- `tests/test_geometry.py:21` `/home/huseyin/dev/setware/setuav-specification/examples/fixed-wing`
- Aynı yol `test_electrical_propulsion.py`'de 6 kez tekrarlanıyor → fixture'a alınabilir

## Ölü/Garip Kod
- `shell.py:108-110` `central_anchor` oluştur → hemen `setCentralWidget(None)` sıfırla
- `controls_dock.py:569-570` solver başarısızsa görsel feasible ama yanlış sonuç
- `controls_dock.py:804-805` `if "res" in locals()` kırılgan
- `plugin_system.py:194-196` `set_workspace` `add_workspace` alias'i → işlevsiz
- `plugin_system.py:603,612` `except Exception` → `KeyboardInterrupt`/`SystemExit` de yutuluyor

## Test Kapsamı
- **İyi test edilmiş:** `plugin_system`, `project`, `theme`, geometri transformları + wing planform + scene
- **Zayıf/hiç:** `geometry/fuselage.py` (1234 satır), `lifting_surface.py` (1802 satır), `airfoil_dialog.py` (462), `widget.py` (672 OpenGL viewer), `control_surface.py`, `shell.py` MainWindow
- **UI test:** pytest-qt yok; sadece `setText/click` ile state doğrulama
- **Fixture:** `TEST_PROJECT_PATH` hardcoded; conftest.py yok

## Tutarlılık
- **Naming:** snake_case + `_` private prefix tutarlı; tek sapma `set_workspace` vs `add_workspace`
- **Docstring:** modül/sınıf düzeyinde karışık (bazıları var, bazıları yok); private helper'lar tamamen belgesiz
- **Logging:** sadece `geometry/workspace.py`'de 1 logger; plugin/project/shell'de sıfır → debug zor
- **Hata mesajı:** bazıları context'li, bazıları `str(exc)` çıplak (`shell.py:271,297,319`)

## Tekrar Eden Helper'lar
- `_property_table`, `_set_property_value`, `_set_property_combo`, `_property_key`, `_fit_table_height` neredeyse identical kopyalanmış (component_editor / controls_dock / instance / battery / assembly / results_dock) → tek mixin/utility'e çıkarılabilir

## Güçlü Yönler (kısa)
- Plugin mimarisi temiz (Protocol + discovery + duplicate guard)
- Undo/redo editörlere sızmıyor
- `GeometryData` renderer-agnostic
- Atomic dosya yazımı
- QSettings ile UI state round-trip

## Gelişime Açık Yönler (kısa)
- Logging stratejisi tutarlı değil
- UI thread'inde uzun solver hesapları var
- Hardcoded yollar conftest fixture'a alınabilir
- Lifting surface editor (1802 satır) bölünebilir
- Property table helper'ları mixin/utility'e çıkarılabilir