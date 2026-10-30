# Repo Markdown kaynak denetimi — 18 Ekim 2026

[English](documentation-audit-2026-10-18.md) · [Türkçe](documentation-audit-2026-10-18_TR.md)

Denetim tabanı: `7830d04fb7794f541004f4289931a7e649ebd9a9` (master). **92 izlenen Markdown dosyası** envantere alınıp incelendi: **44 EN/TR çifti**, bilerek İngilizce tutulan üç teknik/tarihsel referans ve kendi içinde iki dilli bir ekran-görseli README dosyası.

İnceleme güncel kullanım akışlarını, API/komut sözleşmelerini, kimlikleri, sabit/limitleri, kurulum varsayılanlarını, kayıtları, kaynak bağlantılarını, yerel hedef/anchorları, çalıştırılabilir örnekleri ve çeviri kapsamını içerir. Geçmiş gözlemler ve ara toplamlar güncel kabul özeti değil tarihli kanıttır.

## Bulgular ve düzeltmeler

| ID | Belgeler | Düzeltme | Kaynak sınırı |
|---|---|---|---|
| D01 | tests/README*, CONTRIBUTING* | CI yalnız master için gösteriliyordu; bütün dal pushları ve imzalı HEAD kalite kapısı düzeltildi. | `.github/workflows/regression.yml`, `sign-commits.yml` |
| D02 | maintenance-backend*, read-executor* | Altı okuyucu/UI yok/entegrasyon bekliyor iddiaları kaldırıldı; üretim kayıtları, yerel okuyucular ve M07 istisnası açıklandı. | `petrel/features/maintenance/execution/executor.py`, `petrel/features/maintenance/execution/controller.py`, `petrel/features/maintenance/ui/view.py` |
| D03 | maintenance-test-catalog*, test-planner*, safety*, runtime*, guided* | Saf modül sorumluluğu mevcut controller/UI entegrasyonundan ayrıldı; F02/F12 kayıtları eklendi. | `petrel/features/maintenance/discovery/catalog.py`, `petrel/features/maintenance/execution/planner.py`, `petrel/features/maintenance/execution/guided.py` |
| D04 | maintenance-discovery* | READY sorgusu Spoolman ve roots dahil tam altı endpoint ile eşlendi; eski merge-öncesi ifadeler kaldırıldı. | `maintenance_services._ENDPOINTS` |
| D05 | maintenance-profiles*, pulse*, physical* | Genel 950-ms/tek-piksel/loş efekt iddiaları özelliğe bağlı süre ve 1–32-piksel RGB sözleşmesiyle değiştirildi. | `petrel/features/maintenance/domains/pulse/program.py`, `petrel/features/maintenance/domains/pulse/controller.py` |
| D06 | maintenance-stage8-acceptance*, test-recording* | Eski Self Tests yolu, üç saniyelik kullanıcı süresi ve eski kurulum/profil talimatları değiştirildi. | `petrel/features/maintenance/ui/view.py`, `petrel/features/maintenance/domains/pulse/controller.py` |
| D07 | maintenance-thermal*, reference-printer-acceptance* | Yedi ayrı H denemesi ve eski bekleme özetleri yerine birleşik H01 ve kayıtlı prosedür kabulü yazıldı; FAILED_METRIC korundu. | `petrel/features/maintenance/domains/thermal/controller.py`, acceptance JSON ledger |
| D08 | maintenance-thermal* | 16 Ekim hata incelemesinin eksik İngilizce karşılığı eklendi; tarihsel kapsam işaretlendi. | Dated source/trace context retained in both guides |
| D09 | maintenance-acceptance-2026-10-17*, audit-fixes*, resonance* | Tarihli kanıtlar tarihsel işaretlendi; kaldırılmış tavanı koruma ve park edilmiş E11 için elle MMU kapatma talimatları düzeltildi. | `petrel/features/maintenance/domains/thermal/measurements.py`, `petrel/features/maintenance/domains/filament/controller.py` |
| D10 | maintenance-pi-acceptance* | Worktree ölçüm sonuna kadar korundu; Python yolu genelleştirildi, gerçek sürüm A/B karşılaştırması aynı master checkoutlarından ayrıldı. | `tools/validate_maintenance_pi.py`, `tools/measure_petrel_resources.py` |
| D11 | user-guide*, installation*, README*, docs/README* | Açılış bekleme/kurtarma ve korumalı restart davranışı ana rehberlere eklendi. | `petrel/features/recovery/view.py`, `petrel/features/recovery/klipper.py`, `petrel/application/display.py` |
| D12 | print-controls*, user-guide* | Süre anlamları ayrı bölüme taşındı; toplam geçen süre, farklı Remaining/ETA, belirsiz değer ve gün farkı anlatıldı. | `petrel/features/printing/estimates.py`, `petrel/printer/interface.py`, `petrel/features/printing/view.py` |
| D13 | user-guide*, ui-emulator*, screenshots* | Info çubuğu anlatıldı; sabit galeri sayısı/tüm ekranlar iddiası kaldırıldı, çekim sürümü sınırı açıklandı. | `petrel/ui/theme.py`, `petrel/application/display.py`, screenshot scene registry |
| D14 | t5uic1-reference.md, source-audit.md | Area-0 boot bölgesi geri çizimi düzeltildi; İngilizce tarihsel audit içindeki Türkçe tablo çevrildi. | `PetrelDisplay._draw_boot_progress`, retained historical commits |
| D15 | TR/EN role/protocol guides | Kaçırılmış backtickler düzeltildi; çalıştırılabilir yer tutucular, komut blokları ve örnek görsel sırası eşlendi. | Full Markdown pair review and CI document contracts |

