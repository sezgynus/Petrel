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

**Diagnostics → Usage and history → Sampled component usage**, eski ilk-16 sınırından sonraki sayaçlar dahil bütün saklanan komponent sayaçlarını sürekli enkoder kaydırmasıyla gösterir. Nesne anahtarları depolama ve kanıtta ayrı kalır; yalnız sunumda anlaşılır ad kullanılır. Ekranda yalnız kullanım miktarları gösterilir; olay türleri, takip durumu ve sayaç kapasitesi ayrı LCD satırları olarak yazılmaz, ham kanıt verisinde korunur. S10 Moonraker kayıtlı baskı geçmişi ile S12 Petrel örneklenmiş kullanım ayrı kalır.

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

Extra mevcut [configure.sh akışında](installation_TR.md#isteğe-bağlı-eksen-mesafesi-sayaçları) etkinleştirilir; ilk yapılandırmada varsayılan **açık**, aynı yerden kaldırılabilir. Petrel'e ham hareket akışı gönderilmez. Extra, mevcut toolhead trapq kuyruğunu **0,1 saniyede bir** okur; geçen ivmelenme/sabit hız/yavaşlama bölümlerini hesaplayıp mutlak X/Y/Z mesafesini toplar. Konum ofsetleri ve koordinat sıfırlamaları hareket sayılmaz. Klipper'a hareket başına Python hook'u, yeni thread, hareket komutu veya disk yazması eklenmez. Sabit native okuma tamponu **128 kayıt (10.240 bayt)** ve yeniden kullanılır; tick başına tek çıkarma ve en fazla 128 kayıt değerlendirilir. Tampon doluysa sınırsız yetişme döngüsü yerine bütün aralık atlanır. İki saniyeyi aşan gecikmeler ve saat gerilemeleri de atlanıp sayılır. Endstop tetiklenmesiyle kuyruk kısaltma ayrı ele alınması gerektiğinden homing/probing hareketleri bilinçli dışlanır. Fiziksel adım kaybı veya enkoder ölçümü iddia edilmez. Kartezyen takım kafası mesafesi; CoreXY kayış/motor mesafesi, delta kule hareketi, bağımsız carriage hareketi, input-shaper salınımı veya manual-stepper mesafesi değildir.

**Care schedule → Add reminder → X/Y/Z axis → Recorded travel (metres)** seçilir. Mesafe mevcut eksen girdilerinde sunulur; ayrı X/Y/Z travel girdisi yalnız karşılık gelen eksen girdisi yoksa görünür. İkisi aynı Kartezyen sayacı kullanır. Önceden travel girdisinden kaydedilmiş hatırlatıcıların cihaz kimliği ve bakım başlangıcı korunur; numaralı motorlar ve manual stepper’lar XYZ mesafesi devralmaz. Düzenleyici tam metre (1–87.600), kayıt milimetre kullanır. Aralık kullanıcı tanımlıdır, önerilen parça ömrü değildir. Limit altındaki kayıtlı mesafe bakım gerekmediğini kanıtlamaz. Bakım tamamlanması yeni dönem başlatır; toplamları değiştirmez.

**Sampled component usage (S12)** yalnız kalıcı eksen toplamlarını gösterir; takip/duraklama durumu bakım kullanılabilirliği ve diagnostik için iç verilerde korunur. **Recorded axis travel (S13)** bu Klipper oturumunun ham sayaçlarını açıkça kayıtlı alt sınır etiketiyle gösterir. Petrel'in `maintenance-travel.json` dosyası toplamları, sayaç kimliğini ve en fazla sekiz oturum checkpoint'ini atomik saklar. Mevcut worker, beş dakikalık yazma, açık okumalar ve düzenli kapanış akışında kaydeder; değişmemiş toplam yeniden yazılmaz. Aynı oturumda Petrel bağlantısı/servisi yeniden başladığında mesafe tekrar eklenmez. Kaçırılan oturumlar, yazılmadan önce sekizden fazla restart, toplayıcı yoğunluğu, homing/probing ve ani kapanış mesafe kaybettirebilir. Sayaç extra READY ile başlar, yazıcının üretiminden itibaren saymaz. Kapatıldığında/okunamadığında takip duraklar; uydurma sıfır veya yeni bakım başlangıcı atanmaz. Çalışma zamanı keşfi yalnız kurulum tercihini değil, gerçekten yüklenmiş extra'yı gerektirir.

Tam CI paketi kurulum geri alma, temiz Git durumu, varsayılan açık/kapatılmış tercihi koruma, kaldırma, oturum sürekliliği, kısmi hareket hesabı, yoğunluk ve isteğe bağlı hata izolasyonunu denetler. `tools/benchmark_axis_travel.py`, **sabitlenmiş upstream Klipper trapq C uygulamasını** CI'da derler; ivmelenme/kısmi aralık/ters yön/koordinat sıfırlamasını doğrular; extra süresini API benzeri çıkarma/JSON/çözümleme hesabıyla karşılaştırır. Gerçek soketler ve tüm API katmanı bu ölçüme dahil değildir. Runner süreleri Raspberry Pi CPU yüzdesi veya `Timer too close` oluşmayacağının kanıtı değildir; düşük kaynaklı gerçek kartta zamanlama kabulü henüz yapılmamıştır. Extra Klipper'ın iç C/Python sözleşmelerine bağlıdır; Klipper geliştikçe yeniden doğrulanmalıdır. Desteklenmeyen çalışma zamanı toplaması yazıcı shutdown çağrısı yapmadan kendini kapatır; yükleme/config uyumsuzluğu ise extra'yı düzeltip/devre dışı bırakıp Klipper'ı yeniden başlatmayı gerektirebilir.

## Bakım sınıfları ve pasif cihaz envanteri

Bakım envanteri çalıştırılabilir test izninden bağımsızdır. Klipper READY sırasında config-only probe, servo ve sensörler dahil en fazla 256 yapılandırılmış/keşfedilmiş komponent adı tutulur. Fiziksel endstop’lar ayrı `endstop stepper_*` kimliği alır; sensorless/virtual endstop fiziksel anahtar olarak uydurulmaz. BLTouch/smart-effector config ve ortak `probe` durum nesnesi tek kez sunulur. Sınırlı envanter dolarsa cihaz seçimi dışlanan adedi bildirir; menü açılışında keşif veya yeni periyodik abonelik eklenmez.

| Komponent | Bakım sınıfı |
|---|---|
| Eksen / mekanizma / manual stepper | Mechanical maintenance — Mekanik bakım |
| Ekstrüder | Filament feed maintenance — Filament besleme; Nozzle maintenance — Nozzle; Heating system maintenance — Isıtma sistemi |
| Tabla / genel ısıtıcı | Heating system maintenance — Isıtma sistemi bakımı |
| Fan | Fan maintenance — Fan bakımı |
| LED / aydınlatma | Lighting maintenance — Aydınlatma bakımı |
| Genel dijital / PWM çıkışı | Connected device maintenance — Bağlı donanım bakımı |
| Servo | Actuator maintenance — Aktüatör bakımı |
| Probe / endstop / filament / sıcaklık / diğer tanınan sensör | Sensor maintenance — Sensör bakımı |
| MCU / sürücü | Electronics maintenance — Elektronik donanım bakımı |
| Diğer keşfedilmiş donanım | General hardware maintenance — Genel donanım bakımı |

Tek sınıf otomatik seçilir; eksen veya sensör seçimi doğrudan **Choose reminder basis** ekranına gider. Ekstrüderde üç ayrı bakım konusu bulunduğundan sınıf seçimi gösterilir. Sınıflar özel cihaz adına değil Klipper nesne türüne bağlıdır: `output_pin fan` yine bağlı donanım bakımıdır. Yapılandırılmış sensöre güncel okuma veya çalıştırılabilir test olmadan takvim hatırlatıcısı kurulabilir; global örneklenmiş baskı süresi ayrıca etiketlenir. Tetik sayısı veya sensör aktif süresi uydurulmaz. Hatırlatıcı tamamlama, kullanıcı bakımını kaydeder; sensör testini geçmiş sayılmaz.

Eski `inspect_clean`, `lubricate`, `nozzle_inspect` görev kimlikleri uygun yeni sınıf etiketleriyle gösterilir. Politikalar, bakım tarihleri, sayaç kimlikleri ve takip başlangıçları yeniden yazılmaz, birleştirilmez veya sıfırlanmaz. Aynı sınıf adıyla görünen iki eski politika ayrı hatırlatıcı kalır; gereksiz tekrar kullanıcı tarafından açıkça silinir.


## Olay tabanlı sensör sayaçları

**Usage history / Recorded component usage (S12)**, mevcut isteğe bağlı `petrel_axis_travel` Klipper extra’sından birikmiş sayaçları alır. LCD'de her kaynak sadece sayacıyla bir kez listelenir; homing/probing contacts veya switch activations gibi olay türleri için ayrı satır oluşturulmaz. Sensör durumları örneklenerek tetiklenme çıkarımı artık yapılmaz. Toplamı daha seyrek okumak, Klipper’ın yakaladığı olayları kaybettirmez.

| Kaynak | Sayılan olay |
|---|---|
| Filament switch sensörü / dijital veya ADC `gcode_button` | Mevcut callback’te pasif → aktif geçiş; mevcut debounce korunur |
| Filament motion sensörü | Mevcut enkoder girişi callback’inin yükselen kenarı; türetilmiş filament-present bayrağı değil |
| Fiziksel endstop / desteklenen temaslı probe | Gerçek stepper hareketiyle doğrulanmış pozitif homing tetiklenme sonucu |

Bu nedenle iki geçişli homing iki temas sayabilir; her gerçek probing teması ayrıdır. G28 komutu veya yalnız homing tamamlanma bildirimi sayılmaz. Timeout, bırakılmayı arayan hareket, değişmeyen stepper konumu ve tekrarlanan tamamlanma olayı artış üretmez. Boştayken elle basılan endstop homing yakalamasının dışındadır. Sensorless/virtual endstop ve temassız tarama fiziksel switch tetiklenmesi gibi sunulmaz. Desteklenmeyen callback/probe iç yapılarında sahte sayaç oluşturulmaz. Bilinmeyen başlangıç seviyesi yeni tetiklenme değil başlangıç durumudur; bilinen pasif seviyeden sonra sayım başlar.

**Care schedule → Add reminder → sensör → Recorded sensor events** seçilir. **Sensor maintenance** otomatik seçilir. Tam sayı olay aralığını girip gözden geçirin ve kaydedin. Kaydetmek bakım tamamlanma kaydı oluşturmadan takip başlangıcı belirler. Bakım tamamlanınca başlangıç ilerler, toplam korunur. Extra eski/eksik/kapalıysa veya kaynak kullanılamıyorsa takip duraklar. Sayaçlar donanımın bütün ömrünü değil etkin yakalama dönemini kapsar; eşik altı değer bakım gerekmediğini kanıtlamaz.

Extra, READY’de mevcut callback teslimine bir kez bağlanır; orijinal callback’in sonucunu ve hatalarını korur. Yeni sensör polling timer’ı, MCU sorgusu, pin kaydı, G-code, thread veya disk yazması eklemez. Mevcut mesafe toplayıcısı korunur. Sensör yakalama durumu ile mesafe toplayıcısının durumu bağımsızdır. En fazla 64 kaynak ve sınırlı geçici homing gözlemi tutulur. Durum nesnesi `sensor_schema`, `sensor_state`, `sensor_counts`, `sensor_kinds`, `sensor_disabled` ve `sensor_excluded` alanlarını sunar.

Petrel’in ayrı atomik `maintenance-sensor-events.json` kaydı; 32 KiB isim bütçesi ve mevcut 64 KiB dosya sınırı içinde en fazla 128 tarihsel cihazı, sekiz oturum checkpoint’ini saklar. Toplam ve checkpoint birlikte kaydedilir. Aynı oturumda yeniden bağlantı/Petrel restart toplamı tekrar eklemez; yeni Klipper oturumu kendi artışını ekler. Worker yazma hatasında bekleyen görüntüler tekrar denemek için korunur. Yazılmamış Klipper oturum sonları, sekizden fazla bekleyen oturum değişimi veya ani kapanma ölçüm kapsamı kaybettirebilir. Çalışan mevcut oturumda okuma sıklığı olay yakalamayı etkilemez.

Eski `maintenance-sensor-usage.json` örneklemeli toplamları, kimlikleri ve reminder başlangıçları değişmeden korunur ve dışa aktarılan diagnostik raporda bulunur. Güncel kullanım ekranında gösterilmez; takipleri duraklatılır. Bunlar yeni olay toplamlarına eklenmez; özellikle eski motion sensörü varlık sayısı enkoder kenar sayısı değildir. Yeni bakım dönemi için yeni olay dayanağını açıkça seçin. ON süresi/mesafe kayıtları ve kimlikleri korunur. S20 raporu eski örneklemeli sayılarla yeni olay toplamlarını ayırır.

Etkinleştirme/güncelleme mevcut **configure.sh** extra seçeneğiyle yapılır; seçenek artık hem eksen mesafesini hem sensör olaylarını kapsar. Mevcut `PETREL_AXIS_TRAVEL` ayarı, symlink ve include geriye uyumludur. Kurulu symlink güncel extra dosyasını alır; kodu yüklemek için **yazıcı boşta iken Klipper’ı yeniden başlatın**, ardından Petrel’i yeniden başlatın. Klipper restart edilmeden çalışan eski extra yeni alanları sunamaz. Ortak seçeneği kapatmak her iki özelliği duraklatır, kayıtlı geçmişleri korur.

## Sensör diagnostikleri

**Maintenance → Diagnostics → Sensors** yolunda yapılandırılmış sensörü seçip raporunu okuyun. Liste, çalıştırılabilir test izinlerinden bağımsız READY envanterini kullanır. Yalnız config’te bulunan cihazlar da görünür. Her raporda etkin yapılandırma, sunulan durum nesnesi, desteklenen okumalar ve kaynak erişilebilirliği ayrıdır. Filament algılama/etkinlik, buton durumu, son endstop/probe sorgusu, sıcaklık/minimum/maksimum ve desteklenen çevresel, çap veya load-cell alanları yalnız kaynak geçerli değer sağladığında gösterilir. Eksik veya geçersiz okuma sıfıra çevrilmez.

**Refresh reading**, mevcut worker üzerinden tek salt okunur nesne durumu isteği yapar. Yeni sürekli abonelik, sensör başına timer, G-code, hareket, probing veya config değişikliği yoktur. Endstop/probe için Refresh kayıtlı son sorgu sonucunu okur; yeni fiziksel sorgu başlatmaz. Diğer değerler okuma anındaki durum görüntüsüdür. Bağlantı/yapılandırma değişince eski yanıt reddedilir; işlem bitmeden çıkmak ekranı sonradan yönlendirmez. Raporlar mevcut kaydırılabilir Graphite düzenini ve kısmi çizim önbelleğini kullanır.

Güncel kullanım raporları okumaları ve mevcut takip durumunu gösterir. Göç geçmişi, ölçüm kapsamı açıklamaları ve enkoder gezinme talimatları LCD rapor alanını doldurmak yerine dokümantasyonda tutulur.
