# Maintenance güvenlik oturumu kontrolleri (geliştirme)

[English](maintenance-safety.md) · [Planner](maintenance-test-planner_TR.md)

**Durum:** Bu modül fail-closed kabul ve oturum geçersizleştirme katmanıdır. Üretim okuyucuları ve fiziksel controller katmanları bunu kullanır; modülün kendisi komut göndermez veya UI çizmez.

`petrel/features/maintenance/execution/safety.py`, `SafetyContext`, `SafetyDecision`, `SafetySession`, `precheck` ve `MaintenanceSafetyCoordinator` tanımlar. Teste kabul için aynı Klipper epoch'u ve settings nesne işaretiyle READY, açıkça READY webhooks, boşta print istatistiği, kesin pasif virtual SD/pause, aktif manual probe veya meşgul MMU olmaması, pozitif olarak kontrol edilmiş iş kuyruğu ve diğer Petrel işlem çakışmalarının denetlenmiş olması gerekir. Kritik durum eksikse iyimser izin verilmez.

Çağıran taraf güncel iş kuyruğu kanıtını `queue_checked=True` ile bildirmelidir. `job_queue=None` ancak bileşenin bulunmadığı pozitif olarak doğrulanınca uygundur; mevcut kuyruk bilinen güvenli durumda ve boş olmalıdır. Diğer Petrel operasyonları için de `operations_checked=True`, `conflicting_operation=False` açıkça gereklidir. Mevcut Executor entegrasyonu bu bayrakları gerçek kontrolle üretmelidir; körlemesine True vermek güvenlik sözleşmesini bozar.

Aynı anda yalnız bir yerel oturum vardır. Monoton token, epoch ve proses içi config işaretini taşır; kaynak durum, kuyruk ve yanıtlar saklanmaz. Executor **her** yan etkili komuttan hemen önce güncel `SafetyContext` sunup `guard` çağırmalıdır. Kopuş, durum değişimi ve haricî print başlangıcı rezervasyonu geçersizleştirir; eski callback yeni oturuma etki etmez. Bu **evrensel bir yazıcı kilidi değildir** ve haricî Moonraker istemcilerinin eşzamanlı komutlarını engellemez. Oturumu bitirmek geri yükleme veya fiziksel PASS anlamına gelmez.

`tests/test_maintenance_safety.py`; eksik durum, kuyruk loading/starting, eşzamanlı işlemler, pause/printing, MMU/probe, epoch/config değişimi, eski token ve cancel/restart durumlarını kapsar. Regresyon kalite kapısı GitHub Actions CI'dır. Okuyucular ve fiziksel adaptörler ayrı entegredir; hiçbir kayıt gözetimsiz fiziksel eyleme izin vermez.