## Doğrulama ve sınırlar

`tests/test_markdown_contracts.py` yerel Markdown/HTML bağlantılarını, bölüm anchorlarını, açık dil-çifti istisnalarını, çiftlerde komut blokları/görsel sırasını ve keşif endpoint kapsamını denetler. Bunlar anlamsal incelemeyi destekler; sayı eşitliği çeviri anlamını veya donanım davranışını kanıtlamaz.

Bu denetimde yazıcının çalışma davranışı, kabul JSON'u, fiziksel test sonuçları veya PNG/GIF görsel baytları değiştirilmedi. Mevcut görseller örnek çekimdir; güncel metin sonraki kurtarma/süre değişikliklerini anlatır. Harici URL erişimi ağ üzerinden eksiksiz sınanmadı. Lokal regresyon/emülatör veya fiziksel yazıcı testi çalıştırılmadı; tam paket imzalı commit üzerinde CI'da çalışır.

Yalnız-İngilizce istisnaları mevcut dizin politikasını izler: `t5uic1-reference.md`, `source-audit.md`, `mmu-driver-integration.md`. Bunlar incelendi; eksik kullanıcı rehberi çevirisi sayılmadı. `docs/assets/screens/README.md` iki dili tek dosyada içerir.

## Taban sürümün tam dosya envanteri

