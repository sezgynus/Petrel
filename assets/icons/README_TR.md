# Yönetilen LCD ikonları

[English](README.md) · [Türkçe](README_TR.md)

Kütüphanede **212 ikon, 0–211 ID’leri** bulunur. **212–255 boştur**; sonraki ikonu **212** ID’siyle ekleyip sırayla devam edin. Dosya adları sıfır dolgulu olmalıdır (`212.jpg`, `assets/icon-source/212.svg`). UI ve üretim araçlarını `lcd_resources.py` sabitlerine bağlayın. Tek seferlik [ID taşıma haritası](id-migration.json) eski/yeni ID’leri kaydeder; çalışma zamanında tekrar uygulanmaz.

Temizlikte **40 kullanılmayan ikon** (44.535 JPEG baytı) kaldırıldı. Eski 203 ID’sinin Bed Mesh menüsünde kullanıldığı bulundu; `ICON_BED_MESH` (165) olarak korundu. Kalan 212 JPEG ve düzenlenebilir SVG’nin baytları, boyutları, renkleri ve kalitesi değiştirilmeden taşındı. ID’ler ardışıktır; fiziksel yerleşim ID sırasından bağımsızdır.

## Kaynaklar ve paketleme

Bu dizine baseline **4:2:0 JPEG** ekleyin. ID’ler benzersiz ve 0–255 aralığında olmalıdır. Progressive JPEG, diğer renk örneklemeleri, geçersiz dosya adları ve 32767 bayttan büyük yükler reddedilir. Görselleri yeniden üretme aracı açıkça çalıştırılmadıkça mevcut JPEG’ler korunur.

Picture Flash **0** açılış görseline, **1** ortak QR/UI görseline, **2–15** ise **2** numaralı ikon kütüphanesine ayrılmıştır. Güncel çıktı **13×32 KiB**, yani **2–14** slotlarını kullanır. Bu bloklarda **12.581 kullanılabilir bayt boşluk** vardır; **15** numaralı slot da kullanılabilir. Ayrılmış alanın toplam kullanılabilir boşluğu **45.348 bayttır**. Yeni kaynaklarla bu değerler değişir. ID silinince 4096 baytlık dizin küçülmez.

Çalışma zamanı ve dışa aktarma aracı aynı deterministik paketleyiciyi kullanır: best-fit decreasing ardından önceki boşlukları birleştiren sınırlı subset-sum aramaları. Daha büyük boşluk için fazladan blok tüketilmez. Her blok araması kesindir; sıralı aramalar tüm paket için küresel optimum kanıtı değildir. Her bloğun son baytı ayrılmıştır; JPEG blok sınırını aşmaz. Paketleme adresleri değiştirir; JPEG baytlarını ve ID’leri değiştirmez. Önbellek, değişmeyen kaynakları her bağlantıda yeniden paketlemeyi önler.

```sh
python tools/pack_icon_library.py assets/icons /tmp/2.ICO --library 2
```

`assets/emulator/2.ICO` repodaki referans çıktıdır. Üretim sistemi paketi JPEG kaynaklarından otomatik oluşturur; emülatör aynı kaynakları kullanır. Varlıklar değişince çıktıyı ve `docs/lcd-assets.json` dosyasını güncelleyin.

## Otomatik güncelleme ve ID taşıması

İlk LCD bağlantısında kütüphane eşitlenir. **PETICO02** metadata sürümü sıkıştırılmış ID’leri eski dizinden ayırır. PETICO01 kaydıyla yeni ID’lerde açılış animasyonu başlatılmaz; ilk geçişte animasyon yeni dizin tamamlandıktan sonra başlar. Picture Flash yazılmadan tüm native animasyonlar durur. Önce yük blokları, en son dizin yazılır; CRC doğrulamalı kontrol noktaları yarım yüklemeyi sürdürür. Sonraki değişmeyen bağlantılarda Flash yazılmaz. Başarısız otomatik Picture Flash denemesi aynı süreçte tekrarlanmaz.

0/1 slotları, ekran/ses ayarları, NFC UID’leri ve Spoolman kayıtları taşınmaz. LCD SD güncellemesi gerekmez. Eski 3/7 kütüphane tabanlarının kayıtları yönetilen 2 tabanında kullanılmaz. Eski yazılıma dönüldüğünde o yazılım kendi kaynaklarından kendi dizinini yeniden oluşturur.

Elle tanılama yüklemesinden önce Petrel’i durdurun. `tools/reload_icons.py` güncel kaynakları kontrol noktalı olarak zorla eşitler. `tools/flash_icon_library.py` varsayılan olarak güncel kaynakları; açık `--file` seçeneğiyle belirtilen ICO’yu yükler. Tanılama yüklemesi eski metadata’yı geçersiz kılar; sonraki normal açılış yönetilen kaynakları geri getirir. [LCD görselleri](../README_TR.md) kılavuzuna bakın.

