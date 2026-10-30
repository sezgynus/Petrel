# Kaynak kod yerleşimi

[English](source-layout.md) · [Türkçe](source-layout_TR.md) · [Dokümantasyon](README_TR.md)

Kaynak ağacı mevcut kodu özellik ve sorumluluğa göre gruplar. Organizasyon refactoring'i çalışma davranışını korur: aynı ekran ve yazıcı nesneleri, worker sahipliği, komut korumaları, olay akışı, ayarlar, ekran koordinatları ve protokol yükleri kullanılmaya devam eder. Metot gövdeleri ve sınıf durumu, mantıkları yeniden yazılmadan taşınır. Yalnızca dosya adı veya satır sayısı, bütünlüklü bir modülü bölmek için gerekçe değildir.

## Depo haritası

```text
run.py
petrel/
  application/           display.py, startup.py, input.py, tick.py
  printer/               interface.py, models.py, state.py, capabilities.py
  moonraker/             client.py, subscription.py
  hardware/              encoder.py, dwin/
  ui/                    dashboard.py, header.py, home.py, list_menu.py, selection.py
  features/
    files/               printer.py, browser_view.py, preview.py, metadata.py, ...
    printing/            printer.py, view.py, tuning.py, estimates.py
    motion/              printer.py, view.py, settings.py
    temperature/         printer.py, view.py, preset_store.py
    info/                printer.py, view.py, system.py, qr.py
    nfc/                 printer.py, core.py, backend.py, reader.py, *_view.py, ...
    maintenance/         printer.py, discovery/, execution/, domains/, ...
    mmu/                 state.py, view.py, filament_view.py
    power/               printer.py, view.py, lifecycle.py
    buzzer/              control.py, pwm.py, ipc.py, view.py, ...
    leveling/            bed_mesh.py, probe_wizard.py, *_view.py, ...
    case_light/          printer.py, view.py
    display_settings/    settings.py, view.py
    spoolman/            printer.py, spool_view.py, tags.py
    recovery/            klipper.py, view.py
    software_update/     updater.py
  artwork/               resources.py, boot.py, shared.py, icon_library.py, ...
  emulator/              framebuffer.py, assets.py, runtime.py, remote.py, ...
  diagnostics/           memory_profile.py
  configuration_identity.py
  migration.py
  version.py
tools/
tests/
klipper_extras/
native/
kernel/
assets/
docs/
```

Harita sahipliği gösterir; `...` yardımcı dosyaların kısaltmasıdır, geleceğe yönelik yeni bir katman önerisi değildir. Python uygulama kodu `petrel/` altındadır. Kökteki dosyalar dağıtım/yapılandırma giriş noktalarıdır. Testler, geliştirme araçları, native/kernel kodu, Klipper extra modülleri ve görseller kendi amaçlarına göre ayrı tutulur.

## Değişiklik nereye yapılır

| Konum | Sorumluluk |
|---|---|
| `application/display.py` | Ekran nesnesini birleştirme, kaynak ve menü başlatma, eylemleri ve kapanışı koordine etme |
| `application/startup.py` | Mevcut UART yeniden bağlantısı, panel güç yaşam döngüsü ve açılış/flash ilerleme metotları |
| `application/input.py` | Mevcut enkoder/buton olayları, toplu adımlar ve ekran yönlendirmesi |
| `application/tick.py` | Mevcut UI tick, telemetri sunumu ve periyodik güncelleme metotları |
| `printer/interface.py` | `PrinterData` birleştirme, mevcut worker/session sahipliği, telemetri ve komut aktarımını koordine etme |
| `printer/models.py` | Mevcut konum, düzenleme/flag ve malzeme preset kayıtları; `interface.py` içe aktarma bağlarını korur |
| `ui/` | Özellikler arasında kullanılan ortak ekran öğeleri ve menü/seçim araçları |
| `features/<feature>/printer.py` | Özelliğin `PrinterData` üzerindeki mevcut metotları; ayrı istemci, worker veya durum sahibi oluşturmaz |
| `features/<feature>/view.py`, `*_view.py` | Özelliğin mevcut ekran metotları; mevcut mixin yaklaşımıyla birleştirilir |
| Diğer özellik modülleri | Mevcut özellik durumu, protokol entegrasyonu, ayarlar ve hesaplamalar |
| `moonraker/`, `hardware/` | Aktarım, abonelik ve fiziksel ekran/enkoder entegrasyonu |
| `artwork/`, `emulator/`, `diagnostics/` | Yönetilen görseller, bilgisayar tarafı ekran emülasyonu ve profilleme |