| Dosya | İnceleme sonucu |
|---|---|
| `CONTRIBUTING.md` | Düzeltildi |
| `CONTRIBUTING_TR.md` | Düzeltildi |
| `README.md` | Düzeltildi |
| `README_TR.md` | Düzeltildi |
| `assets/README.md` | İncelendi; korundu |
| `assets/README_TR.md` | İncelendi; korundu |
| `assets/emulator/README.md` | İncelendi; korundu |
| `assets/emulator/README_TR.md` | İncelendi; korundu |
| `assets/icons/README.md` | İncelendi; korundu |
| `assets/icons/README_TR.md` | İncelendi; korundu |
| `assets/shared-artwork/README.md` | İncelendi; korundu |
| `assets/shared-artwork/README_TR.md` | İncelendi; korundu |
| `assets/stock-dwin/README.md` | İncelendi; korundu |
| `assets/stock-dwin/README_TR.md` | İncelendi; korundu |
| `docs/README.md` | Düzeltildi |
| `docs/README_TR.md` | Düzeltildi |
| `docs/assets/screens/README.md` | İncelendi; korundu |
| `docs/installation.md` | Düzeltildi |
| `docs/installation_TR.md` | Düzeltildi |
| `docs/klipper-recovery.md` | İncelendi; korundu |
| `docs/klipper-recovery_TR.md` | İncelendi; korundu |
| `docs/lcd-assets.md` | İncelendi; korundu |
| `docs/lcd-assets_TR.md` | İncelendi; korundu |
| `docs/maintenance-acceptance-2026-10-17.md` | Düzeltildi |
| `docs/maintenance-acceptance-2026-10-17_TR.md` | Düzeltildi |
| `docs/maintenance-assessment.md` | İncelendi; korundu |
| `docs/maintenance-assessment_TR.md` | İncelendi; korundu |
| `docs/maintenance-audit-fixes.md` | Düzeltildi |
| `docs/maintenance-audit-fixes_TR.md` | Düzeltildi |
| `docs/maintenance-auxiliary.md` | İncelendi; korundu |
| `docs/maintenance-auxiliary_TR.md` | İncelendi; korundu |
| `docs/maintenance-backend.md` | Düzeltildi |
| `docs/maintenance-backend_TR.md` | Düzeltildi |
| `docs/maintenance-discovery.md` | Düzeltildi |
| `docs/maintenance-discovery_TR.md` | Düzeltildi |
| `docs/maintenance-filament.md` | İncelendi; korundu |
| `docs/maintenance-filament_TR.md` | İncelendi; korundu |
| `docs/maintenance-guided.md` | Düzeltildi |
| `docs/maintenance-guided_TR.md` | Düzeltildi |
| `docs/maintenance-motion.md` | İncelendi; korundu |
| `docs/maintenance-motion_TR.md` | Düzeltildi |
| `docs/maintenance-physical.md` | Düzeltildi |
| `docs/maintenance-physical_TR.md` | Düzeltildi |
| `docs/maintenance-pi-acceptance.md` | Düzeltildi |
| `docs/maintenance-pi-acceptance_TR.md` | Düzeltildi |
| `docs/maintenance-probe.md` | İncelendi; korundu |
| `docs/maintenance-probe_TR.md` | İncelendi; korundu |
| `docs/maintenance-profiles.md` | Düzeltildi |
| `docs/maintenance-profiles_TR.md` | Düzeltildi |
| `docs/maintenance-pulse.md` | Düzeltildi |
| `docs/maintenance-pulse_TR.md` | Düzeltildi |
| `docs/maintenance-read-executor.md` | Düzeltildi |
| `docs/maintenance-read-executor_TR.md` | Düzeltildi |
| `docs/maintenance-reference-printer-acceptance.md` | Düzeltildi |
| `docs/maintenance-reference-printer-acceptance_TR.md` | Düzeltildi |
| `docs/maintenance-resonance.md` | Düzeltildi |
| `docs/maintenance-resonance_TR.md` | Düzeltildi |
| `docs/maintenance-runtime.md` | Düzeltildi |
| `docs/maintenance-runtime_TR.md` | Düzeltildi |
| `docs/maintenance-safety.md` | Düzeltildi |
| `docs/maintenance-safety_TR.md` | Düzeltildi |
| `docs/maintenance-stage8-acceptance.md` | Düzeltildi |
| `docs/maintenance-stage8-acceptance_TR.md` | Düzeltildi |
| `docs/maintenance-system.md` | Düzeltildi |
| `docs/maintenance-system_TR.md` | Düzeltildi |
| `docs/maintenance-test-catalog.md` | Düzeltildi |
| `docs/maintenance-test-catalog_TR.md` | Düzeltildi |
| `docs/maintenance-test-planner.md` | Düzeltildi |
| `docs/maintenance-test-planner_TR.md` | Düzeltildi |
| `docs/maintenance-test-recording.md` | Düzeltildi |
| `docs/maintenance-test-recording_TR.md` | Düzeltildi |
| `docs/maintenance-thermal.md` | Düzeltildi |
| `docs/maintenance-thermal_TR.md` | Düzeltildi |
| `docs/maintenance-ui.md` | İncelendi; korundu |
| `docs/maintenance-ui_TR.md` | İncelendi; korundu |
| `docs/mmu-driver-integration.md` | İncelendi; korundu |
| `docs/mmu-guide.md` | İncelendi; korundu |
| `docs/mmu-guide_TR.md` | İncelendi; korundu |
| `docs/print-controls.md` | Düzeltildi |
| `docs/print-controls_TR.md` | Düzeltildi |
| `docs/restore-stock-dwin.md` | İncelendi; korundu |
| `docs/restore-stock-dwin_TR.md` | İncelendi; korundu |
| `docs/screenshots.md` | Düzeltildi |
| `docs/screenshots_TR.md` | Düzeltildi |
| `docs/source-audit.md` | Düzeltildi |
| `docs/t5uic1-reference.md` | Düzeltildi |
| `docs/ui-emulator.md` | Düzeltildi |
| `docs/ui-emulator_TR.md` | Düzeltildi |
| `docs/user-guide.md` | Düzeltildi |
| `docs/user-guide_TR.md` | Düzeltildi |
| `tests/README.md` | Düzeltildi |
| `tests/README_TR.md` | Düzeltildi |
