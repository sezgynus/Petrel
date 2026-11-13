# LCD uyumluluğu

[English](lcd-assets.md) · [Türkçe](lcd-assets_TR.md) · [Dokümantasyon](README_TR.md)

## Desteklenen ekran

Petrel aynı 272×480 dikey arayüzü DWIN T5UIC1 ve uyumlu Creality DACAI panellerinde sunar. Ekran kasası veya yazıcı adı kontrolcü ailesini tek başına belirlemez. TJC ve ilgisiz DWIN modelleri bu desteğin kapsamında değildir. DWIN, DACAI ve TJC firmware/kaynak paketleri birbirinin yerine kullanılamaz.

- **DWIN T5UIC1:** Uyumlu 4,3 inç Ender 3 V2 paneli; T5UIC1 komutları ve ekran yönü **1** kullanılır. Stok font desteklenir, Petrel'in HZK fontu isteğe bağlıdır.
- **DACAI:** Örnek doğrulanmış donanım Ender 3 Max Neo revizyon 1.5'tir. Kartta Allwinner F1C100s ve çoğu zaman 大彩 etiketi bulunur; güncelleme klasörü `DWIN_SET` yerine `private` adını taşır. Ayrıntılı [firmware/test kapsamı](dacai_TR.md) başka revizyonları veya firmware sürümlerini otomatik doğrulamaz.

