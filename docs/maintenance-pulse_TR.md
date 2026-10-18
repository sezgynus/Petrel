# Maintenance Aşama 8B — süre sınırlı aktüatör komutlarının oluşturulması

[English](maintenance-pulse.md)

Bu **saf derleyicidir**: değişmez `PulseProgram` kayıtları üretir, kendisi komut göndermez. Açık onay, canlı güvenlik, gönderim ve gözlem ayrı fiziksel controller'a aittir. Süre özelliğe bağlıdır: F01/F04 kısa fan darbesi, O03 görsel çıkış ve S18 ses kısa programlardır; F02 üç adet 2.000 ms kademe, O04 dört adet 650 ms renk aşaması içerir. F12 bağımsız sınırlı duruştan-kalkış denemeleri olarak gönderilir; bütün testler için 950 ms sınırı yoktur.

Yalnız tam kayıtlı USER hedefleri uygundur. F01/F02/F12 parça fanını kullanır; F04 izinli `fan_generic`; O03 açık visual rolü, canlı başlangıç değeri ve ham config pin kimliği; S18 izinli varsayılan-OFF audible çıkış ister. Bağımsız O04, piksel başına tam geri yüklemeyle 1–32 aynı tip RGB/RGBW pikseli destekler; tanınan Happy Hare segmentleri kendi LED denetleyicisini kullanır. Bilinmeyen başlangıç/sahiplik reddedilir. Komutlanan PWM ölçülmüş RPM değildir.

Yürütücü boşta/kuyruk/işlem durumunu yeniden denetler, her gönderimi korur ve telemetri varsa geri yüklemeyi doğrular. S18 ve Happy Hare O04 elektronik geri yükleme doğrulaması değil kullanıcı gözlemi anlamını korur. Aşağıdaki bölümler gerçek protokollerdir; önceki kısa/loş/tek-piksel sürümlerinin yerini almıştır. CI fiziksel çıkışı kanıtlamaz.

## S18 geri okuma sınırı

Açık izinle etkinleştirilen `pwm_cycle_time` buzzer için Klipper durum geri bildirimi yoktur. Sınırlı script önce KAPALI komutu gönderir, 50 ms bekler, 150 ms ses üretir ve yeniden KAPALI komutu gönderir. Toplam 200 ms'lik program geri yüklemeyi **dener**, ancak fiziksel gerçekleştiğini kanıtlamaz; `restored()` fonksiyonu uydurma durum değeri verilse bile S18'i telemetriyle doğrulanmış saymaz. Yalnız kullanıcı izni verilmiş, efektif yapılandırmada varsayılanı KAPALI olan tam çıkış kabul edilir.

S18/O03 SET_PIN derleyicileri Klipper'ın ham yapılandırmasından ayrı olarak doğrulanan, özgün harf biçimini koruyan `pin_command_name` ister. Eksik veya harflerden bağımsız olarak farklı adları reddeder ve bütün `SET_PIN PIN=` komutlarında yalnız bu doğrulanmış yazılışı kullanır.

## O04 LED zincirleri: otomatik yetenek keşfi, güvenli test

O04 donanımdan bağımsızdır. Klipper'ın başka bir denetleyici tarafından yönetilmeyen `led`, `neopixel`, `dotstar` ve `pca9632` zincirlerinde 1–32 aynı tip RGB/RGBW piksel, açık `led` rolü izni, kullanıcı onayı, indeksli renk uyarımı ve piksel başına önceki renklerin iki geri okumayla kontrolü korunur. Yazılımsal durum fiziksel ışık çıkışının kanıtı değildir; `PASSED_USER` için olumlu kullanıcı gözlemi her zaman zorunludur.

Happy Hare için Petrel, **sabit MMU adı, pin veya gate sayısı kullanmadan** efektif `[mmu_leds <unit>]` ayarlarını ve gerçek Klipper nesnelerini inceler. Fiziksel zincir `exit_leds`, `entry_leds`, `status_leds`, `logo_leds` segmentlerine bölünebilir; ayrı indeks aralıkları ve farklı MMU birimleri desteklenir. Her segmentin fiziksel indeksleri kesin, çakışmasız ve sınırlandırılmış olmalıdır. Güvenilir Happy Hare LED zincirleri, yazıcıya özel LED profili gerekmeksizin otomatik olarak **kullanıcı onaylı test adayı** olarak keşfedilir. Keşif asla komut göndermez veya otomatik PASS üretmez.

