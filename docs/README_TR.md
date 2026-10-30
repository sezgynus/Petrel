# Dokümantasyon

[English](README.md) · [Türkçe](README_TR.md) · [Proje ana sayfası](../README_TR.md)

## Kullanıcı rehberleri

| Rehber | Kullanım amacı |
|---|---|
| [Yazıcı bağlantısı ve kurtarma](klipper-recovery_TR.md) | Olağan açılış bekleyişi, hata ayrıntıları ve korumalı restart eylemleri |
| [Kurulum ve yapılandırma](installation_TR.md) | Bağlantı, kurulum, harici ayarlar, güncellemeler ve sorun giderme |
| [Kconfig yapılandırma menüsü](configuration_TR.md) | Menüde gezinme, ayarları kaydetme ve uygulama, isteğe bağlı bileşenler ve otomatik yapılandırma |
| [DWIN yardımcı UART](dwin-uart_TR.md) | İsteğe bağlı Linux seri portunu kurma/kaldırma, programlardan erişim, baud hızları ve bağlantı sınırları |
| [Günlük kullanım](user-guide_TR.md) | Baskı, hareket, ısıtma, kalibrasyon, Device, Info, ışık ve güç |
| [Maintenance kullanımı](user-guide_TR.md#maintenance) | Bakım planları, donanım kontrolleri, sonuçlar, diagnostik, öneriler ve güncel ekranlar |
| [Maintenance fiziksel kabulü](maintenance-stage8-acceptance_TR.md) | Güvenlik kontrollü fiziksel testler, çıkış izinleri, kullanıcı gözlemi ve gerçek Pi kabulü |
| [MMU ve filament](mmu-guide_TR.md) | Happy Hare kanalları, makara atama, takım eşlemesi, EndlessSpool ve kurtarma |
| [NFC kartları ve paylaşım](user-guide_TR.md#nfc-ve-rfid) | Acil durdurma, makara kartı/gate, telefonla bağlantı paylaşma; [Kconfig kurulumu](configuration_TR.md#nfc) ve LCD Device → NFC Settings |
| [LCD uyumluluğu](lcd-assets_TR.md) | Desteklenen ekranı seçme ve panel kaynaklarını kontrol etme |
| [Orijinal DWIN kaynaklarına dönüş](restore-stock-dwin_TR.md) | Kalıcı Flash uyarısı, Creality DWIN_SET paketi ve LCD microSD geri yükleme adımları |
| [Print ve Tune](print-controls_TR.md) | Baskı ekranı, çalışma zamanı ayarları ve isteğe bağlı politika switchleri |

[Ekran galerisi](screenshots_TR.md): belgelenmiş örnek durumlar ve forumlarda kullanılabilecek doğrudan görsel bağlantıları.

## Katkı ve araçlar

| Rehber | Kullanım amacı |
|---|---|
| [Katkıda bulunma](../CONTRIBUTING_TR.md) | Issue, pull request, dokümantasyon ve geliştirme kontrolleri |
| [Kaynak kod yerleşimi](source-layout_TR.md) | Özellik sahipliği, ortak UI, maintenance grupları ve yalnız organizasyon değişikliği kontrolleri |
| [Emülatör ekran görüntüleri](ui-emulator_TR.md) | Çalışan serviste görüntü almayı açma ve görselleri kaydetme |
| [Testler](../tests/README_TR.md) | Otomatik kontrolleri çalıştırma ve donanım doğrulamasını planlama |
| [UI için C adayı profilleme](ui-native-profiling_TR.md) | Normal kaynak ölçümü, CPU örneklemesi ve Python tahsis kaynağını ayrı inceleme |
| [LCD görselleri](../assets/README_TR.md) | Özel ikon hazırlama ve görselleri tanıma |
| [Emülatör kaynakları](../assets/emulator/README_TR.md) | Eşleşen bilgisayar tarafı font ve ikonları seçme |

## İsteğe bağlı teknik ve geçmiş referanslar

Bu İngilizce referanslar panel çalışmaları veya geçmiş bağlam içindir; normal kullanım için gerekli değildir. Güncel davranış yukarıdaki kullanıcı rehberlerinde anlatılır.

- [T5UIC1 panel yapılandırması ve protokolü](t5uic1-reference.md): panel firmware/kaynakları ve düşük seviyeli referans.
- [Stok kaynak envanteri](lcd-assets.json): incelenmiş kaynak hash ve boyutları.
- [Geçmiş kaynak audit'i, 2026-10-05](source-audit.md): önceki incelemenin bulguları.
- [Geçmiş MMU sürücü entegrasyonu, 2026-10-08](mmu-driver-integration.md): MMU birleştirmesinden önceki entegrasyon kaydı.

- [Repo Markdown denetimi, 2026-10-18](documentation-audit-2026-10-18_TR.md): kaynak tutarlılığı, iki dil kapsamı, düzeltmeler ve tam incelenen-dosya envanteri.
