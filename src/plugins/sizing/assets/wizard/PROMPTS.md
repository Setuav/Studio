# SetUAV Studio - Sizing Wizard 3D Görsel Promptları

Bu dokümanda Boyutlandırma Sihirbazı (Sizing Wizard) seçenekleri için kullanılan ve kullanılacak olan görsel üretim promptları listelenmiştir.

Tüm görseller aynı görsel dilde, kamera açısında ve materyal tonunda üretilmektedir.

---

## Genel Görsel Standartları (Style Guidelines)

* **Model Stili:** OpenVSP mühendislik tarzı, katı 3D CAD kil model (matte clay render).
* **Malzeme:** Düzgün, mat açık gri kil (light-gray clay), dokusuz, parlaklıksız.
* **Işıklandırma:** Yumuşak 3 noktalı stüdyo aydınlatması, gölgeli ambient occlusion.
* **Arka Plan:** Düz koyu antrasit (`#1a1a1f`).
* **Kamera Açısı:** Yüksek üçte bir (isometric 3/4) açı, uçağın burnu sol-alt köşeye bakacak şekilde.
* **En-Boy Oranı:** 4:3.
* **Negatif Filtre:** Kokpit camı/penceresi yok, iniş takımı/tekerlek yok, pervane/motor yok (itki başlığı hariç), panel çizgisi yok, kaplama/çıkartma yok.

---

## 1. Başlık: Genel Konfigürasyon Tipi (Aircraft Architecture)

### 1.1 Konvansiyonel (Conventional)
* **Dosya:** `config_conventional.jpg`
```text
Professional 3D CAD clay model of a conventional fixed-wing UAV aircraft, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Streamlined fuselage, high straight tapered main wing, conventional empennage (single vertical stabilizer and horizontal tail at the rear). Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 1.2 Pod ve Boru Kuyruk (Pod-and-Boom)
* **Dosya:** `config_pod_boom.jpg`
```text
Professional 3D CAD clay model of a pod-and-boom fixed-wing UAV aircraft, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Rounded aerodynamic front fuselage pod, high wing mounted on the pod, slender tubular tail boom extending rearward from the pod to an inverted T-tail / conventional tail empennage at the back. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 1.3 İkiz Kirişli (Twin-Boom)
* **Dosya:** `config_twin_boom.jpg`
```text
Professional 3D CAD clay model of a twin-boom fixed-wing UAV aircraft, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Central fuselage pod, high main wing, two slender parallel tail booms extending rearward from each wing into twin vertical fins joined by a high horizontal stabilizer bridge at the rear. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 1.4 Uçan Kanat (Flying Wing)
* **Dosya:** `config_flying_wing.jpg`
```text
Professional 3D CAD clay model of a tailless flying wing UAV (swept blended delta wing), OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Pure flying wing with integrated center body, swept leading edge, vertical winglet fins at both wingtips, no tail boom, no empennage. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

---

## 2. Başlık: Kanat Konumu ve Düşey Yerleşimi (Wing Placement)

### 2.0 Tek Prompt ile 3 Seçeneği Birlikte İsteme (Önerilen)

#### Seçenek A: Tek Seferde 3 Ayrı Görsel Üretmesini İsteme
Modelden aynı sohbette sırasıyla 3 ayrı görsel vermesini istemek için tek prompt:

```text
Generate 3 separate 3D CAD clay model images of the same conventional fixed-wing UAV, demonstrating the 3 different wing vertical placement options. Keep the fuselage shape, tail empennage, lighting, camera angle, and style completely identical across all 3 images:

Image 1 (wing_high.jpg - High-Wing): Straight tapered main wing mounted directly on top of the fuselage roof.
Image 2 (wing_mid.jpg - Mid-Wing): Straight tapered main wing mounted at the exact vertical centerline/equator of the fuselage body.
Image 3 (wing_low.jpg - Low-Wing): Straight tapered main wing mounted at the bottom belly of the fuselage with a slight upward dihedral angle.

Style specifications for all 3 images: OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

#### Seçenek B: Tek Karede Yan Yana 3'lü Karşılaştırma (Side-by-Side Triptych - 16:9)
*(Bu tek geniş görseli ürettiğinde, Python ile saniyeler içinde 3 eşit parçaya bölüp `wing_high.jpg`, `wing_mid.jpg`, `wing_low.jpg` yapabiliriz)*

```text
A side-by-side technical comparison showing three identical fixed-wing UAVs in 3D CAD clay model style, arranged in a horizontal row from left to right, comparing wing vertical placements:

1. Left Aircraft: High-Wing configuration (main wing mounted flush to the very top roof of the fuselage).
2. Center Aircraft: Mid-Wing configuration (main wing passing directly through the exact vertical center/equator of the fuselage).
3. Right Aircraft: Low-Wing configuration (main wing mounted to the bottom belly of the fuselage with slight dihedral).

