# Sınırlı salt-okunur Maintenance yürütücüsü (geliştirme)

[English](maintenance-read-executor.md) · [Güvenlik](maintenance-safety_TR.md)

**Durum:** İstek üzerine çalışan bilgi yürütücüsü Diagnostics ile entegredir. Motor/ısıtıcı/fan sürmez veya donanım PASS üretmez. M07 korumalı register-sorgu G-code yolunu; diğer okuyucular sınırlı GET veya açıkça kayıtlı yerel kayıt/panel sağlayıcılarını kullanır.

`maintenance_executor.read_only_adapters()` host/sistem, termal, hareket/sürücü, filament ve ortam alan kayıtlarını birleştirir. Rastgele cihaz adından kayıt türetilmez. Yeni thread, bağlantı veya abonelik olmadan mevcut istemci ve worker kullanılır. Her okuma olumlu boşta/oturum kontrolleri ister; gönderim ve sonuç alımı değişen baskı/bağlantı/config durumunu reddeder. Yerel okuyucular kayıtlı geçmiş, örneklenmiş kullanım ve panel/enkoder sayaçlarını kapsar. Açık rapor dışa aktarımı ayrı sınırlı depolama işlemidir; donanım eylemi değildir.

`start(row)`, açıkça tanımlı INFORMATION planını, güvenilir sabit adaptörü, sınırlı timeout'u ve güncel pozitif güvenlik bağlamını doğrulayıp kabul durumunu döndürür. `poll()` engellemez; sonuç hazır değilken `None` döndürür. `cancel()` oturumu geçersizleştirip eski yanıtı atar; `close()` Petrel'e ait istemci/worker'ı kapatmaz. Ham API sözlükleri veya gizli anahtarlar saklanmadan, yanıtın yalnız seçilmiş sayısal/durum alanları küçük kanıt tuple'ına çevrilir.

Başarılı bilgi okumasında `ReadResult.status=None` kullanılır: **telemetri gözlendi, fiziksel test PASS değildir**. Eksik ölçüm `INCONCLUSIVE`, iptal/güvensiz durum `ABORTED`, okuma hatası/zaman aşımı `ERROR` olur. Bunlar tamamlanmış fiziksel test olarak kalıcı depolanmaz.

**Güncel entegrasyon:** `MaintenanceReadController` canlı kuyruk/işlem kanıtını sağlar ve yürütücüyü yönetir; LCD adlandırılmış raporlar ve tam sayfalı ölçümler sunar. Çağıran taraf olumlu güvenlik bayrağı uydurmamalıdır. İlk yalnız-GET aşaması tarihseldir; aşağıdaki doğrudan M07 yolu uygulanmıştır.

`tests/test_maintenance_executor.py`, geçerli/eksik/geçersiz yanıtları, yöntem seçimini, iptali, sıradaki okumayı, dış baskı başlangıcını, epoch değişimini ve paylaşılan worker sahipliğini GitHub Actions CI'da kapsar.

## Güncel M07 uygulaması: homing bağımsız doğrudan register tanılaması

Güncel M07 Diagnostics, desteklenen TMC çiplerinde yalnız kullanıcının talebi üzerine
`DUMP_TMC STEPPER=<verified name> REGISTER=DRV_STATUS` çalıştırır.
Klipper'ın `notify_gcode_response` çıktısı mevcut Moonraker bağlantısında
komut tamamlanması ve yeni yanıt imleciyle değerlendirilir. Önceki konsol
satırları, belirsiz/çift cevap, iletişim hatası ve kayıp yanıt hatasız
sürücü sonucu üretmez. Motor enable/homing/hareket/register yazımı yoktur.
TMC2208'de doğrulanmış bit maskeleri çözülür; diğer desteklenen çiplerde
ham register gösterilir. TMC2660, yan etkili register-seçimi nedeniyle eski
pasif yolda kalır. M07 bilgi tanılamasıdır; M10 ayrılmış/boş kalır.
CI hem normal GET hem doğrudan kayıt/iletişim hata akışını sınar; yerel test yoktur.
