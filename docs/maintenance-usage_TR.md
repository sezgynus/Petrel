# Komponent kullanım takibi

[English](maintenance-usage.md) · [Maintenance](user-guide_TR.md#maintenance)

Maintenance, Klipper READY sırasında gerçek nesne envanterinden pasif kullanım tanımları üretir. Aynı kayıt sistemi mevcut WebSocket aboneliğini, toplayıcıyı ve keşif snapshot'ını besler. Çıkışı okumak için fiziksel test izni gerekmez. Kullanım ölçmek amacıyla çıkış sürülmez; menü açmak keşif çalıştırmaz. `printer_capabilities.py` bağımsız kalır.

## Desteklenen ölçümler

| Klipper nesnesi | Abone olunan alan | Kaydedilen anlam |
|---|---|---|
| `fan`, `fan_generic`, `heater_fan`, `controller_fan`, `temperature_fan` | `speed` | Bildirilen komut hızı sıfırın üzerindeyken geçen süre; doğrulanmış mil dönüşü değildir |
| `extruder`, numaralı extruder'lar, `heater_bed`, `heater_generic` | `power` | Bildirilen ısıtıcı PWM'i sıfırın üzerindeyken geçen süre; enerji veya sıcaklık üzerinde kalma süresi değildir |
| `output_pin`, `pwm_cycle_time`, `pwm_tool` | `value` | Bildirilen çıkış değeri sıfırın üzerindeyken geçen süre; özel cihaz adına bağlı değildir |
| `led`, `neopixel`, `dotstar`, `pca9533`, `pca9632` | `color_data` | Bildirilen RGBW kanallarından biri sıfırın üzerindeyken geçen süre; optik ölçüm değildir |

Her örnekte belgelenmiş alan doğrulanır. Eksik değer, sayı yerine boolean, sonlu olmayan/negatif sayı, geçersiz fan/ısıtıcı aralığı ve bozuk LED dizisi okunamayan veri sayılır. LED dizisi yapılandırılmış zincir uzunluğuyla eşleşmeli; her elemanda sıfır ile bir arasında dört kanal bulunmalıdır. Yalnız efekt/enable bayrağı aydınlanma kanıtı değildir. Servo hareketi, eksen mesafesi, sensör geçişi ve tetik sayısı bu ON süresi profillerinden çıkarılmaz. Bunlar ayrıca güvenilir metrik sözleşmesi ister; diğer keşfedilen cihazlarda takvim ve global örneklenmiş baskı hatırlatıcıları kullanılabilir.

Yalnız iki uçta da geçerli ON örneği bulunan, sıfırdan büyük ve en fazla iki saniyelik aralıklar sayılır. Epoch/yapılandırma değişimi ve bağlantı kesintisi sürekliliği keser. Örnekler arasındaki kısa etkinlikler kaçabilir. Sayaçlar kaydedilmiş alt sınırdır; kesin ömür, güç tüketimi, fiziksel hareket veya kalan kullanım ömrü değildir. Örnekleme boşluklarını iyileştirme ayrı görevdir.

## Hatırlatıcılar ve diagnostik

**Maintenance → Care schedule → Add reminder** üzerinden cihaz/iş seçilir; kullanım tanımı bulunan cihazda **Sampled powered hours** sunulur. Seçenek kabiliyeti gösterir; ilk örnek henüz gelmedi diye kaybolmaz. **Sampled printing hours** global yazıcı sayacıdır; komponentin kendi ON süresinden farklıdır.

Yeni hatırlatıcı ilk geçerli sayaç okumasında kalıcı başlangıç alır. Kaydetmek bakım yapılmış sayılmaz. **I completed this service**, toplam sayacı sıfırlamadan yeni bakım dönemi başlatır. Güncel okuma kaybolursa ilerleme duraklar; mevcut başlangıç değiştirilemez veya uydurma sıfır üretilemez. Care schedule ve hatırlatıcı ayrıntısı tutarlı biçimde kayıtlı ilerleme / Tracking starting / Tracking paused kullanır.

**Diagnostics → Usage and history → Sampled component usage**, eski ilk-16 sınırından sonraki sayaçlar dahil bütün saklanan komponent sayaçlarını mevcut rapor sayfalamasıyla gösterir. Nesne anahtarları depolama ve kanıtta ayrı kalır; yalnız sunumda anlaşılır ad kullanılır. Takip durumu ve boş sayaç yuvaları kapasite sorunlarını gösterir. S10 Moonraker kayıtlı baskı geçmişi ile S12 Petrel örneklenmiş kullanım ayrı kalır.

## Kaynak ve kalıcılık sınırları

- En fazla **64 aktif metrik tanımı**. Standart `fan`, `extruder`, `heater_bed` önceliklidir; ardından nesne adı sırası kullanılır. **96 UTF-8 baytı** aşan adlar dışlanır ve adedi bildirilir.
- **Zincir başına 64**, takip profilleri toplamında **256 LED elemanı**. Bu sınırlar ek durum kopyalama ve abonelik yükünü de sınırlar. Dışlanan desteklenebilir profiller S12'de **Tracking capacity excluded** olarak görünür.
- Kaldırılmış cihazlar dahil en fazla **128 kalıcı komponent sayacı**. Eski kayıtlar korunur; dolu kayıt yeni adı reddederek **Counter capacity reached** gösterir. Sıfır kullanım göstermez, eski bakım referansını silmez. Ömür boyu sayaçlar otomatik temizlenmez.
- Kullanım JSON'u **64 KiB** içinde sürüm 1 kalır. Mevcut `sampled_on_s`, `sampled_print_s`, `counter_id`, bakım tamamlanmaları ve takip başlangıçlarının kimlik/birimleri korunur. Yeni desteklenen cihaza geçmiş kullanım atanmaz. Tekrar yüklemek mevcut değerleri dönüştürmez/sıfırlamaz.
- Örnekleme dosya/ağ I/O'su yapmaz. Mevcut worker yaklaşık **beş dakikada bir**, açık worker okumalarında ve düzenli kapanışta yazar. Boş ve değişmemiş sayaç farkı yeniden yazılmaz. Atomik yazma başarısızsa bekleyen miktarlar yeniden denemek üzere RAM'e alınır. Ani güç kesintisinde henüz yazılmamış son bölüm kaybolabilir.
- Yeni alan abonelikleri bağlantı başlangıcında hazırlanır. Case-light görünümü ve termal kontrol abonelikleri kullanım alanlarını korur; görünümü kapatmak sayacı durdurmaz. Bağımsız thread, soket veya HTTP polling döngüsü eklenmez.

Özellik öncesi yazıcı koda dönmek ters migrasyon değildir: eski kodun sayaç sınırları daha küçüktür; okuma tavanı da 64 kayıttır. Böyle bir geri dönüş öncesinde eşleşen kullanım/değerlendirme dosyalarını koruyun; uyumluluğu zorlamak için yeni kaydı kırpmayın veya kimliğini yeniden üretmeyin. Nesne adı yapılandırılmış kaynağı tanımlar, donanım seri numarasını değil; aynı adla donanım değiştirmek yeni parça ömrünü otomatik algılamaz.

## CI doğrulaması ve maliyet raporu

Her imzalı branch HEAD'inde tam regresyon çalışır. Rastgele çıkış adları, geçersiz örnekler, boşluk/epoch, ortak abonelikler, eski kimlik/yazma kurtarma, bakım başlangıcı, 128 sayaç sayfalaması, LED yük sınırları ve kapasite bildirimi kapsanır. Mevcut kısmi çizim/framebuffer regresyonları aktiftir; ekran yerleşimi ve ikon kaynakları değişmemiştir. Fiziksel kabul ayrıdır.

`tools/benchmark_maintenance_usage.py`, yeni toplayıcıyı imzalı `a1c01ef13249e2b9b703cd3a97f7b27b8d24600c` tabanının `maintenance_records.py` dosyasıyla karşılaştırır. Workflow tam olarak bu kaynağı alır. Tipik kurulum, 64 fan ve 256 LED bütçesi senaryolarında izleme yükü eklenmemiş tick süreleri; ayrı tracing geçişlerinde tutulan/tepe Python bellek miktarı raporlanır. Tam kaynak durum JSON'u ve uzun adlarla dolu sayaç dosyası da boyutlandırılır. Mevcut keşif RSS/PSS/USS raporu metrik tanımı depolamasını içerir.

Bunlar sentetik CI runner ölçümleridir. Bir Hz CPU dönüşümü, toplayıcı çalışma süresinden hesaplanan tahmindir; Pi işlemci ölçümü değildir. Abonelik çözümleme/kopyalama, tüm uygulamanın belleği ve fiziksel LCD trafiği mikrobenchmark kapsamı dışındadır. Gerçek Pi CPU/RSS/PSS/USS kabulü, yetkilendirilmiş donanım karşılaştırmasına kadar ölçülmüş sayılmaz.
