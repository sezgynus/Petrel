# Mainsail sayısal gösterim eşliği

[English](mainsail-numeric-display.md)

Referans: Mainsail `dda4f43f2a2e667af9a0050c0db151daad0c8516` kaynak kodu.

## Uygulananlar

- MMU kalan filament yüzdesi: yukarı yuvarlama; toplam ağırlık için initial_weight, yoksa filament.weight. Toplam bilinmiyorsa yüzde bilinmiyor.
- Fan, hız/akış override, ışık, CPU/RAM ve MCU yükü: JavaScript Math.round davranışı.
- Canlı hız: toFixed(0); akış: negatifleri gösterimde sıfıra sınırlama ve sığdığı yerde toFixed(1).
- Move X/Y iki, Z üç; geniş Z offset alanları üç ondalık. Dashboard X/Y iki ondalık.
- MMU nozzle sıcaklığı bir ondalık; geniş hedef sıcaklık alanları ham sayısal değer. Sistem sıcaklıkları toFixed(0).
- PA/smooth time üç, SCV bir, firmware retraction uzunlukları iki basamakta aşağı kesilir. Retraction hızları ve Motion hız/ivme değerleri tam sayıya kesilir. Cruise ratio yüzde olur.
- Elapsed/Remaining saniyeli H:MM:SS; dosya önizleme süresi gün/saat/dakika/saniye. Önizleme ağırlığı tam gram; filament uzunluğu 1000 mm üstünde iki ondalık metre, diğer durumda tam mm.
- Mesh değerleri ve min/max sığdığı yerde üç ondalık.

## Yerleşim nedeniyle korunan farklar

| Alan | Korunan gösterim | Gerekçe |
|---|---|---|
| Dashboard nozzle/bed sıcaklık çifti | Tam sayı | 8 px font ile ondalıklı çift 74 px sütunu aşıyor. |
| Dashboard Z | Bir ondalık | İşaret ve üç tam basamakla üç ondalık sağ sütuna sığmıyor. |
| Dashboard Z offset | İki ondalık | -20.000, 48 px alanı aşıyor. |
| Dashboard akış >=100 mm³/s | Tam sayı | 100.3mm3/s, 74 px sütunu aşıyor. |
| Yoğun mesh ve geniş negatif değerler | Eski yoğunluk bazlı hassasiyet | Nokta etiketleri birbirine taşmamalı; 9+ sütunda eski biçim korunur. |
| Olağandışı uzun menü/önizleme/süre değerleri | Alan bazlı eski kısa biçim | Yeni basamaklar sığmazsa eski hassasiyete dönülür; menüde o da sığmazsa sınırlandırılmış # kullanılır. |

Örnekler: Move Z -100.123 yerine -100.1; mesh 8 sütunda -0.126 yerine -0.13. Sayısal etiketler için mevcut piksel bütçeleri korunur.

Telemetri toplama sıklığı, tahmin algoritması ve komut adımları değiştirilmez. Maintenance kanıt değerlerinin dört anlamlı basamaklı genel biçimi korunur; bunların tümü için tek bir Mainsail karşılığı yoktur. Aynı zamana ait olmayan ölçümler biçim eşliğiyle eşitlenmez.

## Doğrulama

CI regresyonları JavaScript çalışma zamanı ile yuvarlama sınırlarını, ham komut değerlerini ve etiketlerin piksel sınırlarını karşılaştırır. Tam test paketi, Maintenance ölçümleri ve tüm dokümantasyon ekran renderları CI içinde çalışır. Fiziksel ekran testi ayrıca gerekir; bu rapor donanım testi yapıldığını iddia etmez.