Kurulumda [panelinizi seçin](installation_TR.md#panelinizi-seçin). Panel seçimi otomatik algılanmaz; DWIN için **DACAI panel** kapalı, DACAI için açık olmalıdır.

## Panel özellikleri

| Özellik | DWIN T5UIC1 | DACAI |
|---|---|---|
| Baskı, Tune, hareket, kalibrasyon, MMU, Spoolman ve Maintenance | Kurulu Klipper/entegrasyon özelliklerine bağlı | Aynı ortak arayüz ve koşullar |
| Açılış, menü ikonları ve NFC/fan animasyonları | Yerel ikon kütüphanesi ve panel animasyonları | Otomatik yüklenen ikon sayfaları; kareleri host ilerletir |
| Baskı önizlemesi | Siyah arka plan filtresi | Arayüz zeminine birleştirilmiş opak önizleme |
| Parlaklık/karartma | Panel sürücüsü üzerinden | Aynı kontroller; panelin 0–63 aralığına eşlenir |
| Buzzer ve olay sesleri | Pi donanımsal PWM | Aynı; panel protokolünden bağımsız |
| Host'a bağlı NFC okuyucu | Desteklenir | Desteklenir; USB/UART/I²C/SPI okuyucu yeteneklerine bağlı |
| Ekran üzerinden ek seri port / bağlı NFC | İsteğe bağlı DWIN yardımcı UART | Desteklenmez; DACAI seçimi kurulu aracı servisini kaldırır |
| Ekran görüntüsü / uzak ekran | Desteklenir | DACAI komutları yorumlanır; fiziksel font/görünüm farklı olabilir |
| Font | Stok DWIN veya isteğe bağlı HZK | Panelde kurulu `private/truefont` TrueType; Petrel yüklemez |
| Host–ekran hızı | 115200 | 115200; isteğe bağlı 230400, 460800 veya 921600 |
| Stok kaynak kurtarma | Yalnız DWIN için orijinal DWIN_SET | Modele uygun DACAI firmware/`private` paketi; DWIN_SET kullanılmaz |

## Kalıcı LCD kaynakları ve stok görsellere dönüş

İki panelde de görseller kalıcıdır; Pi yazılımını kaldırmak stok görünümü geri getirmez. Açılış ve ortak görsel 0/1 numaralı resimleri kullanır. **DACAI**, ikon kütüphanesinin tamamını şu anda sekiz adet 272×480 JPEG sayfası olarak **16 ve üzeri** resimlere yükler; yaklaşık 320 KB toplam depolama kullanır. İlk yükleme referans panelde 115200'de yaklaşık 40 s, 460800'de 20 s sürer. Sonraki açılışlarda yalnız değişen resimler yüklenir. Hata eşitlemeyi başarılı saydırmaz; sonraki açılış yeniden dener. SD güncellemesi, boş ikonlar ve depolama sınırı için [DACAI kurtarma rehberine](dacai_TR.md) bakın.

### DWIN kaynak düzeni ve kurtarma

Aşağıdaki Picture Flash blok/ICO düzeni ve DWIN_SET kurtarması yalnız **DWIN** içindir.

> **⚠️ Stok görseller otomatik değiştirilir.** Orijinal Ender-3 V2 kaynakları Petrel'in modern arayüzünün ihtiyaç duyduğu tüm ikon durumlarını, animasyonları ve görselleri sağlamıyordu. Petrel, tutarlı görünüm ve hızlı yerel ikon çizimi için kalıcı **Picture Flash** belleğindeki kaynaklarını artık kendisi yönetir. Bu işlem **geçicî değildir** ve Petrel kaldırılınca geri alınmaz.

- **Açılış JPEG'i:** Petrel `assets/petrel_bootsplash.jpg` görselini Picture Flash **0** numaralı yuvaya eşitler.
- **Ortak UI JPEG’i:** Petrel `assets/petrel_shared.jpg` görselini Picture Flash **1** numaralı yuvaya eşitler. Info, QR bölgelerini bu sayfanın çözülmüş Area 1 önbelleğinden kopyalar.
- **2 numaralı ikon kütüphanesi:** `assets/icons/` içindeki baseline JPEG'ler 32 KiB bloklara paketlenir; **2** numaralı yuvadan başlayarak **2–15** aralığında yalnız değişen bloklar yazılır. Böylece menü ikonları, seçim durumları, baskı kontrolleri ve animasyon kareleri yeniden tekrar tekrar çizilmeden kullanılır.
- **Gereksiz yazmaları önleme:** İçerik parmak izleri ayrı bir kalıcı Data Flash alanında tutulur; eşleşen kaynaklar normalde atlanır. Bu parmak izleri **orijinal OEM görsellerin yedeği değildir**.
- **Otomatik üzerine yazılmayanlar:** LCD kernel'i ve font kaynakları. Baskı önizlemeleri geçici SRAM'e taşınır. Paketle sunulan ASCII fontu **isteğe bağlıdır** ve yalnız kullanıcı isterse SD kartla yüklenir.

**Stok Creality açılış görseline ve ikonlarına dönmek için**, Petrel'i durdurduktan sonra [orijinal DWIN_SET](../assets/stock-dwin/DWIN_SET) paketini LCD'nin microSD yuvasından yükleyin. Adımlar [orijinal DWIN'e dönüş rehberinde](restore-stock-dwin_TR.md) bulunur. Host yazılımını kaldırmak tek başına Picture Flash'ı geri yüklemez. Bu paket yalnızca **DWIN T5UIC1** içindir; DACAI/TJC ile kullanılamaz. LCD kaynakları yazıcının ana kart firmware'ini de geri yüklemez.

## Panel kurmadan veya değiştirmeden önce

Yalnız ekran boyutunu değil, kontrolcü ailesini ve kurulu kaynak paketini kontrol edin. Uygulama kurulum betiği LCD kernel firmware'ini veya LCD fontunu yüklemez. DWIN firmware çalışmaları için [T5UIC1 referansını](t5uic1-reference.md), DACAI için [DACAI referansını](dacai_TR.md) kullanın.

Kurulumdan sonra fiziksel ekranda menü yazılarını/ikonlarını, renkleri, önizlemeleri ve encoder gezinmesini inceleyin. Çalışan emülatör görüntüsü farklı panel/kaynak paketinde aynı görünümü garanti etmez.

## Baskı önizlemeleri

Önizlemeler Moonraker'dan gelir ve yeni panel kaynak paketi gerektirmez. Eksik thumbnail baskı başlatmayı engellemez. Görseller yeniden başlatma veya yeniden bağlantı sonrası tekrar hazırlanır; kurulu ikonların yerine geçmez. **DWIN:** Thumbnail’ler kalite 94 baseline 4:2:0 JPEG, siyah zemin ve panelin gelişmiş arka plan filtresini kullanır. Modelin koyu pikselleri alpha birleştirmesinden önce en az 48 parlaklık seviyesine yükseltilir; saf siyah koyu gri olur. Tam şeffaf pikseller ve kenar boşlukları siyah kalır, filtrelenince UI zemini görünür. Yarı şeffaf kenarlar panel filtresinde kesilebilir; fiziksel ekranda kontrol edin.

**DACAI:** Önizlemeler opaktır ve arayüz zeminine birleştirilir. Panel yalnız 4:2:0 JPEG çözer; model kenarlarında 2 piksele kadar ince renk saçakları kalabilir. Siyah filtreleme davranışı DWIN ile aynı değildir.

## Kaynakları tanıma

**Aşağıdaki ICO paketleme ve manuel yükleme komutları yalnız DWIN içindir.** DACAI aynı JPEG kaynaklarını ikon sayfalarına dönüştürür; zorla yeniden yüklemek için [DACAI SD sonrası adımlarını](dacai_TR.md#microsd-güncellemesinden-sonra) izleyin.

Uygulama artık kütüphane 2'yi [`assets/icons`](../assets/icons/README_TR.md) kaynaklarından oluşturur ve güncelleme sonrası ilk LCD bağlantısında değişen blokları otomatik yükler. Değişmeyen kaynaklar atlanır. JPEG ekleme, paketi dışa aktarma ve panel kaynakları yeniden kurulduktan sonra zorla yükleme için bu kılavuzu kullanın.

Normal kullanımda otomatik eşitleme yeterlidir. Geliştirici tanılaması için aşağıdaki komut güncel `assets/icons` JPEG kaynaklarından paketi yeniden oluşturup UART üzerinden yükler; referans ICO dosyasını okumaz:

```sh
sudo systemctl stop Petrel.service
if systemctl is-active --quiet Petrel-dwin.service; then
  export PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock
else
  unset PETREL_DWIN_SOCKET
fi
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py && sudo systemctl start Petrel.service
```

Araç yapılandırılmış seri portu kullanır ve 2’den başlayan slotlara yazar (her 32 KiB blok için bir slot). Yazma başarısız olursa servis kapalı kalır. Yazma onayları kontrol edilir; Flash geri okuması yapılmaz. Yüklemeden sonra ikonları fiziksel panelde kontrol edin.

Referans export dosyasının kendisini incelemek için servis kapalıyken açıkça `--file` verin. Aşağıdaki işlem, JPEG kaynaklarından yeniden paketlemek yerine belirtilen dosyanın baytlarını yükler; kaynaklar değiştiyse bu referans dosya farklı veya eski olabilir:

```sh
sudo systemctl stop Petrel.service
if systemctl is-active --quiet Petrel-dwin.service; then
  export PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock
else
  unset PETREL_DWIN_SOCKET
fi
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py --file ~/Petrel/assets/emulator/2.ICO && sudo systemctl start Petrel.service
```

Katkı görselleri için `tools/pack_icon_library.py kaynak.ICO hedef.ICO --library 2`, JPEG görsellerini koruyarak her ikonu tek bir 32 KiB blokta tutar. Böylece gözlenen çizim sorunlarıyla ilişkili blok sınırlarında ikonların bölünmesi önlenir.

[Stok envanteri](lcd-assets.json) proje için önceden incelenen kaynakları kaydeder. Kendi panelinizde kurulu dosyaları belirlemez. Katkı görselleri ve emülatör font seçimi talimatlarına [dokümantasyon dizininden](README_TR.md) ulaşabilirsiniz.

## LCD fontu

**DACAI:** Paneldeki `private/truefont` TrueType fontunu kullanır. Aşağıdaki DWIN HZK/font-SD işlemini uygulamayın. Petrel font yüklemez; görüntü farklılıkları için kendi modelinizin DACAI firmware paketine bakın.

**DWIN için:**

**İsteğe bağlı — Petrel stok DWIN LCD fontuyla çalışır.** Font değişimi, Petrel'in özellikleri veya performansı için gerekli değildir; yalnızca yazı görünümüne ilişkin bir tercihtir. Paketle sunulan ASCII fontu, fiziksel ekrandaki yazıları Petrel'in dokümantasyon ekran görüntülerine benzetebilir. Bunu tercih ederseniz `0T5UIC1.HZK` içeren yalnızca font amaçlı `assets/fonts/DWIN_SET` klasörünü uyumlu bir LCD güncelleme SD kartına kopyalayın. Yazıcıyı kapatın, kartı LCD'nin kart okuyucusuna takın ve enerjiyi verin. Kaynak güncellemesi tamamlanınca kapatın, kartı çıkarın ve normal başlatın. **Bu isteğe bağlı font değişimi için stok geri yükleme paketi olan `assets/stock-dwin/DWIN_SET` klasörünü kullanmayın.** Petrel açılış görselini ve ikon kütüphanesini UART üzerinden otomatik günceller; Pi servisi font Flash'ını kendiliğinden yazmaz. Emülatör paketle sunulan fontu kullandığından stok fontlu fiziksel ekrandaki yazılarla ekran görüntüleri farklı görünebilir. Fontun DejaVu lisansı `assets/emulator/Petrel-font-license.txt` içindedir.


## Ardışık yönetilen ID’ler

Güncel kütüphanede 0–185 ID’lerinde 186 ikon vardır; 186–255 boştur. DWIN'deki PETICO06 metadata sürümü, yeni açılış kareleri başlamadan önce PETICO05 dahil eski yerleşik dizinleri geçersiz sayar. DWIN çıktısı 12 blok kaplar; DACAI aynı ikon ID'lerini ayrı sayfalarda taşır. [Güncel ikon envanterine](../assets/icons/README_TR.md) bakın.

### Manuel bağlantı sahipliği

Bu komutları yazıcı boşta iken Petrel servis kullanıcısıyla çalıştırın. Yardımcı UART kuruluysa `Petrel-dwin.service` çalışır kalsın ve yukarıdaki gibi display socket açıkça seçilsin: SSH kabuğu UI servisinin drop-in ortamını devralmaz. Böylece fiziksel UART’ın tek sahibi korunur ve yardımcı UART/NFC istemcileri kopmaz. Broker yoksa socket değişkenini kaldırın ve yapılandırılmış fiziksel UART’ı doğrudan kullanın. Broker sahipken fiziksel UART’ı doğrudan açmayın. Yükleme kısayolu olarak broker’ı durdurmayın; yardımcı istemcilerin bağlantısını keser. Hata Petrel’i inceleme için kapalı bırakır; sorunu çözünce başlatın. `reload_icons.py --boot`, 0 ve 1 numaralı slotlarla kütüphane 2’yi açıkça onarır; `--boot` yoksa mevcut ikon/ortak sayfa davranışı korunur. Panel ayarları ve fontlar korunur.
