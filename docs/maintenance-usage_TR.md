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

**Diagnostics → Usage and history → Sampled component usage**, eski ilk-16 sınırından sonraki sayaçlar dahil bütün saklanan komponent sayaçlarını sürekli enkoder kaydırmasıyla gösterir. Nesne anahtarları depolama ve kanıtta ayrı kalır; yalnız sunumda anlaşılır ad kullanılır. Takip durumu ve boş sayaç yuvaları kapasite sorunlarını gösterir. S10 Moonraker kayıtlı baskı geçmişi ile S12 Petrel örneklenmiş kullanım ayrı kalır.

## Kaynak ve kalıcılık sınırları

- En fazla **64 aktif metrik tanımı**. Standart `fan`, `extruder`, `heater_bed` önceliklidir; ardından nesne adı sırası kullanılır. **96 UTF-8 baytı** aşan adlar dışlanır ve adedi bildirilir.
- **Zincir başına 64**, takip profilleri toplamında **256 LED elemanı**. Bu sınırlar ek durum kopyalama ve abonelik yükünü de sınırlar. Dışlanan desteklenebilir profiller S12'de **Tracking capacity excluded** olarak görünür.
- Kaldırılmış cihazlar dahil en fazla **128 kalıcı komponent sayacı**. Eski kayıtlar korunur; dolu kayıt yeni adı reddederek **Counter capacity reached** gösterir. Sıfır kullanım göstermez, eski bakım referansını silmez. Ömür boyu sayaçlar otomatik temizlenmez.
- Kullanım JSON'u **64 KiB** içinde sürüm 1 kalır. Mevcut `sampled_on_s`, `sampled_print_s`, `counter_id`, bakım tamamlanmaları ve takip başlangıçlarının kimlik/birimleri korunur. Yeni desteklenen cihaza geçmiş kullanım atanmaz. Tekrar yüklemek mevcut değerleri dönüştürmez/sıfırlamaz.
- Örnekleme dosya/ağ I/O'su yapmaz. Mevcut worker yaklaşık **beş dakikada bir**, açık worker okumalarında ve düzenli kapanışta yazar. Boş ve değişmemiş sayaç farkı yeniden yazılmaz. Atomik yazma başarısızsa bekleyen miktarlar yeniden denemek üzere RAM'e alınır. Ani güç kesintisinde henüz yazılmamış son bölüm kaybolabilir.
- Yeni alan abonelikleri bağlantı başlangıcında hazırlanır. Case-light görünümü ve termal kontrol abonelikleri kullanım alanlarını korur; görünümü kapatmak sayacı durdurmaz. Bağımsız thread, soket veya HTTP polling döngüsü eklenmez.

Özellik öncesi yazıcı koda dönmek ters migrasyon değildir: eski kodun sayaç sınırları daha küçüktür; okuma tavanı da 64 kayıttır. Böyle bir geri dönüş öncesinde eşleşen kullanım/değerlendirme dosyalarını koruyun; uyumluluğu zorlamak için yeni kaydı kırpmayın veya kimliğini yeniden üretmeyin. Nesne adı yapılandırılmış kaynağı tanımlar, donanım seri numarasını değil; aynı adla donanım değiştirmek yeni parça ömrünü otomatik algılamaz.

## CI doğrulaması ve maliyet raporu

Her imzalı branch HEAD'inde tam regresyon çalışır. Rastgele çıkış adları, geçersiz örnekler, boşluk/epoch, ortak abonelikler, eski kimlik/yazma kurtarma, bakım başlangıcı, 128 sayaç kaydırması, LED yük sınırları ve kapasite bildirimi kapsanır. Mevcut kısmi çizim/framebuffer regresyonları aktiftir; ekran yerleşimi ve ikon kaynakları değişmemiştir. Fiziksel kabul ayrıdır.

`tools/benchmark_maintenance_usage.py`, yeni toplayıcıyı imzalı `a1c01ef13249e2b9b703cd3a97f7b27b8d24600c` tabanının `maintenance_records.py` dosyasıyla karşılaştırır. Workflow tam olarak bu kaynağı alır. Tipik kurulum, 64 fan ve 256 LED bütçesi senaryolarında izleme yükü eklenmemiş tick süreleri; ayrı tracing geçişlerinde tutulan/tepe Python bellek miktarı raporlanır. Tam kaynak durum JSON'u ve uzun adlarla dolu sayaç dosyası da boyutlandırılır. Mevcut keşif RSS/PSS/USS raporu metrik tanımı depolamasını içerir.

Bunlar sentetik CI runner ölçümleridir. Bir Hz CPU dönüşümü, toplayıcı çalışma süresinden hesaplanan tahmindir; Pi işlemci ölçümü değildir. Abonelik çözümleme/kopyalama, tüm uygulamanın belleği ve fiziksel LCD trafiği mikrobenchmark kapsamı dışındadır. Gerçek Pi CPU/RSS/PSS/USS kabulü, yetkilendirilmiş donanım karşılaştırmasına kadar ölçülmüş sayılmaz.

