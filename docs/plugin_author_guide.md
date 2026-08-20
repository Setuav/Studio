# Setuav Studio Plugin Yazar Rehberi

## Kontrat

- Plugin bir sınıf; `id: str` + `activate(api: StudioAPI) -> None` zorunlu
- Miras gerekmez; `StudioPlugin` yalnızca `typing.Protocol` (structural typing)
- `id` benzersiz ve namespaced: `org.setuav.studio.*` (yerleşik), `com.sirket.*` (üçüncü parti)

```python
class MyPlugin:
    id = "com.example.myplugin"

    def activate(self, api: StudioAPI) -> None:
        api.add_panel(...)
```

## Paketleme ve Keşif

İki keşif yolu:

1. **Bundled plugin** → `setuav_studio/plugins/<name>/` altında; modülde `PLUGIN = MyPlugin()` attribute'u
2. **Üçüncü parti** → `pyproject.toml` entry point:

```toml
[project.entry-points."setuav_studio.plugins"]
myplugin = "myplugin.plugin:MyPlugin"
```

Yükleme hataları `PluginLoadIssue` olarak toplanır; plugin çökse bile uygulama ayakta kalır. `activate` içinde exception fırlatma → plugin atlanır, diğerleri yüklenir.

## Versiyon Beyanı (`provides`)

- Opsiyonel; plugin'in sağladığı API sürümünü bildirir
- `provides = {"org.setuav.core": "1.0.0"}` → proje bu sürümü ister
- Projedeki istek (`data["plugins"]`), sağlanan sürümle karşılaştırılır

Karşılaştırma kuralları:
- `""` veya `"*"` → her sürüm uyumlu
- `"^1.2.3"` → caret: `>=1.2.3` ve `<2.0.0` (major 0 ise minor kırılımı)
- Diğer → tam eşitlik (`"1.2.3"` sadece `1.2.3` ile uyumlu)

## Katkı Tipleri (Contribution)

| Katkı | API | Ne zaman |
|---|---|---|
| Panel (dock) | `api.add_panel(PanelContribution(...))` | Bir dock widget'ı eklemek için |
| Workspace | `api.add_workspace(WorkspaceContribution(...))` | Yeni çalışma alanı için |
| Tool (Tools menüsü) | `api.register_tool(ToolContribution(...))` | Menü aksiyonu için |
| Action (herhangi menü) | `api.add_action(ActionContribution(...))` | `Tools` dışı bir menüye aksiyon için |
| Component editor | `api.register_component_editor(type_id, factory)` | Bileşen tipine özel editör için |
| Kind editor | `api.register_kind_editor(kind, factory)` | `kind`'e göre fallback editör için |
| Component icon | `api.register_component_icon(type_id, icon)` | Bileşen ikonu için |
| Kind icon | `api.register_kind_icon(kind, icon)` | Kind fallback ikonu için |
| Geometry provider | `api.register_geometry_provider(type_id, fn)` | 3D görüntüleme için geometri üretimi |
| Requirement checker | `api.set_project_requirement_checker(fn)` | Proje uyumluluk kontrolü |

## StudioAPI Temel Yüzeyi

**State:**
- `api.current_project` / `api.project` → `ProjectDocument | None`
- `api.current_workspace_id` → aktif workspace id
- `api.current_selection` → seçili nesne

**Düzenleme (undo/redo otomatik):**
- `api.edit_component(component, before, after, description)` → bileşen dict'ini değiştirir, undo stack'e ekler
- `api.edit_project(data, before, after, description)` → proje verisini değiştirir
- `api.undo()` / `api.redo()`

**Olaylar (listener):**
- `api.on_project_changed(listener)` → proje değişince
- `api.on_project_content_changed(listener)` → içerik değişince
- `api.on_selection_changed(listener)` → seçim değişince
- `api.on_section_selection_changed(listener)` → bölüm seçimi değişince
- `api.on_modified_changed(listener)` → modified bayrağı değişince
- `api.on_workspace_changed(listener)` → workspace değişince

**Diğer:**
- `api.switch_workspace(workspace_id)`

## Notlar ve Kurallar

- `add_panel` çağrısı shell hazır değilse `RuntimeError` fırlatır → `activate` içinde güvenle çağrılır (shell her zaman hazır)
- Workspace/action handler'lar geç bağlanırsa çağrılar biriktirilir, handler bağlanınca flush edilir
- Plugin'ler Qt nesnesi değildir; sadece API referansı alırlar
- QWidget'lar `factory` ile üretilir; `factory()` çağrısı shell thread'inde yapılır
- Plugin'ler arası iletişim için resmi mekanizma: event bus + paylaşılan `project.data` dict

## Örnek: Minimal UI Plugin

```python
from PySide6.QtCore import Qt
from setuav_studio.plugin_system import PanelContribution, WorkspaceContribution

class MyPlugin:
    id = "com.example.myplugin"

    def activate(self, api: StudioAPI) -> None:
        api.add_workspace(
            WorkspaceContribution(id="com.example.workspace", title="Example", order=30)
        )
        api.add_panel(
            PanelContribution(
                id="com.example.panel",
                title="Example Panel",
                factory=ExamplePanel,  # Callable[[], QWidget]
                workspace_id="com.example.workspace",
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
            )
        )
```

## Örnek: Component Editor Plugin

```python
from setuav_studio.component_editor import BaseComponentEditor, ParameterField

class MotorEditor(BaseComponentEditor):
    def __init__(self, api, component):
        super().__init__(api, component)
        self.add_parameter_field(
            ParameterField(key="kv", label="KV", kind="number", unit="rpm/V", default=900.0)
        )

class MyPlugin:
    id = "com.example.myplugin"
    provides = {"org.setuav.core": "1.0.0"}

    def activate(self, api: StudioAPI) -> None:
        api.register_component_editor("org.setuav.core:motor", lambda c: MotorEditor(api, c))
        api.register_component_icon("org.setuav.core:motor", "fa6s.engine")
```

## Test Etme

- Testler `unittest` tabanlı; `tests/_common.py`'den `get_qapp()` ve `TEST_PROJECT_PATH` kullan
- UI widget testleri `setText/click` ile state mutasyonu doğrular
- Plugin keşfi testi: `PluginManager(api)` + `activate(CorePlugin())` + `discover()` → issue listesi boş olmalı

## Degraded Mode

- Proje, olmayan/uyumsuz bir plugin gerektiriyorsa `project.plugin_issues` doldurulur, `project.degraded` True olur
- Plugin'iniz eksikse kullanıcı uygulamayı yine de kullanabilir (read-only değil) — ama ilgili editörler/paneller yüklenmez

## Kurallar Özeti

1. `id` namespaced, benzersiz, asla değiştirme (proje dosyaları buna bağlanır)
2. `activate` içinde ağır iş yapma (UI thread'de çalışır)
3. Uzun hesapları worker thread'e al (QRunnable/QThreadPool)
4. Bileşen verisine dokunurken `api.edit_component` kullan (undo/redo otomatik)
5. UI yazarken logical icon isimleri veya `fa6s.*` specifier kullan (doğrudan Path/QIcon da kabul edilir)