# DACAI panelleri

[English](dacai.md) · [Türkçe](dacai_TR.md) · [Dokümantasyon](README_TR.md)

Bazı Creality yazıcılar, örneğin **Ender 3 Max Neo**, DWIN T5UIC1 paneline benzeyen ancak **Guangzhou DACAI** (大彩) tarafından üretilen 4,3 inç düğmeli bir ekranla gelir. Bu panelin yazılımı T5UIC1 komut setinin büyük bölümünü taklit eder; bu nedenle Petrel onu panele özel küçük bir sürücüyle kullanabilir.

## Paneli tanıma

- Panelin microSD güncelleme klasörünün adı `DWIN_SET` değil, **`private`**'tır (`icon/`, `image/`, `truefont/`, `config.txt` içerir).
- Kartta bir **Allwinner F1C100s** işlemci ve çoğu zaman 大彩 etiketi bulunur.

## Panel yazılımı

Referans panel, Creality'nin resmi Ender 3 Max Neo ekran yazılımıyla çalışır: Creality
`SW-V1.4.1_C` paketindeki (20 Ekim 2022) `Display Firmware` klasöründe bulunan `firmware.zlib`
(derleme 18 Mayıs 2022). Animasyonlar (`0x28`), sanal alanlar (`0x25`/`0x26`) ve `0x27` bit 7
davranışı panelin daha eski fabrika yazılımıyla da doğrulandı. **Önizlemeler (`0x70`), resim
yükleme (`0x33`), 15'ten büyük resim ID'leri ve dolayısıyla ikon sprite sayfaları yalnızca resmi
yazılımla doğrulandı.** İkonlar veya önizlemeler boş kalırsa önce paneli güncelleyin: bu paketteki
`firmware.zlib` dosyasını ve `private` klasörünü FAT32 bir kartın köküne kopyalayın (ayırma birimi
4096), kart takılıyken panele güç verin ve ardından kartı çıkarın.

> **⚠️ Bir DACAI paneline asla `DWIN_SET` klasörü kopyalamayın.** DWIN ve DACAI kaynak paketleri birbirinin yerine kullanılamaz.

## Etkinleştirme

`./configure.sh` çalıştırın, **Display panel** menüsünü açın, **DACAI panel** seçeneğini işaretleyin ve isterseniz daha hızlı bir **DACAI host UART speed** seçin. Kaydedin, çıkın ve Apply sorusunu onaylayın. Ayarlar `Petrel.env` içinde `PETREL_DACAI=1` ve `PETREL_DACAI_BAUD` olarak saklanır.

| Hız | Kullanım |
|---|---|
| 115200 | Varsayılan; panelin açılış hızı |
| 230400, 460800, 921600 | Daha hızlı görsel yükleme ve önizleme; üçü de referans panelde hatasız çalıştı |

Panel, yükseltilmiş hızı güç kesilene kadar korur. Petrel kapanırken hızı 115200'e geri alır ve paneli beklerken iki hızı da dener; böylece çöken veya yeniden başlatılan servis paneli yine bulur.

## Petrel'in yüklediği içerik

microSD kart gerekmez. İlk açılışta Petrel UART üzerinden şunları yükler:

| Resim | İçerik |
|---|---|
| 0 | Açılış görseli |
| 1 | Ortak arayüz görseli (Info QR bölgeleri) |
| 16 ve üzeri | İkon sprite sayfaları: 272×480 JPEG sayfalarına yerleştirilmiş ikon kütüphanesi |

İlk yükleme 460800 baud'da yaklaşık 15 saniye sürer. İçerik parmak izleri panelin Data Flash alanında saklanır; sonraki açılışlarda yalnızca değişen resimler yüklenir.

DACAI panelleri ikonları yalnızca kendi ikon dosyalarından okur ve bu dosyalar UART üzerinden yazılamaz. Bu yüzden Petrel her ikonu sanal ekran alanı 1'deki bir sprite sayfasından kopyalayarak çizer ve ikon animasyonlarını (açılış ilerlemesi, fan) host tarafında ilerletir. Diğer Petrel özellikleri değişmeden çalışır.

## microSD güncellemesinden sonra