İlgili her birime Happy Hare'nin kendi `MMU_SET_LED` denetleyicisiyle tam parlaklıkta kırmızı → mavi → yeşil → beyaz aşamaları gönderilir; her aşama `DURATION=0.40 FADETIME=0`, ardından `G4 P650` ve `M400` kullanır. Tek komut birkaç doğrulanmış segmenti kapsayabilir; farklı birimler ayrı adreslenir. Happy Hare zincirine ham `SET_LED` gönderilmez, yöneticisi kapatılmaz. Komut sonrasındaki iki okuma başlangıçtaki `enabled` ve `animation` politikasını kontrol eder. Bu, animasyonlu RGB'nin birebir dönüşünü doğrulamaz; olumlu gözlem `OBSERVED_USER`, `restore_verified=False` verir. Zamanlama açıklaması aşağıdadır.

Bütün fiziksel testlerde çift açık onay, güncel yazıcı/kuyruk/işlem güvenlik denetimleri ve sınırlı komutlar korunur. Devre dışı LED denetimi, meşgul MMU, eksik/çelişkili durum kanıtı, yinelenen veya sınır dışı LED indeksleri, bir segmentte birden fazla fiziksel zincir, desteklenmeyen isimler ve aynı fiziksel zincire bağımsız efekt sahipliği ön kontrolde reddedilir. Fiziksel zincirin yalnız bir bölümü eşlenmişse ancak **değiştirilecek her pikselin sahibi kesin olarak belirlenmişse** o bölüm test edilir; diğer piksellere bilerek müdahale edilmez. Bilinmeyen eklentilerin LED kontrolü tahmin edilmez. CI taklit testi, fiziksel kabul değildir.

### Happy Hare sayısal UNIT uyumluluğu

[mmu_leds NAME] bölümündeki ek, G-code UNIT indeksi olmak zorunda değil; birim ADIDIR. Bazı Happy Hare sürümleri yalnızca sayısal UNIT argümanı kabul eder. Petrel sayısal indeksi, Happy Hare'nin birimleri oluştururken kullandığı yetkili [mmu_machine] units sıralamasından çözer. Birim adındaki rakamdan indeks çıkarmaz ve ilk birimin adını unit0 varsaymaz. Eksik, yinelenmiş veya tutarsız eşleme G-code gönderilmeden testi engeller. Böylece gerçek sistemlerde görülen "unable to parse unit0" hatası giderilir.

### Happy Hare birim kimliği ile görünen adın ayrılması

Yüklü Happy Hare `mmu_machine` nesnesi, etkin `configfile.settings.mmu_machine.units` alanı bulunmasa da `num_units` ve ardışık `unit_N` kayıtlarını verebilir. Bazı sürümlerde canlı `unit_N.name`, `[mmu_leds NAME]` bölümündeki gerçek birim kimliği değil, **kullanıcıya gösterilen etikettir**. Bu iki adın eşleşmesi gerekmez. Petrel görünen adı G-code içine yazmaz; bölüm adında geçen rakamdan da indeks tahmin etmez.

Sayısal `UNIT` indeksi iki sınırlı ve salt okunur kanıttan biriyle çözülür: (a) etkin `[mmu_machine] units` listesinin doğrulanmış sırası, mevcutsa canlı birim sayısı ve karşılaştırılabilir gerçek kimliklerle tutarlı olmalıdır; veya (b) **tam olarak tek bir** canlı MMU birimi, seçili zinciri yöneten **tam olarak tek bir** yapılandırılmış MMU LED denetleyicisi ve geçerli `unit_0` kaydı bulunmalıdır. İkinci durumda kullanıcıya görünen addan bağımsız olarak `UNIT=0` kesinleşir; yazıcıya özel istisna eklenmez. Birden fazla MMU birimi bulunup gerçek sıralama doğrulanamıyorsa görünen adlar yeterli sayılmaz ve O04 engellenir.