Kayıtlı hatırlatıcıyı kaldırmak için **Care schedule** içinde açın, **Remove reminder** seçin ve ayrı **Remove reminder?** ekranında onaylayın. İlk seçili eylem **Keep reminder** olur. Silme mevcut worker üzerinde çalışır ve yenilenmiş takvime döner. Kayıtlı politika ve ona ait aktif takip başlangıcı kaldırılarak iki kayıt alanı da serbest bırakılır; kullanım sayaçları ve tamamlanan bakım geçmişi korunur. Onay ekranı açıldıktan sonra düzenlenen hatırlatıcı eski onayla silinemez.

## İsteğe bağlı Kartezyen eksen mesafesi

Extra mevcut [configure.sh akışında](installation_TR.md#isteğe-bağlı-eksen-mesafesi-sayaçları) etkinleştirilir; ilk yapılandırmada varsayılan **açık**, aynı yerden kaldırılabilir. Petrel'e ham hareket akışı gönderilmez. Extra, mevcut toolhead trapq kuyruğunu **0,5 saniyede bir** okur; geçen ivmelenme/sabit hız/yavaşlama bölümlerini hesaplayıp mutlak X/Y/Z mesafesini toplar. Konum ofsetleri ve koordinat sıfırlamaları hareket sayılmaz. Klipper'a hareket başına Python hook'u, yeni thread, hareket komutu veya disk yazması eklenmez. Sabit native okuma tamponu **128 kayıt (10.240 bayt)** ve yeniden kullanılır; tick başına tek çıkarma ve en fazla 128 kayıt değerlendirilir. Tampon doluysa sınırsız yetişme döngüsü yerine bütün aralık atlanır. İki saniyeyi aşan gecikmeler ve saat gerilemeleri de atlanıp sayılır. Endstop tetiklenmesiyle kuyruk kısaltma ayrı ele alınması gerektiğinden homing/probing hareketleri bilinçli dışlanır. Fiziksel adım kaybı veya enkoder ölçümü iddia edilmez. Kartezyen takım kafası mesafesi; CoreXY kayış/motor mesafesi, delta kule hareketi, bağımsız carriage hareketi, input-shaper salınımı veya manual-stepper mesafesi değildir.

**Care schedule → Add reminder → X/Y/Z travel → Lubricate mechanism → Recorded travel (metres)** seçilir. Düzenleyici tam metre (1–87.600), kayıt milimetre kullanır. Aralık kullanıcı tanımlıdır, önerilen parça ömrü değildir. Limit altındaki kayıtlı mesafe bakım gerekmediğini kanıtlamaz. Bakım tamamlanması yeni dönem başlatır; toplamları değiştirmez.

**Sampled component usage (S12)** kalıcı eksen toplamlarını ve takip/duraklama durumunu içerir. **Recorded axis travel (S13)** bu Klipper oturumunun ham sayaçlarını açıkça kayıtlı alt sınır etiketiyle gösterir. Petrel'in `maintenance-travel.json` dosyası toplamları, sayaç kimliğini ve en fazla sekiz oturum checkpoint'ini atomik saklar. Mevcut worker, beş dakikalık yazma, açık okumalar ve düzenli kapanış akışında kaydeder; değişmemiş toplam yeniden yazılmaz. Aynı oturumda Petrel bağlantısı/servisi yeniden başladığında mesafe tekrar eklenmez. Kaçırılan oturumlar, yazılmadan önce sekizden fazla restart, toplayıcı yoğunluğu, homing/probing ve ani kapanış mesafe kaybettirebilir. Sayaç extra READY ile başlar, yazıcının üretiminden itibaren saymaz. Kapatıldığında/okunamadığında takip duraklar; uydurma sıfır veya yeni bakım başlangıcı atanmaz. Çalışma zamanı keşfi yalnız kurulum tercihini değil, gerçekten yüklenmiş extra'yı gerektirir.

Tam CI paketi kurulum geri alma, temiz Git durumu, varsayılan açık/kapatılmış tercihi koruma, kaldırma, oturum sürekliliği, kısmi hareket hesabı, yoğunluk ve isteğe bağlı hata izolasyonunu denetler. `tools/benchmark_axis_travel.py`, **sabitlenmiş upstream Klipper trapq C uygulamasını** CI'da derler; ivmelenme/kısmi aralık/ters yön/koordinat sıfırlamasını doğrular; extra süresini API benzeri çıkarma/JSON/çözümleme hesabıyla karşılaştırır. Gerçek soketler ve tüm API katmanı bu ölçüme dahil değildir. Runner süreleri Raspberry Pi CPU yüzdesi veya `Timer too close` oluşmayacağının kanıtı değildir; düşük kaynaklı gerçek kartta zamanlama kabulü henüz yapılmamıştır. Extra Klipper'ın iç C/Python sözleşmelerine bağlıdır; Klipper geliştikçe yeniden doğrulanmalıdır. Desteklenmeyen çalışma zamanı toplaması yazıcı shutdown çağrısı yapmadan kendini kapatır; yükleme/config uyumsuzluğu ise extra'yı düzeltip/devre dışı bırakıp Klipper'ı yeniden başlatmayı gerektirebilir.
