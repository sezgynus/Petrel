# Yönetilen LCD ikonları

[English](README.md) · [Türkçe](README_TR.md)

Baseline **4:2:0 JPEG** dosyalarını buraya ekleyin veya mevcut olanları değiştirin. Dosya adı ikon ID'siyle başlamalı: `092.jpg`, `092-about.jpg` veya `092_about.jpeg`. ID aralığı 0–255'tir; her ID yalnız bir dosyada kullanılabilir. Mevcut ID'lerin anlamı korunur. ID ve içerik aynı kalırken dosya adını değiştirmek yükleme başlatmaz. Yeni görsel kütüphaneye girer; ID'nin arayüzde nerede gösterileceğini UI kodu seçer.

JPEG'ler boyutlandırılmadan ve yeniden sıkıştırılmadan korunur. Progressive JPEG, diğer renk örnekleme biçimleri, yinelenen ID ve 32767 bayttan büyük görseller reddedilir. Kütüphane Picture Flash 2–15 slotlarına sığmalıdır; resim 0 Petrel açılış görselidir, resim 1 ortak UI görsel sayfasıdır ve ikon kütüphanesi resim 2’den başlar.

Uygulama güncellemesinden sonraki ilk LCD bağlantısında bu klasörden kütüphane oluşturulur. Paketleyici önce büyükten küçüğe best-fit yerleşimi oluşturur; ardından her önceki bloğu dolduracak JPEG alt kümesini bayt düzeyinde bitset dinamik programlamasıyla arayarak boşlukları birleştirmeyi dener. İyileştirme aynı veya daha az blokta daha büyük kesintisiz boşluk sağlarsa seçilir; aksi durumda geçerli başlangıç yerleşimi korunur. ID sırası fiziksel yerleşimden bağımsızdır. Her bloğun son baytı ayrılır ve UART yazımına dahil edilmez. Hiçbir JPEG blok sınırını geçmez.

Yalnız değişen bloklar yüklenir; tablo bloğu en son yazılır. Paneldeki kayıt tamamlanan blokları saklar; sonraki açılış eksik yüklemeyi tamamlar. Değişmeyen kütüphanede Flash yazılmaz. Başarısız Picture Flash denemesi aynı süreçte tekrarlanmaz. Yükleme ilerlemesi ve hatalar loglarda yer alır.

Çalışma sırasında kullanılan paketin aynısını dışa aktarın:

```bash
python tools/pack_icon_library.py assets/icons /tmp/2.ICO --library 2
```

Emülatör de bu JPEG kaynaklarını kullanır. `assets/emulator/2.ICO` referans çıktıdır; otomatik güncellemenin kaynağı değildir.

Özel UI ikonları 100–109 ve 124 ID'lerini kullanır. MMU 100/101, Display 108/109 ID'leriyle seçili olmayan/seçili 110×100 ana menü ikonlarını kullanır; boyutlar mevcut ana menü yerleşimine uyar; normal ve seçili Graphite yüzeyleri farklıdır. Boş makara 124 ID’sini kullanır. Metal makara yan parçaları 1–7 genişlikleri için 110–123 ID'lerini kullanır; dar alanlarda ayrı tam makara görselleri gerekmez. Sembolik eşleştirme `lcd_resources.py` içindedir. Tüm UI ikonları doğrudan kütüphane 2'den çizilir.

Panel kaynaklarını yeniden yüklediğinizde, kayıt eski kurulumu tarif ediyor olabileceğinden zorla yeniden yükleyin:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

Yazma onayları ve kayıt geri okuması doğrulanır; Picture Flash'ın kendisi geri okunmaz. Yeni ikon yerleşimini fiziksel ekranda kontrol edin.

## Graphite

Graphite; ışık, parlaklık, ses ayarları, hareket parametreleri, kalibrasyon ve profiller için 210–234 ID’lerini ekler. Düzenlenebilir SVG kaynakları `assets/icon-source` içindedir; JPEG üretmek için `python tools/render_icon_sources.py` çalıştırın (geliştirme bağımlılığı: CairoSVG). Siyah JPEG zemini panelin şeffaf/enhanced ikon modu ile filtrelenir; menü ve dashboard yüzeyleri korunur. İkon paketi 2 numaralı slotta başlar, 2–15 slotlarını kullanabilir; 512 baytlık metadata kaydı Data Flash `0x0200–0x03FF` aralığındadır.