Keşif abone olunmuş canlı durumla, fiziksel ön kontrol ise yeniden sorgulanan güncel durumla aynı kanıtı doğrular. Yazıcı/kuyruk güvenlik denetimi, geçici Happy Hare efekti ve zorunlu kullanıcı gözlemi korunur. Belirsiz veya çelişen birim/denetleyici sayısında G-code gönderilmez.

### O04 dört renkli tam parlaklık görsel testi

RGB destekli LED zincirlerinde **kırmızı → mavi → yeşil → beyaz** sıralaması kullanılır; **eşlenmiş bütün LED'ler birlikte**, kanal başına tam seviye (1,0) ile değiştirilir. Her aşama 650 ms sürer. RGB zincirinde beyaz `R=G=B=1`; bağımsız RGBW zincirinde özel beyaz kanalı denemek için `W=1, R=G=B=0` kullanılır. Bağımsız indeksli zincirlerde tam kare bir defada aktarılır; sonunda **her LED'in başlangıçta yakalanan özgün rengi** geri yüklenir. `PASSED_USER` için Klipper'dan iki kararlı durum geri okuması ve kullanıcının açık olumlu gözlemi gerekir.

Happy Hare segmentleri dört adet `MMU_SET_LED ... (R,G,B) DURATION=0.40 FADETIME=0` aşamasıyla çalıştırılır; her aşamadan sonra **`G4 P650` ve `M400`** vardır. Klipper `G4` ile hareket zamanını ilerletir, fakat gerçek 650 ms dolmadan sonraki G-code'a geçebilir. `M400` beklemeyi tamamlatır ve sonraki renkten önce Happy Hare reactor zamanlayıcısına çalışma fırsatı verir. Aksi hâlde Happy Hare'nin ertelenen efektleri ara renkleri (örneğin maviyi) ezebilir. Yeni bir zamanlayıcı iş parçacığı veya ikinci fiziksel gönderim kullanılmaz. İki aşama arasında yaklaşık 250 ms normal Happy Hare renkleri görünebilir. Happy Hare kendi zamanlayıcısıyla **kontrol politikasına** geri döner; birebir RGB geri yüklemesi okunamadığından olumlu kullanıcı gözlemi `OBSERVED_USER`, `restore_verified=False` üretir. Kullanıcı yalnız herhangi bir değişimi değil dört rengi de görmüş olmalıdır.

Kırmızı/yeşil/mavi fiziksel kanalları tanımlı olmayan tek renkli `[led]` nesneleri RGB O04 testinden komut gönderilmeden çıkarılır. Tam beyazın kısa süreli de olsa loş uyarıma göre daha fazla akım çekebileceği unutulmamalıdır; güç kapasitesi tahmin edilmez, parlaklık sessizce azaltılmaz. CI yalnız komutları doğrular; gerçek renk veya elektriksel çalışmayı değil.

### Efektif Klipper color_order uyumluluğu

Klipper neopixel yapılandırmasında config.getlist('color_order'), Moonraker'ın configfile.settings alanında JSON listesi olarak sunduğu bir tuple döndürebilir. O04, hem liste biçimini (tüm pikseller için tek ortak RGB/RGBW sıralaması veya her piksel için ayrı sıralama), hem de virgülle ayrılmış metni doğrular. Bozuk veriler, karışık RGB/RGBW pikseller, eksik RGB kanalları ve geçersiz zincir boyutları G-code öncesinde engellenir. Bağımsız ve Happy Hare denetimindeki zincirler aynı doğrulamayı paylaşır. Engellenen fiziksel ön kontrol BLOCKED kalır; güvenli derleyici hata kodu Petrel günlüğüne "Maintenance physical preflight blocked" olarak yazılır, Moonraker'ın serbest içerikli yanıtları açığa çıkarılmaz.

### F02 parça soğutma fanı hız kademesi testi

