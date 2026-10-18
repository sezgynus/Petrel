# Maintenance fiziksel kabulü

[English](maintenance-stage8-acceptance.md) · [Türkçe](maintenance-stage8-acceptance_TR.md) · [Profiller](maintenance-profiles_TR.md) · [LCD rehberi](user-guide_TR.md#maintenance) · [Kabul çizelgesi](maintenance-reference-printer-acceptance_TR.md)

## Kapsam ve ön şartlar

Maintenance master ile entegredir. CI yazılım sözleşmelerini doğrular; gerçek hareketi, sesi, ışığı, ısıtmayı veya geri yüklemeyi değil. Kabul, çizelgede kaydedilen özellik/cihaz/sürüm içindir; bu prosedür değişti diye kabul edilmiş kayıtları sıfırlamayın.

İmzalı, CI başarılı sürüm kullanın ve çalışan servisin checkout'unu doğrulayın. Yalnız boşta güncelleyin/yeniden başlatın: baskı/pause, kuyrukta iş, MMU/prob/kalibrasyon veya çözülmemiş jog geri alma bulunmamalıdır. Fiziksel yolu açıp ilgili grubun koşullarını inceleyin. Fiziksel çalıştırmada operatör başında olmalıdır. İsteğe bağlı görsel/ses/genel fan/bağımsız LED çıkışları sürüm-2 rol beyanı ister; tanınan Happy Hare LED'leri doğrulanmış denetleyici eşlemesini kullanır. Parça fanı adayları ek profil istemez.

## Cihaz üstünde manuel sıra

1. **Maintenance → Check printer** altında işlev grubunu ve tam cihazı seçip **Prepare check** açın. Hazırlık durum okur, donanım çalıştırmaz.
2. Hazırlığı ve ayrı onayı okuyun. **Start check** veya sunulduğunda **Home axes and continue** seçin. Controller'a özel eylemler **Run short pulse**, **Run speed steps**, **Run color sequence** veya **Run PID** olabilir. **Kullanıcı yanıtı zaman aşımına uğramaz.** Eski güvenlik kanıtı yeni kontrol ister; insan yanıtına süre dayatmaz.
3. İstenen fiziksel davranışı gözleyip seçili akışı izleyin. F02 üç adet 2 saniyelik kademe; O04 kırmızı → mavi → yeşil → beyaz; F12 fiziksel tam duruş onayı içerir. Termal H01 tek ısıtıcı koşusunda yedi alt metrik üretir; yedi ayrı menü denemesi değildir.
4. Geri yükleme kanıtını ve sonucu inceleyin. Yalnız açık gözlem ve desteklenen geri okuma `PASSED_USER` üretebilir. S18 ve Happy Hare O04 `OBSERVED_USER`, `restore_verified=False` kullanır; elektronik geri yükleme uydurmayın. Ölçüt başarısızlığı ile prosedürün çalışmaması farklıdır.
5. **Details**, sayfalar ve önerileri inceleyin. **Back to checks** önceki cihaza döner. Aktif iptal grubun açıkladığı güvenlik yolunu izler; ısıtma/belirsiz hareket Klipper shutdown isteyebilir. Belirsiz komutu körlemesine tekrarlamayın.
6. Bağımsız bilgi **Maintenance → Diagnostics** altındadır. Okumalar rapordur; donanım PASS değildir. Destek kaydı/dışa aktarım **Diagnostics → Support tools** altındadır.

## Kayıt ve geri dönüş

İmzalı SHA, tam hedef/yöntem, kullanıcı yanıtı, controller sonucu ve geri yükleme kanıtını kaydedin. Kanonik JSON ve iki kabul çizelgesini yalnız açık kullanıcı onayından sonra güncelleyin. CI fiziksel kabul vermez. Geçici aday checkout kullanıldıysa özgün systemd ayarını geri getirip boşta daemon-reload ve servis restart yapın; hangi checkout'un çalıştığını varsaymak yerine gerçek WorkingDirectory/ExecStart'ı doğrulayın.

## Tarihsel Aşama 8 saha bulguları

Aşağıdaki tarihli hatalar eski sürümleri açıklar; güncel kabul çizelgededir. Geçici branch yolları, eski profil anahtarları ve bekleme durumları kurulum talimatı değildir. Özellikle eski `buzzer_output` yerine sürüm-2 aktüatör rolleri geçmiştir; referans yazıcının sonraki F01/S18/O04/F02 kabulleri korunur.

## F01 saha bulgusu ve sonraki doğrulama

2026-10-16 tarihli Remote Display kabulünde F01 parça soğutma fanı kamerada kısa süre çalışırken yürütücü `INCONCLUSIVE / restore_not_verified` döndürdü. Sonradan bağımsız `/printer/objects/query?fan&webhooks` sorgusu `fan.speed=0.0`, `fan.rpm=null`, `webhooks.state=ready` gösterdi. İlk fiziksel deneme **PASS değildir**; anlık geri yükleme doğrulaması başarısız oldu, sonraki okuma da geçmişteki geri yükleme zamanlamasını kanıtlamaz. Yeni doğrulama penceresi/tekrar okuma yamasının CI sahte testleri vardır; feature worktree güncellendikten sonra **yeni** gerçek Pi kabul testi gereklidir. Tekrar fiziksel testten önce yazıcının boşta ve fanın durmuş olduğunu doğrula.

## S18: saha bulgusu ve bekleyen geri okuma kabulü

Pi'de `configfile.settings['pwm_cycle_time buzzer']` için pin PB13, value=0, shutdown_value=0, scale=1 doğrulandı; ancak `printer.objects.list` nesneyi içermiyor ve `printer.objects.query` durum sunmuyor. Güncellenen S18 izinli akışı yalnız yapılandırmadan keşif ve **insanın ses gözlemi** üzerine kuruludur; `OBSERVED_USER` sonucu doğrulanmış geri yükleme anlamına gelmez. Bu Klipper nesnesinde S18'in telemetriyle geri yükleme kabulü **mümkün değildir**. `buzzer_output='buzzer'` izni, fiziksel buzzer'ın doğru ve yazıcı boşta iken güvenli uyarılabilir olduğundan emin olunduktan sonra kullanılmalıdır. CI sahte testini gerçek donanım kabulü sayma.

## S18 büyük/küçük harfe duyarlı G-code saha bulgusu

2026-10-16 tarihinde S18 listede görünmeye başladı, ancak ilk fiziksel deneme `INCONCLUSIVE / script_failed_or_restore_unknown` ile sonuçlandı: Klipper'ın geçerli mux seçeneği `Buzzer` iken Petrel `PIN=buzzer` üretti. Çıkışın gerçekten uyarıldığı **doğrulanmadı**. İmzalı düzeltme salt-okunur ön kontrolde özgün, büyük/küçük harfe duyarlı bölüm adını çözümler. Yeni ve boşta yazıcı üzerinde kısa sesin **çıkıp ardından kesildiğini** gösteren fiziksel test `OBSERVED_USER` olarak kaydedilene kadar Aşama 8 S18 **BEKLEMEDE** kalır; durum geri okuma doğrulaması iddia edilmez.