Ekran sorumlulukları farklı olduğunda bir özellik birden fazla açık isimli view içerebilir. Küçük ve bütünlüklü ilgili işlevleri birlikte tutun. Açıklayıcı mevcut modül adlarını koruyun; yalnızca dosyayı kısaltmak için genel `utils` modülleri oluşturmayın veya ilgisiz yardımcıları bir özelliğe taşımayın.

## Maintenance grupları

| Dizin | Mevcut sorumluluk |
|---|---|
| `discovery/` | Kabiliyet keşfi, cihaz envanteri ve keşif oturumu |
| `execution/` | Planlar, çalışma/dispatch korumaları, controller, executor ve yönlendirmeli iş akışı |
| `domains/` | Isıl, hareket, filament, prob ve yardımcı çıkışlar gibi fiziksel alan uygulamaları |
| `assessment/` | Değerlendirme modeli, kuralları, kalıcı kayıtları ve servisi |
| `records/` | Kayıtlar, kullanım toplayıcıları, cihaz sunumu ve servis referansları |
| `diagnostics/` | Raporlar, test izleme ve kaynak ölçümü |
| `ui/` | Maintenance menüleri, görünümleri, gezinme ve değerlendirme sunumu |

`features/maintenance/printer.py`, `PrinterData` üzerindeki mevcut köprü metotlarını tutar; mevcut controller veya worker sahipliğini devralmaz.

## Yerleşimi düzenleme ve kontrol etme

Açık paket importları kullanın; kod taşırken test patch hedeflerini, araç importlarını, kurulum yollarını ve belgeleri güncelleyin. `bed_mesh`, `screws_tilt`, `probe_wizard` gibi alan adları, kalıcı anahtarlar ve native dosya isimleri çalışma sözleşmesidir; Python modül yolu değildir. Bunlara sınırsız metin değiştirme uygulamayın.

Bağımlılık yönünü koruyun: özellik metotları `self` üzerinden sağlanan ekran/yazıcı nesnesini kullanır; birleştirilmiş ekran/yazıcı sınıfını uygulama giriş noktasından geri içe aktarmamalıdır. Sorumluluk zaten mevcutsa metotları mevcut özellik mixin'lerine taşıyın. Yeni gruplama mixin'leri bağımsız başlatma veya durum sahipliği içermemelidir.

Yalnızca organizasyon değişikliğinde, taşıma öncesi/sonrası metot AST'lerini ve sınıf alanlarını karşılaştırın, decorator/imzaları koruyun ve ardından [regresyon kontrollerini](../tests/README_TR.md) çalıştırın. Mevcut testler içe aktarma anında izole donanım taklitleri kullanır: `patch.dict` kapsamı bittikten sonra içe aktarılan yeni kopyayı değil, `tests/test_regressions.py` tarafından tutulan sahip modülü patch edin. Mevcut UI-state ve maintenance benchmark'larını da çalıştırın. İmzalama botu commit SHA'sını değiştirir; imzasız önceki commit yerine imzalı branch HEAD'ini doğrulayın. Kuyrukta veya başarısız bir workflow, geçmiş kontrol sayılmaz.

Kurulumdan sonra ekran davranışı olağan fiziksel doğrulamayı yine gerektirir. Bu yerleşim değişikliği ayar migrasyonu, yeni servis veya yeniden üretilmiş panel kaynağı gerektirmez. Belge ekran görüntüsü workflow'u ayrıca istenerek elle çalıştırılır.