READY keşfinde F02 doğrulandığında ve etkin fan yapılandırmasında sonlu, kullanılabilir bir PWM aralığı bulunduğunda Petrel, açık kullanıcı gözlemine (**USER**) dayanan üç kademeli fan testi sunar. `off_below` / `max_power` yapılandırma aralığının %40, %70 ve %100 noktalarından birbirinden farklı üç komut hesaplar; her kademede 2.000 ms bekler (toplam 6.000 ms) ve **aynı sınırlı komut dizisinin sonunda** güncel, test öncesi `fan.speed` değerine dönüş komutunu ekler. Fiziksel yürütücü mevcut iş kuyruğu/idle güvenliğini, açık onayı, komut sonrası geri yükleme değerinin tekrar okunmasını ve kullanıcının gerçekten hız değişimini görmesini gerektirir. Komutun kabul edilmesi veya PWM set değeri, takometresiz RPM ölçümü sayılmaz. Geçersiz sınır, bilinmeyen başlangıç durumu veya eski Klipper bağlamında komut gönderilmez. Referans çizelgesi yenilenmiş 2.000-ms/kademe sürümünün kullanıcı kabulünü kaydeder; önceki 800-ms kabulü ve belirsiz denemeler tarihseldir. Son elektronik geri yükleme ayrıca bildirilmemiştir; kabul bunu uydurmaz.


F02 onay ekranı `Run speed steps`, dört renkli O04 ise `Run color sequence` gösterir. Diğer kısa darbeler `Run short pulse` metnini korur. Kabul hedef/sürüm bazlıdır; güncel referans çizelgesini kullanın.


**Uzun F02 ve HTTP zamanlaması:** 6 saniyelik `G4` dizisi, MoonrakerClient'ın normal 5 saniyelik HTTP zaman aşımını aşabilir; fan kademeleri fiziksel olarak çalışsa bile `INCONCLUSIVE` oluşabilir. Yalnız F02 için sınırlandırılmış 10 saniyelik POST zaman aşımı kullanılır (taşıma katmanı 15 saniyenin üstünü reddeder). Böylece komut tamamlanma yanıtı ve sonrasında fan başlangıç değerinin **iki ayrı** okumayla doğrulanması mümkün olur. Diğer işlemler eski zaman aşımını korur; belirsiz hatada komut tekrar gönderilmez ve otomatik PASS üretilmez. 2 sn/kademelik ilk Pi denemesi kullanıcı onay ekranından önce INCONCLUSIVE verdiği için yeni sürümün kabulü değildir.

### Happy Hare O04 canlı bayrak uyumluluğu

Happy Hare, `[mmu_leds <unit>]` Klipper durumunda `enabled` ve `animation` değerlerini gerçek boolean yerine **tam olarak** `'True'` / `'False'` metinleriyle döndürebilir. Petrel O04 ön kontrolünde **ve** komut sonrası iki geri okumada yalnız bu iki kesin metni veya yerel boolean değerlerini kabul eder. `enabled=True` zorunludur; `animation` geçerli `True` ya da `False` olabilir, ancak son okumalar test öncesi durumla eşleşmelidir. Sayısal, eksik, biçimi bozuk metinler ve devre dışı LED kontrolcüsü güvenlik gereği engellenir. Bu değişiklik Happy Hare'yi devre dışı bırakmaz, doğrudan LED komutu veya tahminî ünite kimliği kullanmaz, renklerin fiziksel olarak geri yüklendiği iddiasında bulunmaz. Eski uyumluluk hataları tarihsel olarak korunur; güncel çizelgede sonraki dört-renk kullanıcı kabulü kayıtlıdır.


**O04 mavi renk kabulü:** 16 Ekim 2026'da tip uyumluluğu düzeldikten sonra LED testi çalıştı; kullanıcı yalnız kırmızı → yeşil → beyaz gördü, mavi gözlenmedi. Bu eksik fiziksel gözlem yeni sürüm için PASS değildir. `G4` / `M400` senkronizasyon düzeltmesi sonraki kullanıcı gözlemiyle referans çizelgesinde kabul edilmiştir; eksik eski gözlem tarihsel kalır. Sadece yönetilen Happy Hare O04 için sınırlı HTTP timeout kullanılır; diğer testlerin bekleme ayarı değişmez.