All three aircraft feature the exact same streamlined fuselage shape, same dimensions, and same conventional tail. High three-quarter isometric view with each aircraft nose pointing toward the bottom-left corner. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Seamless solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, 16:9 widescreen aspect ratio.
```

---

### Ayrı Ayrı Üretmek İçin Bağımsız Promptlar:


### 2.1 Üstten Kanat (High-Wing)
* **Dosya:** `wing_high.jpg`
*(Not: `config_conventional.jpg` görseli zaten üstten kanattır, dilerseniz doğrudan kopyalayabilir veya sıfırdan üretebilirsiniz)*
```text
Professional 3D CAD clay model of a conventional fixed-wing UAV aircraft highlighting high-wing configuration, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Streamlined fuselage, high straight tapered main wing mounted directly on top of the fuselage, conventional empennage (single vertical stabilizer and horizontal tail at the rear). Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 2.2 Ortadan Kanat (Mid-Wing)
* **Dosya:** `wing_mid.jpg`
```text
Professional 3D CAD clay model of a conventional fixed-wing UAV aircraft highlighting mid-wing configuration, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Streamlined fuselage, mid-mounted straight tapered main wing passing through the exact vertical center of the fuselage, conventional empennage (single vertical stabilizer and horizontal tail at the rear). Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 2.3 Alttan Kanat (Low-Wing)
* **Dosya:** `wing_low.jpg`
```text
Professional 3D CAD clay model of a conventional fixed-wing UAV aircraft highlighting low-wing configuration, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Streamlined fuselage, low-mounted straight tapered main wing attached to the bottom of the fuselage with slight dihedral angle, conventional empennage (single vertical stabilizer and horizontal tail at the rear). Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no propellers, no motor, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```



---

## 3. Başlık: Kuyruk Tipi (Tail Configuration)

> **Not:** Kadrajda büyük gövde ve kokpit yer almaz. Kamera kuyruğun hücum kenarlarına (önden-çapraz) bakar; yöneliş yine uçağın burnu sol-alta bakacak şekildedir. Kuyruk yalnızca ince bir karbon/alüminyum kuyruk borusuna (tubular boom) montelidir.

### 3.1 Konvansiyonel Kuyruk (Conventional Tail)
* **Dosya:** `tail_conventional.jpg`
```text
Professional 3D CAD clay model of an isolated Conventional Tail empennage, OpenVSP engineering style. Front three-quarter isometric view facing the leading edges of the tail surfaces, oriented with the aircraft flight direction pointing toward the bottom-left corner of the frame. Minimal fuselage: the tail is mounted on a very slender, simple tubular tail boom that enters from the bottom-left and terminates at the tail. No large fuselage body, no cabin, no cockpit windows, no wings. The empennage consists of a single vertical stabilizer fin and a horizontal tailplane mounted to the base. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 3.2 T-Kuyruk (T-Tail)
* **Dosya:** `tail_t_tail.jpg`
```text
Professional 3D CAD clay model of an isolated T-Tail empennage, OpenVSP engineering style. Front three-quarter isometric view facing the leading edges of the tail surfaces, oriented with the aircraft flight direction pointing toward the bottom-left corner of the frame. Minimal fuselage: the tail is mounted on a very slender, simple tubular tail boom that enters from the bottom-left and terminates at the tail. No large fuselage body, no cabin, no cockpit windows, no wings. The empennage consists of a single vertical stabilizer fin with the horizontal stabilizer mounted directly at the very top tip of the vertical fin forming a clean distinct T-shape. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 3.3 V-Kuyruk (V-Tail / Ruddervators)
* **Dosya:** `tail_v_tail.jpg`
```text
Professional 3D CAD clay model of an isolated V-Tail empennage, OpenVSP engineering style. Front three-quarter isometric view facing the leading edges of the tail surfaces, oriented with the aircraft flight direction pointing toward the bottom-left corner of the frame. Minimal fuselage: the tail is mounted on a very slender, simple tubular tail boom that enters from the bottom-left and terminates at the tail. No large fuselage body, no cabin, no cockpit windows, no wings. The empennage consists of two angled stabilizer surfaces extending upward in a symmetrical V-shape (ruddervators) from the boom, with no vertical fin. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 3.4 Ters V-Kuyruk (Inverted V-Tail)
* **Dosya:** `tail_inverted_v.jpg`
```text
Professional 3D CAD clay model of an isolated Inverted V-Tail empennage (like Bayraktar TB2 / RQ-7 style), OpenVSP engineering style. Front three-quarter isometric view facing the leading edges of the tail surfaces, oriented with the aircraft flight direction pointing toward the bottom-left corner of the frame. Minimal airframe: the tail is mounted on TWO parallel slender tubular tail booms (twin booms) entering from the bottom-left. The empennage consists of two angled stabilizer surfaces joined at the top center and slanting downward in a clean inverted V-shape (^), connected directly to the two twin tail booms. No large fuselage body, no cabin, no cockpit, no wings. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

---

## 4. Başlık: İtki ve Motor Yerleşimi (Propulsion Layout)

> **Kullanım Yöntemi:** Google AI Studio'ya `config_conventional.jpg` görselini yükleyin ve uçağın gövde/kuyruk geometrisini birebir koruyarak yalnızca motor eklemesini isteyin:

### 4.1 Çekici Motor (Tractor Propeller — Burun)
* **Referans Görsel:** `config_conventional.jpg`
* **Dosya:** `prop_tractor.jpg`
```text
Modify this exact 3D CAD model image:
Add a single tractor propeller with a streamlined nose spinner mounted directly to the very front nose of the fuselage, pulling the aircraft forward. Keep the exact same fuselage shape, high-wing, conventional tail, camera angle (isometric nose facing bottom-left), light-gray clay material, and dark charcoal background (#1a1a1f).
```

### 4.2.A İtici Motor (Pusher Propeller — Pilon Tipi / Skywalker Tarzı)
* **Referans Görsel:** `config_conventional.jpg`
* **Dosya:** `prop_pusher_pylon.jpg`
```text
Modify this exact 3D CAD model image:
Add an electric motor pod with a 2-blade pusher propeller mounted on top of the fuselage spine, directly behind the wing trailing edge. The propeller faces rearward to push the aircraft forward. The front nose of the fuselage remains completely clean, rounded, and empty with no propeller. Keep the exact same fuselage shape, high-wing, conventional tail, camera angle, light-gray clay material, and dark charcoal background (#1a1a1f).
```

### 4.2.B Talon Tarzı Tam İtici (True Rear Pusher — X-UAV Talon / Mini Talon Tarzı)
* **Dosya:** `prop_pusher_talon.jpg` (veya `prop_pusher.jpg`)
```text
Professional 3D CAD clay model of an X-UAV Talon style true rear-pusher fixed-wing UAV, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Streamlined aerodynamic fuselage pod with a blunt rounded camera nose, high straight-tapered main wings. Symmetrical V-tail empennage mounted on the rear fuselage. At the very rear tail cone tip of the fuselage (behind the V-tail), a single 2-blade pusher propeller with spinner is mounted, pushing the aircraft forward from the very tail tip. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```

### 4.3 Çift Çekici Motor (Twin Tractor — Kanat Önü)
* **Referans Görsel:** `config_conventional.jpg`
* **Dosya:** `prop_twin.jpg` (veya `prop_twin_tractor.jpg`)
```text
Modify this exact 3D CAD model image:
Add two streamlined engine nacelles with 2-blade propellers and spinners mounted symmetrically on the leading edges of the wings (one motor on the left wing, one motor on the right wing), pulling the aircraft forward. The central fuselage nose remains completely clean, smooth, and empty with no propeller. Keep the exact same fuselage shape, high-wing, conventional tail, camera angle, light-gray clay material, and dark charcoal background (#1a1a1f).
```

### 4.4 Kanattan İtici Motor (Wing-Mounted Pusher — Kanat Firar Kenarı İtici)
* **Referans Görsel:** `config_conventional.jpg` (veya sıfırdan)
* **Dosya:** `prop_wing_pusher.jpg`
```text
Modify this exact 3D CAD model image:
Add two streamlined engine nacelles on the wings with 2-blade pusher propellers mounted at the trailing edge of each wing, facing rearward to push the aircraft forward. The front nose and the wing leading edges remain completely clean, smooth, and empty with no propellers. Keep the exact same fuselage shape, high-wing, conventional tail, camera angle, light-gray clay material, and dark charcoal background (#1a1a1f).
```

#### Sıfırdan Metin ile Üretmek İçin (Kanattan İtici):
```text
Professional 3D CAD clay model of a twin wing-pusher fixed-wing UAV, OpenVSP engineering style, high three-quarter isometric view with the aircraft nose pointing toward the bottom-left corner of the frame. Two streamlined engine nacelles mounted on the wings with 2-blade pusher propellers located at the trailing edge of the wings facing rearward, pushing the aircraft forward. The front fuselage nose and wing leading edges are completely clean and smooth with no propellers. High-wing, conventional tail. Clean solid matte light-gray clay material, soft directional studio lighting, subtle ambient occlusion shadows, smooth aerodynamic surfaces. Solid dark charcoal background (#1a1a1f). No cockpit windows, no canopy, no landing gear, no textures, no panel lines, no markings, isolated CAD rendering, 4:3 aspect ratio.
```
