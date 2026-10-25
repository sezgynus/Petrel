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
| Dashboard Z | Dinamik 0–3 ondalık | 48 px alana sığan en yüksek hassasiyet; sondaki sıfırlar kaldırılır. |
| Dashboard Z offset | Dinamik 0–3 ondalık | Aynı 48 px bütçesi; sığmazsa hassasiyet azaltılır. |
| Dashboard akış >=100 mm³/s | Tam sayı | 100.3mm3/s, 74 px sütunu aşıyor. |
| Yoğun mesh ve geniş negatif değerler | Eski yoğunluk bazlı hassasiyet | Nokta etiketleri birbirine taşmamalı; 9+ sütunda eski biçim korunur. |
| Olağandışı uzun menü/önizleme/süre değerleri | Alan bazlı eski kısa biçim | Yeni basamaklar sığmazsa eski hassasiyete dönülür; menüde o da sığmazsa sınırlandırılmış # kullanılır. |

Örnekler: Move Z -100.123 yerine -100.12; mesh 8 sütunda -0.126 yerine -0.13. Sayısal etiketler için mevcut piksel bütçeleri korunur.

Telemetri toplama sıklığı, tahmin algoritması ve komut adımları değiştirilmez. Maintenance kanıt değerlerinin dört anlamlı basamaklı genel biçimi korunur; bunların tümü için tek bir Mainsail karşılığı yoktur. Aynı zamana ait olmayan ölçümler biçim eşliğiyle eşitlenmez.

## Doğrulama

CI regresyonları JavaScript çalışma zamanı ile yuvarlama sınırlarını, ham komut değerlerini ve etiketlerin piksel sınırlarını karşılaştırır. Normal regresyon iş akışı tam test paketini ve Maintenance ölçümlerini çalıştırır; doküman görsellerini yeniden üretmez. Tam PNG/GIF yayını Documentation Render üzerinden manueldir; yalnız NFC yayını başarılı aynı-SHA regresyonu ve `docs(nfc):` başlığı gerektirir. `docs(audit):` imzalama yolu tam üretimi aynı commit içine alabilir. Sıkı yayımlanmış görsel eşliği `PETREL_VERIFY_PUBLISHED_SCREENS=1` ile 24 Maintenance sahnesini kapsar; her push’ta tüm sahneleri kapsamaz. Fiziksel ekran testi ayrıca gerekir; bu rapor donanım testi yapıldığını iddia etmez.

Z ve Z offset alanları en fazla üç ondalıktan başlayıp metin sığana kadar hassasiyeti azaltır. Ham değer/komut değiştirilmez. Dashboard biçimlendirmesi yalnız ham değer değişince hesaplanır; iki alan için sınırlı önbellek kullanılır. Sabit genişlikte boşluk dolgusu ve mevcut alan temizliği eski rakam kalıntılarını önler. Mesh ve sıcaklık kuralları korunur.

## Dashboard hizalaması

Tüm sayısal alanların ilk karakteri 20 px ikon kutusunun 4 px sağından başlar (ikon X + 24 px). Başta dolgu boşluğu kullanılmaz; sıcaklık çiftleri tek, boşluksuz metindir. Z/offset boşluk dolgusu yalnız sağa eklenir. Metin küçülürken önceki alan temizlenir; değişmeyen değer yeniden çizilmez. Sütun bütçesini aşan olağandışı değerler komşu ikona taşmak yerine # ile gösterilir. Sayısal hassasiyet ve ham değerler değişmez.

X/Y/Z ikonlarının altında (x = ikon X + 3..16, y = 470..472) bulunan 14×3 piksellik çizgi, mevcut abonelikten gelen Klipper `toolhead.homed_axes` durumunu gösterir: referanslanmışsa turkuaz, referanslanmamışsa amber, veri geçersiz veya bağlantı yoksa gri. Ayrı üç alanlı çizim önbelleği yalnız değişen çizgileri günceller; ek Moonraker isteği, ikon, animasyon ya da dashboard tam çizimi gerekmez.

## Gösterge denetimi düzeltmeleri

Wi-Fi okuma kuyruğu hataları ve iptaller arayüz çevrimini kesmez; sinyal bilinmiyor olur ve beş saniyelik tekrar aralığı korunur. Info aynı Wi-Fi önbelleğini kullanır, ikinci bir iw sorgusu başlatmaz. Maintenance üst şeridi temizlediğinde saat, Wi-Fi ve Klipper önbellekleri birlikte geçersizleştirilir. Başlıklar Wi-Fi bölgesinden önceki 23 karakterlik alana sığdırılır; uzunsa üç noktayla kısaltılır. Yayımlanmış görsel kontrolleri repodaki dosyaları inceler; açıkça istenen üretim, görselleri yenileyip yayından önce sıkı Maintenance eşliğini doğrular. [Üretim sözleşmesine](ui-emulator_TR.md#png-çerçeve-ve-gif-yenileme) bakın.