## Print butonları, switchler ve fan görselleri

Print butonları yuvarlatılmış yüzeyi, seçim çerçevesini ve Lucide simgesini tek JPEG içinde taşır; etiketler panelin **0 numaralı fontuyla** native metin olarak çizilir. Normal dar butonlar **243–247**, seçili karşılıkları **125–129** (78×36); tamamlanan baskının Tune/Close çiftleri **130–133** (119×36) ID'lerini kullanır. AFTER JOB switchleri **248/249** (27×12) kullanır. Normal/seçili siluetleri aynı tutun: üretici aynı nötr opak kenarı taşıyan keskin yuvarlak maske kullanır; böylece filtrelenen JPEG kenarlarında önceki durumun pikselleri kalmaz.

Fan kareleri **235–242**, dashboard'un **RGB565 `0x18C4`** zemininde nötr fan simgesiyle üretilir. JPEG yuvarlamasının aynı RGB565 renginde kalması için SVG'de renk basamağının ortasındaki `#1c1a24` RGB değeri kullanılır. Native animasyonda (`0x28`) arka plan filtresi seçeneği bulunmadığından bu kareler opaktır; duran fan da aynı opak çizimi kullanır. SVG'den yeniden üretirken bu zemini koruyun. Fan ve tam buton JPEG'leri **kalite 100**, baseline **4:2:0** kullanır. Diğer üretilen ikonlar kalite 94 kullanır. JPEG'i tekrar sıkıştırmak yerine SVG'den üretin. Lucide kaynak lisansı: [Lucide lisansı](../icon-source/Lucide-LICENSE.txt).

## Paket boyutu ve ayrılan alan

Mevcut referans paket **13×32 KiB = 416 KiB**, yani **2–14** slotlarını kullanır. Ayrılan üst sınır **14×32 KiB = 448 KiB**, yani **2–15** slotlarıdır; **15** büyüme için kullanılabilir. Mevcut kaynaklarla kullanılabilir boşluk **35.049 bayttır**: mevcut pakette 2.282 bayt ve ek slotta 32.767 bayt. Bu ayrılmış blok alanıdır; birebir JPEG veri bütçesi değildir: dizin, yerleşim boşlukları ve blokların ayrılmış son baytları da alan tüketir. Picture Flash, **0x0200–0x03FF adresindeki 512 baytlık Data Flash metadata kaydından** ayrıdır. Dışa aktarma aracı artık yönetilen kütüphaneyi varsayılan alır; açık seçim için `--library 2` verin.

## JPEG uyumluluk kuralı

Yönetilen tüm ikonlar baseline RGB/YCbCr JPEG ve **4:2:0** örnekleme kullanmalıdır (`Pillow: subsampling=2`). `tools/render_icon_sources.py` ile doğrudan SVG’den üretin; JPEG’leri tekrar tekrar sıkıştırmayın. Fiziksel T5UIC1 testinde 4:4:4, hem Flash hem baytları geri okunarak doğrulanmış SRAM üzerinden seçili ana menü kartlarını ve homing görselini bozdu; 4:2:0 düzgün çizildi. Temiz emülatör görüntüsü panelin JPEG çözücüsünü doğrulamaz. Kaynak yükleyici diğer örnekleme biçimlerini panele erişmeden reddeder; CI tüm ikonların biçimini ve ICO’nun kaynaklarla eşleşmesini kontrol eder. Görsel güncellemelerden sonra seçili/seçili olmayan ana menü kartlarını, homing’i, küçük menü/durum ikonlarını ve animasyonu fiziksel panelde kontrol edin.

Maintenance mevcut küçük Graphite menü ikonlarını yeniden kullanır. Eski büyük kutu ID’leri 157–163 kaldırılmıştır; paketlenmez ve UI tarafından kullanılmaz.

