# Canlı Maintenance güvenlik kanıtları (geliştirme)

[English](maintenance-runtime.md) · [Güvenlik oturumu](maintenance-safety_TR.md)

**Aşama 5:** Petrel'in mevcut işlemleri ve Moonraker job queue için yalnız ihtiyaç anında canlı güvenlik bağlamı. Bu modül normal telemetri akışında polling, yeni worker, komut veya aktüatör eklemez.

`maintenance_runtime.read_queue_evidence(client, epoch, config_marker)`, `job_queue` bileşeninin varlığını olumlu doğrulamak için küçük `GET /server/info` isteği yapar. Bileşen varsa `GET /server/job_queue/status` okur; yalnız bilinen kuyruk durumu ve *boş/dolu* bilgisi değişmez kanıt olarak kalır. Dosya adları ve kimlikler atılır. Başarısız veya bozuk yanıt kuyruk yok demek değildir. Her gözlem monoton zaman damgası taşır ve aynı Klipper epoch/config kapsamında en fazla üç saniye geçerlidir.

`live_safety_context(printer, evidence)`, kalıcı config ağacını yeniden kopyalamadan ihtiyaç anında subscription snapshot alır, etkin Petrel işlemlerini (jog/recovery, ayar kaydı, bed mesh, screws tilt, probe wizard, MMU) kontrol eder ve var olan fail-closed `precheck` için güncel `SafetyContext` üretir. Eksik print/pause/virtual SD/webhooks durumu reddedilir. UI menüsü boşta diye başka bir işlem güvenli sayılmaz.

**Güncel entegrasyon:** Controller katmanları kuyruk GET işlemlerini mevcut sınırlı worker üzerinde yapar; UI thread üzerinde veya her normal telemetri güncellemesinde çalıştırmaz. Kabul/gönderim için üç saniyelik tazelik sınırı vardır; aktif controller katmanları ayrıca kendi sınırlı izleme/yeniden okuma sözleşmelerini tanımlar. Harici istemciler kontroller arasında durum değiştirebildiğinden fiziksel gönderimde canlı durum da yeniden doğrulanır. Aktif çalışma kuralları için hareket, termal ve rezonans rehberlerine bakın.

Regresyonlar: `tests/test_maintenance_runtime.py`; bütün testler push'ta GitHub Actions üzerinde çalışır.