## Güncel kaynaklar

| Amaç | ID’ler | Boyut / davranış |
|---|---|---|
| Dashboard hotend / tabla | 9 / 10 | 18×18; kullanılmayan eski 20×20 ayar sürümleri kaldırıldı |
| MMU normal / seçili | 120 / 121 | 110×100 |
| Ekran normal / seçili | 71 / 72 | 110×100 |
| Klasör; MCU; makine; sunucu; yazılım; güç | 122; 123; 124; 125; 69; 70 | Klasör 20×18, diğerleri 20×20 |
| Makara flanşları / boş makara | 73–86 / 87 | 1–7 genişlik, 52 yükseklik / 42×52 |
| Bakım kontrol / tanılama / öneri / servis | 126–129 | 20×20 |
| Wi-Fi zayıf / orta / güçlü | 130–132 | 20×20, filtrelenen koyu arka plan |
| NFC ayarları; arayüz; port | 133; 118; 119 | 20×20 |
| RFID ana menü normal / seçili | 134 / 135 | 110×100 |
| Telefon yaklaştırma | 136–147 | 12 opak 160×160 kare, kanal 2, 200 ms/kare |
| Küçük NFC paylaşım normal / seçili | 148 / 149 | 20×20 kontrol, 16×16 sembol |
| Makara yaklaştırma | 150–161 | 12 opak 160×160 kare, kanal 3, 200 ms/kare |
| Acil durum; makara; ata; kaldır; ileri; yeniden dene | 35; 47; 48; 49; 50; 51 | Ortak 20×20 amaç ikonları |
| Kart yaklaştırma | 57–68 | 12 opak 160×160 kare, kanal 3, 200 ms/kare |
| Bed Mesh menüsü | 165 | `ICON_BED_MESH` sabiti |
| Fan; açılış | 192–199; 207–211 | Native animasyon kanalları 1 / 0 |

Telefon paylaşımı sunucuda kare zamanlayıcısı olmadan 2,4 saniyede döner. Okuma, hata, iptal ve pencere değişimi animasyonu durdurur. Yetenek keşfi Software bölümündeki Petrel sürümünden önceki küçük NFC kontrolünün görünürlüğünü belirler; QR altında ek paylaşım satırı yoktur. Paylaşım hatasında ilk kare sabit gösterilir.

Makara ve genel kart ataması ortak yakalama popup’ını kullanır. Emergency Assign/Replace kart karelerini, makara ataması makara karelerini kullanır. Tıklama iptal eder; okuma, açık UID/kayıt onayından önce animasyonu durdurur. Yalnız okuma Spoolman ataması yazmaz. Güç pencereleri, bağlantı kapanması ve ekran değişimi animasyonu durdurur/temizler; bekleyen yakalama kaynak ekrana dönüldüğünde sürer veya tamamlanır. Yeniden çizim ve enkoder hareketi yakalamayı baştan başlatmaz.

## Görsel üretimi

- `python tools/render_icon_sources.py --ids 148 149` seçilen SVG ID’lerini üretir; `--ids` olmadan yalnız bilinçli tam yeniden üretim yapın. Fiziksel panel baseline 4:2:0 ister; 4:4:4 daha önce görselleri bozdu.
- `python tools/render_button_backings.py` güncel buton zemini ID’lerini kullanır.
- `python assets/icon-source/nfc-settings/render.py` ve `python assets/icon-source/rfid/render.py` güncel amaç ikonlarını ve SVG’lerini üretir.
- `python assets/icon-source/nfc-card/render.py`: kalite 65, optimize Huffman tabloları, baseline 4:2:0.
- `python assets/icon-source/nfc-spool/render.py`: özgün kayıpsız PNG’ler, kalite 84, optimize Huffman tabloları, baseline 4:2:0.
- `python assets/icon-source/nfc-share/render.py`: onaylanan telefon çizimi ve NFC N-Mark. Bütün üreticiler artık sıkıştırılmış ID’leri hedefler.

Ortak Graphite çizgileri, filtrelenen siyah arka planlar ve normal/seçili durumları korunur. N-Mark atfı [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt), Lucide atfı [Lucide-LICENSE.txt](../icon-source/Lucide-LICENSE.txt) içindedir.

## Print butonları, switchler ve fan görselleri

Print Tune/Pause/Resume/Stop/MMU kontrolleri normal 200–204, seçili 88–92 ID’lerini kullanır. Geniş Tune 93/94, Close 95/96; iş anahtarları 205/206 ID’lerindedir. Etiketler şeffaf yuvarlatılmış görseller üzerinde çalışma zamanında native metinle yazılır. 192–199 fan kareleri dashboard rengindeki opak arka planı ve native animasyonu korur; üretici yeni aralıkları JPEG kalitesini değiştirmeden tanır.
