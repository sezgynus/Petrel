# Maintenance Aşama 8 — yönlendirmeli donanım gözlem sözleşmeleri

[English](maintenance-guided.md)

Bu **güvenilir hedef ve kullanıcı onayı katmanıdır**; aktüatör değildir. Üretim pulse derlemesi ve fiziksel yürütme ayrı [pulse](maintenance-pulse_TR.md) ve [controller](maintenance-physical_TR.md) katmanlarında uygulanmıştır.

`maintenance_guided.guided_plan(snapshot)`, mevcut değişmez discovery/catalog/planner kayıtlarını birleştirip yalnız tam eşleşen USER yöntemi adaylarını sunar: `F01` RPM'siz stok part fan, `F02` hız kademeleri, `F12` adaptif kalkış eşiği, `F04` gerçekten keşfedilmiş fan_generic örnekleri, `O04` adlandırılmış LED cihazları, `O03` açıkça `visual` rolü verilen ve `maintenance.visual:<object>` kanıtı bulunan her `output_pin` ile `S18` açıkça `audible` rolü verilen ve `maintenance.audible:<object>` kanıtı bulunan her `pwm_cycle_time`. Rastgele `output_pin`, heater fan, controller fan, servo, macro, bilinmeyen fan ya da sahte takometre bu listeye giremez. Donanım fiziksel olarak takılı olsa dahi servis kanıtı eksikse aday gösterilmez.

`GuidedConsentGate`, tam eşleşen kayıtlı hedefi, güncel READY epoch/config durumunu ve *olumlu doğrulanmış* iş kuyruğu ile Petrel operasyon kontrollerini içeren fail-closed `MaintenanceSafetyCoordinator` koşullarını denetler. Açık kullanıcı isteğini kaydeder ancak hiçbir komutu çalıştıramaz veya kuyruğa alamaz. Tek olumlu terminal kayıt `CONSENTED / no_hardware_command_dispatched` şeklindedir. Onay; motor dönmesi, ışık yanması, ses duyulması veya fiziksel PASS kanıtı değildir.

Ayrı fiziksel controller küçük bir izin listeli komut adaptörü kullanır; her yazmadan hemen önce kuyruk/operasyon güvenlik kanıtı tekrar denetlenmeli, uygun hedeflerde başlangıç durumu kaydedilmeli, yürütme ve hata/kopma durumunda temizleme sınırlı ve doğrulanmış olmalı, ancak sonra kullanıcı gözlem kanıtı istenmelidir. Komutlanan PWM ile ölçülen RPM ayrı tutulmalıdır. Güvenli geri alma tanımlanamayan bütün profiller engellenmelidir.

Bu saf katman UI, endpoint polling, worker oluşturma, fiziksel komut veya baskı sıcak yolu işi yapmaz; üretim UI/controller entegrasyonu ayrıca vardır. Regresyon: `tests/test_maintenance_guided.py`.
