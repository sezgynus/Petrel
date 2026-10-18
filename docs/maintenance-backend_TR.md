# Maintenance salt-okunur backend entegrasyonu

[English](maintenance-backend.md) · [Türkçe](maintenance-backend_TR.md) · [Güvenlik](maintenance-runtime_TR.md)

`PrinterData`, **Maintenance → Diagnostics** ile bağlı, istek üzerine çalışan `MaintenanceReadController` sahibidir. Altı okuyuculu ilk Aşama 6 artık uygulamanın tamamı değildir. `maintenance_executor.read_only_adapters()` kayıtları host/sistem, termal, hareket/sürücü, filament ve ortam bilgilerini kapsar; tam güncel liste burada ve içe aktarılan alan kayıtlarında tanımlıdır.

`maintenance_read_plan()` kayıtlı okuyucuları güncel keşif snapshot'ıyla kesiştirir. `start_maintenance_read(feature_id, device=...)` mevcut Maintenance worker'ında sınırlı salt-okunur ön kontrol başlatır. `poll_maintenance_read()` beklerken sonuç döndürmez, tamamlanınca `ReadResult` verir; `cancel_maintenance_read()` geç yanıtları geçersiz kılar. Kopuş/epoch değişimi işlem sahibini iptal eder. Kapatma yeni worker/client oluşturmaz veya değiştirmez.

Ön kontrol `/server/info` ve bileşen kuruluysa `/server/job_queue/status` üzerinden iş kuyruğunu olumlu doğrular. Başarısız endpoint kuyruk yok demek değildir. Yazıcı yaşam döngüsü, print/pause/manual-probe/MMU ve diğer Petrel işlemleri gönderimden ve sonuç alınmasından önce denetlenir. Bilgi okuyucuları donanım PASS üretmez. M07 ayrıca korunan, istek üzerine register sorgusudur; [yürütücüye](maintenance-read-executor_TR.md) bakın.

Normal menüleri açmak diagnostik okuyucuları çalıştırmaz. Pasif READY keşfinin ayrı sınırlı servis sorgusu, örneklenmiş kullanımın ayrı kayıt yolu vardır; bunlar diagnostik çalıştırma değildir. Sonuçlar açık etiket/birim ve sayfalama içeren [salt-okunur LCD raporlarında](maintenance-ui_TR.md) açılır. Petrel'in yerel rezervasyonu harici istemcileri kilitlemez. Controller, yürütücü ve diagnostik sunumu regresyonları GitHub Actions üzerinde çalışır.