Paneli microSD kartından güncellemek yüklenen resimleri siler, ancak parmak izleri kalır; bu nedenle Petrel bunu fark etmez. Her şeyi yeniden yüklemek için:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/dacai_artwork.py --serial-port /dev/ttyS0
sudo systemctl start Petrel.service
```

`/dev/ttyS0` yerine yapılandırmanızdaki UART'ı kullanın.

## Sınırlar

- **Yazı tipi:** Metinler panelde kurulu TrueType yazı tipini (`private/truefont`) kullanır. Petrel yazı tipi yüklemez.
- **Yardımcı UART yok:** Panelde ikinci bir UART bulunmaz; bu nedenle [DWIN yardımcı UART](dwin-uart_TR.md) ve ekrana bağlanan NFC okuyucular kullanılamaz. Büyük NFC yaklaşma animasyonları yüklenmez.
- **Siyah saydamdır:** DWIN ikon çiziminde olduğu gibi saydam ikonlarda siyaha yakın pikseller arka plan sayılır; çok ince koyu ayrıntılar kaybolabilir.
- **Önizlemeler opaktır:** `0x70`, siyah zemini `0x24` gibi filtreleyemez; bu yüzden Petrel baskı önizlemelerini siyah yerine arayüz arka planına (veya baskı kutucuğuna) yerleştirir. Panel yalnızca 4:2:0 JPEG çözdüğü için model kenarlarında en fazla 2 piksellik ince bir renk saçağı kalabilir.
- **Emülatör:** Ekran görüntüleri DWIN çizim yolunu gösterir.

## Geliştiriciler için

`DacaiDriver` (`petrel/hardware/dwin/dacai.py`), `T5UIC1Display` sınıfından türetilir; DWIN yolu
değişmeden kalır. Ekran kodunu değiştirirken şu noktalara dikkat edin:

- **Çizimleri sürücü metotları üzerinden yapın.** `show_icon`, `configure_animation`,
  `set_animation_mask`, `copy_cache`, `show_sram_jpeg`, `set_backlight` ve `prepare_picture`
  yeniden tanımlanmıştır. Ham opcode'ları `_send` ile gönderen kod DACAI işlemesini atlar.
- **İkonlar için ek iş gerekmez.** Sprite sayfaları çalışma anında `assets/icons` klasöründen
  oluşturulur (`petrel/artwork/sprites.py`); yeni veya değişen ikonlar bir sonraki açılışta
  yüklenir. `sprites.SKIPPED_IDS` içindeki ikon ID'leri (büyük NFC kareleri) yüklenmez.
- **Kütüphane 2 animasyonları** host tarafından ilerletilir (`poll_host_animations`, arayüz
  tick'inden çağrılır). Aralık `0x28` birimini (10 ms) korur; en kısa kare süresi 40 ms'dir.
- **Ayrılmış kaynaklar:** resim 0 (açılış), 1 (ortak görsel) ve 16 ve üzeri (sprite sayfaları);
  DWIN kayıtlarına ek olarak Data Flash `0x0600`–`0x083F` (sprite kontrol kayıtları).
- **DACAI'de bulunmayanlar:** `0x24` (`show_sram_jpeg` kullanın), `0x39`/`0x3A` (yardımcı UART
  yok), ikon dosyası yazma. Yeni bir opcode için `DacaiDriver` içinde yeniden tanımlama
  gerekebilir; aşağıdaki tabloya bakın.
- **Resimlere yeni görsel:** JPEG baytlarını `write_sram` + `store_sram_as_picture` öncesinde
  `lcd.prepare_picture()` üzerinden geçirin (baseline 4:2:0, DACAI'de en fazla 32.764 bayt).
- **Testler:** `tests/test_dacai_panel.py` protokol farklarını, sprite yerleşimini/senkronunu ve
  host animasyonlarını kapsar.

## DWIN T5UIC1'den farklar

Referans panelde (Ender 3 Max Neo, kart Rev 1.5) ölçülmüştür. Sürücü `petrel/hardware/dwin/dacai.py` dosyasındadır.

| Komut | DACAI davranışı | Sürücü |
|---|---|---|
| `0x24` SRAM JPEG | Uygulanmamış; DACAI `0x70 x y adres` opak çizer | `0x70` kullanır; önizlemeler arayüz arka planına, RGB565 basamağının ortasında, JPEG kalitesi 100 ile yerleştirilir |
| `0x27` alan kopyalama | Bit 7 ters: ayarlı = siyah saydam | Bit 7'yi tersine çevirir |
| `0x33` SRAM → resim | 32 KB'nin tamamını `image/<id>.jpg` olarak saklar; dosya `FF D9` ile bitmelidir; 15'ten büyük ID'ler kabul edilir | JPEG'leri COM segmentiyle 32 KB'ye tamamlar |
| İkon kütüphanesi | İkon dosyaları UART üzerinden yazılamaz | Sprite sayfaları + `0x25`/`0x27` |
| `0x28` animasyon | Yalnızca panelin kendi ikon dosyaları için | Animasyonlar host tarafından ilerletilir |
| `0x31`/`0x32` Data Flash | Yazma, çerçevesiz `A5 'OK'` ile onaylanır | Onay olarak kabul edilir |
| `0x30` arka ışık | 0–63 ile sınırlı | 0–255 değeri 4–63'e eşlenir (0 = kapalı) |
| `0x38` | Host UART hızını güç kesilene kadar değiştirir | İsteğe bağlı hızlı bağlantı |
| `0x39`/`0x3A` | Uygulanmamış | Yardımcı UART yok |