Küçük bakım amaç ikonları 164–167 ID’leridir (20×20): onay çemberi, aktivite dalgası, ampul ve takvim. Wi-Fi gücü için **168 (zayıf), 169 (orta), 170 (güçlü)** ID’leri kullanılır (20×20). JPEG’lerin siyah zemini, mevcut native gelişmiş şeffaflık filtresiyle kaldırılır; düzenlenebilir SVG kaynakları `assets/icon-source` içindedir. Tümü Graphite çizgisini ve baseline 4:2:0 JPEG kodlamasını izler. Referans paket artık 13×32 KiB yer kaplar.

NFC ayarları menü satırı, tanınan NFC N siluetini ortak 20×20 Graphite turkuaz tarzında gösteren ikon **171** (`ICON_NFC`) kullanır. Salt okunur NFC özellik durumu Info düzenini izler ve işlem ikonu kullanmaz. Düzenlenebilir ikon kaynağı `assets/icon-source/171.svg` dosyasındadır.

NFC silueti [Pictogrammers Material Design Icons — nfc](https://github.com/Templarian/MaterialDesign/blob/master/svg/nfc.svg) kaynağından uyarlanmıştır; oranları korunmuş, yalnız eşit ölçekleme ve Graphite renklendirmesi uygulanmıştır. Kaynak atfı ve lisans [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt) dosyasındadır.

RFID ana menüsü, NFC N sembollü **172/173** normal/seçili ikonlarını (110×100) kullanır. Graphite kart yüzeyleri, seçim çerçevesi ve native etiket alanı diğer ana menü ikonlarıyla aynıdır; Info ikonunu paylaşmaz.

## NFC telefonu yaklaştırma animasyonu

Share via NFC, popup RGB565 `0x2967` zemininde **174–185** ID’li on iki opak 160×160 kare kullanır. DWIN native `0x28`, animasyon kanalı **2**, **20×10 ms** aralıkla **2,4 saniyede** döner; sunucuda kare zamanlayıcısı yoktur. 0/1 kanalları açılış/fan için korunur. Kapanma, tamamlanma, hata ve pencere değişimi yeniden çizimden önce kanal 2’yi durdurur. Başarısız paylaşımda ilk kare animasyonsuz gösterilir. Yeniden üretim: `python assets/icon-source/nfc-share/render.py`; eklenen NFC N-Mark bitmap’i onaylanan önizlemenin simgesini korur. N-Mark, NFC’yi tanımlar (NFC Forum).

## Küçük NFC paylaşım kontrolü

**186/187** ID’leri (`ICON_NFC_SHARE_NORMAL` / `ICON_NFC_SHARE_SELECTED`), **16×16** telefon, NFC N silueti ve paylaşım oku içeren normal/seçili **20×20** kontrollerdir. Mevcut 24 piksel satırlara, satır yüksekliğini artırmadan sığarlar. Normal durumda odak çerçevesi yoktur; seçili durumda aynı sınırlar içinde turkuaz çerçeve ve renkli zemin bulunur. Düzenlenebilir kaynaklar: `assets/icon-source/186.svg` ve `187.svg`; yeniden üretim: `python tools/render_icon_sources.py --ids 186 187`. NFC silueti, atfı [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt) içinde bulunan kaynağı yeniden kullanır. Info ekranında Software bölümünün Petrel satırında, sürüm numarasının hemen önünde kullanılır. Okuyucu paylaşım kabiliyeti doğrulandığında görünür; QR altında ayrı paylaşım satırı bulunmaz.

## NFC spool okutma animasyonu (ayrılmış kaynak)

**188–199** ID’leri (`ICON_NFC_SPOOL_FIRST` / `ICON_NFC_SPOOL_LAST`), onaylanan önizlemenin on iki opak **160×160** karesini içerir. Spool panele yaklaşır, NFC dalgaları yanar ve geri çekilir. Bu kaynak henüz hiçbir ekranda kullanılmaz; animasyon kanalı veya zamanlayıcı başlatılmaz. Gelecekteki kullanım için önerilen aralık 200 ms/kare (2,4 saniye/döngü).

Kayıpsız PNG kaynakları `assets/icon-source/nfc-spool` içindedir. Yeniden üretim: `python assets/icon-source/nfc-spool/render.py`; ardından referans ICO’yu yukarıdaki paketleme komutuyla güncelleyin. Yeni JPEG’ler Flash sınırına sığmak için kalite **84**, optimize edilmiş Huffman tabloları, baseline **4:2:0** kullanır; mevcut ikonlar değişmez. Paket **13×32 KiB = 416 KiB** ile ayrılmış 2–15 aralığında 2–14 slotlarını kullanır.

## NFC ayarları işlem ikonları

NFC Settings ve seçim alt menüleri Info yerine alana uygun ikonlar kullanır: RFID modülü **171**, arayüz **155** (çift yönlü veri okları), port/cihaz **156** (fiş), bağlantı hızı **220**, Kaydet **228**, bağlantı testi **165**. Cihaz listesi boş/yükleniyor/hata satırları da port ikonunu kullanır. Yeni 155/156 ikonları siyah filtrelenebilir zemin üzerinde 20×20 Graphite çizgisindedir; baseline 4:2:0, kalite 94 ve optimize edilmiş Huffman tabloları kullanır. SVG kaynakları `assets/icon-source/155.svg` ve `156.svg`; Pillow ile yeniden üretim: `python assets/icon-source/nfc-settings/render.py`. Yeni ikonlara alan açmak için spool kareleri kayıpsız PNG kaynaklarından kalite 84 ile yeniden kodlanmıştır; boyutlar ve animasyon içeriği değişmez. Paket 416 KiB içinde kalır.

## Otomatik boşluk birleştirme

Optimizasyon hem çalışma anındaki `build_library` hem ICO dışa aktarma/yeniden paketleme yolunda ortaktır; JPEG baytlarını, boyutları ve ikon ID’lerini değiştirmez. Girdi sırasından bağımsız deterministik yerleşim aynı kaynaklardan aynı ICO ve parmak izlerini üretir. Her blok için alt küme araması tamdır; blokların sırayla seçimi genel bin-packing optimumunu her gelecek ikon kümesi için garanti etmez. Sığan başlangıç yerleşimi kaybedilmez; ayrılan slot sınırı aşılırsa dosya üretilmez. Mevcut 234 ikon ve 13 blokta kullanılabilir **2.282 baytın tamamı son blokta** toplanır. Dizin 4096 bayttır ve her bloğun son baytı ayrılmış kalır. Gelecek kaynak değişikliklerinde kalan boşluk doğal olarak değişir. Mevcut paket önbelleği sayesinde arama UI karelerinde veya değişmeyen yeniden bağlantılarda tekrarlanmaz. İlk güncellemede yerleşimi değişen bloklar normal senkronizasyonla yüklenir.

## Kütüphane 3 veya 7’den geçiş

Bu güncellemeden sonraki ilk LCD bağlantısı CRC ile doğrulanmış metadata kaydını okur. Tamamlanmış eski dizin, yükleme başlayana kadar açılış animasyonunu sağlayabilir. İlk ikon bloğu değiştirilmeden önce tüm native animasyonlar durdurulur. Eski kütüphanenin hash kayıtları yeni başlangıç adresinde yeniden kullanılmaz: gereken bütün bloklar 2’den başlayarak yüklenir ve yeni dizin slot 2’ye en son yazılır. Doğrulanmış blok kayıtları yarıda kalan aktarımı devam ettirir; sıfır dizin hash’i kısmi kütüphaneden açılış animasyonu başlatılmasını engeller. Slot 0/1, ekran ayarları ve buzzer kayıtları korunur. SD kartla kaynak güncellemesi gerekmez. Sonraki değişmeyen bağlantılarda Flash yeniden yazılmaz. Referans çıktı, emülatör ve elle yeniden yükleme araçları `2.ICO` ile `lcd_resources.py` içindeki ortak kimliği kullanır. 14 blok hash’i mevcut 512 baytlık metadata kaydına sığar.

Elle tanısal yükleme, Picture Flash yazımından önce eski metadata kaydını geçersiz kılar ve doğrular; sonraki normal açılış yönetilen kaynakları otomatik geri yükler. Blok kayıtlı zorunlu kaynak yüklemesi için `tools/reload_icons.py` kullanın.
