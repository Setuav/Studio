# Studio Motor Mount Planı

## Amaç

Motorun yerleşimini manufacturing’e özel bir veri olarak değil, Studio tasarım modelinin parçası olarak tanımlamak.

Aynı motor mount bilgisi:

- Geometry viewport’unda gösterilecek.
- Propulsion analizlerinde kullanılacak.
- Pervane clearance kontrolünde kullanılacak.
- İleride CAD/manufacturing tarafına aktarılacak.

## Temel karar

Motor mount bilgisi project-level ayrı bir liste olmayacak. Her motor component kendi `mount` özelliklerini taşıyacak.

Motor component:

```text
org.setuav.core:motor
├── electrical properties
├── performance properties
└── parameters.mount
```

## Veri modeli

Motor component içindeki veri:

```json
{
  "id": "motor-01",
  "type": "org.setuav.core:motor",
  "parameters": {
    "kv": 900,
    "max_power": 1200,
    "mount": {
      "target_id": "main-wing",
      "position": "front",
      "offset": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0
      },
      "orientation": {
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0
      }
    }
  }
}
```

Alanlar:

- `target_id`: Geometry tarafından yayınlanan mount hedefi.
- `position`: `front` veya `rear`.
- `offset`: Seçilen mount frame’e göre motor mount noktasının offset’i.
- `orientation`: Motor ekseninin mount frame’e göre yönelimi.

Sol/sağ motor ayrı bir mount modeli olmayacak. Simetrik geometry ve propulsion mantığı gerektiğinde iki tarafı türetecek.

## Geometry plugin sorumlulukları

Geometry plugin mount edilebilir geometry hedeflerini yayınlayacak.

### Mount target türleri

```text
wing
fuselage_segment
```

### Mount target verisi

```text
MountTarget
├── id
├── type
├── parent_id
└── frames
    ├── front
    └── rear
```

Örnek hedefler:

```text
main-wing
horizontal-tail
vertical-tail
fuselage/segment-01
fuselage/segment-02
```

### Geometry işlevleri

- Lifting surface’leri mount target olarak yayınlamak.
- Fuselage segmentlerini mount target olarak yayınlamak.
- Stable target ID üretmek ve korumak.
- Target için `front/rear` mount frame hesaplamak.
- Motor mount noktası ve yönelimini hesaplamak.
- Pervane çapına göre clearance circle preview üretmek.
- Mount yüzeyi ile pervane clearance kesişimini kontrol etmek.

Geometry’nin sorumluluğu:

> Nerelere mount edilebilir ve o noktadaki frame nedir?

Geometry plugin motorun kendisini veya propulsion kararını bilmeyecek.

## Propulsion plugin sorumlulukları

Motor component editor’ına mount bölümü eklenecek:

```text
Motor
└── Mount
    ├── Target
    ├── Position: Front / Rear
    ├── Offset
    └── Orientation
```

### Propulsion işlevleri

- Geometry’den mount target listesini almak.
- Motor için target seçmek.
- `front/rear` seçmek.
- Offset ve orientation düzenlemek.
- Motorun seçili pervanesiyle geometry preview istemek.
- Clearance sonucunu göstermek.
- Motor mount bilgisini propulsion analizlerine aktarmak.

Propulsion’ın sorumluluğu:

> Motor hangi mount target’a, hangi konfigürasyonla kurulmuş?

## Motor ve pervane ölçüleri

- Motor ve pervane boyutları component/catalog verisinden gelecek.
- Mount modeli bu ölçüleri tekrar tanımlamayacak.
- Pervane clearance çemberinin yarıçapı:

```text
propeller.diameter / 2
```

- Motor mount noktası ile clearance circle boyutu birbirinden ayrı kavramlar olarak tutulacak.

## Kullanıcı akışı

1. Kullanıcı propulsion workspace’te motor component’ini açar.
2. Motorun `Mount` bölümünden geometry target seçer.
3. `Front` veya `Rear` seçer.
4. Gerekirse offset/orientation düzenler.
5. Studio, seçili pervane çapıyla clearance circle’ı geometry viewport’unda gösterir.
6. Clearance veya geçersiz target durumu kullanıcıya bildirilir.
7. Veriler motor component’iyle birlikte project dosyasına kaydedilir.

## Uygulama sırası

1. Geometry target ve frame veri modelini tanımla.
2. Wing ve fuselage segmentleri için stable target üretimini ekle.
3. Geometry mount-frame hesaplama API’sini ekle.
4. Motor modeline `mount` property erişimini ekle.
5. Motor editor’ına target/position/offset/orientation alanlarını ekle.
6. Geometry preview ve clearance analizini propulsion plugin’e bağla.
7. Project save/load davranışını test et.
8. Motor kurulumu değiştiğinde propulsion analizlerinin güncellendiğini test et.
9. Target silinmesi veya değişmesi durumunda validation ekle.


