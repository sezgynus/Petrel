# Yönetilen LCD ikonları

[English](README.md) · [Türkçe](README_TR.md)

Kütüphanede **200 ikon, 0–199 ID’leri** bulunur. **200–255 boştur**; sonraki ikonu **200** ID’siyle ekleyip sırayla devam edin. Dosya adları sıfır dolgulu olmalıdır (`200.jpg`, `assets/icon-source/200.svg`). UI ve üretim araçlarını `lcd_resources.py` sabitlerine bağlayın. [İlk ID taşıma haritası](id-migration.json) ilk geçişi kaydeder. Sonraki [eksen tekilleştirme haritası](id-deduplication.json), 212 ID’li dizini ara 209 ID’li dizine taşır; 42→31, 43→32 ve 44→33 ortak kullanımlarını içerir. Ardından [native onay taşıması](id-native-confirm.json), eski 49 numaralı yazılı butonla birlikte 16–23 aralığındaki kullanılmayan sekiz Print ikonunu kaldırır; dokuz boşluğu tek nihai haritada kapatır. Bunlar inceleme kayıtlarıdır; çalışma zamanında ID çevirisi yapılmaz.

Temizlikte **40 kullanılmayan ikon** (44.535 JPEG baytı) kaldırıldı. Eski 203 ID’sinin Bed Mesh menüsünde kullanıldığı bulundu; `ICON_BED_MESH` (153) olarak korundu. Kalan JPEG ve düzenlenebilir SVG’nin baytları, boyutları, renkleri ve kalitesi değiştirilmeden taşındı. ID’ler ardışıktır; fiziksel yerleşim ID sırasından bağımsızdır.

Dashboard ve Move menüsü artık X/Y/Z için **23/24/25** ID’lerini ortak kullanır. Bayt düzeyinde aynı üç kopya kaldırılarak **2.868 bayt** ve üç ID kazanıldı. **200** ile başlayan **56 boş ID** vardır.

## Kaynaklar ve paketleme

Bu dizine baseline **4:2:0 JPEG** ekleyin. ID’ler benzersiz ve 0–255 aralığında olmalıdır. Progressive JPEG, diğer renk örneklemeleri, geçersiz dosya adları ve 32767 bayttan büyük yükler reddedilir. Görselleri yeniden üretme aracı açıkça çalıştırılmadıkça mevcut JPEG’ler korunur.

Picture Flash **0** açılış görseline, **1** ortak QR/UI görseline, **2–15** ise **2** numaralı ikon kütüphanesine ayrılmıştır. Güncel çıktı **12×32 KiB**, yani **2–13** slotlarını kullanır. Bu bloklarda **5.379 kullanılabilir bayt boşluk** vardır; **14/15** numaralı slotlar da kullanılabilir. Ayrılmış alanın toplam kullanılabilir boşluğu **70.913 bayttır**. Yeni kaynaklarla bu değerler değişir. ID silinince 4096 baytlık dizin küçülmez.

Çalışma zamanı ve dışa aktarma aracı aynı deterministik paketleyiciyi kullanır: best-fit decreasing ardından önceki boşlukları birleştiren sınırlı subset-sum aramaları. Daha büyük boşluk için fazladan blok tüketilmez. Her blok araması kesindir; sıralı aramalar tüm paket için küresel optimum kanıtı değildir. Her bloğun son baytı ayrılmıştır; JPEG blok sınırını aşmaz. Paketleme adresleri değiştirir; JPEG baytlarını ve ID’leri değiştirmez. Önbellek, değişmeyen kaynakları her bağlantıda yeniden paketlemeyi önler.

```sh
python tools/pack_icon_library.py assets/icons /tmp/2.ICO --library 2
```

`assets/emulator/2.ICO` repodaki referans çıktıdır. Üretim sistemi paketi JPEG kaynaklarından otomatik oluşturur; emülatör aynı kaynakları kullanır. Varlıklar değişince çıktıyı ve `docs/lcd-assets.json` dosyasını güncelleyin.

## Otomatik güncelleme ve ID taşıması

İlk LCD bağlantısında kütüphane eşitlenir. **PETICO05** metadata sürümü sıkıştırılmış ID’leri eski dizinden ayırır. PETICO01/PETICO02/PETICO03/PETICO04 kaydıyla yeni ID’lerde açılış animasyonu başlatılmaz; ilk geçişte animasyon yeni dizin tamamlandıktan sonra başlar. Picture Flash yazılmadan tüm native animasyonlar durur. Önce yük blokları, en son dizin yazılır; CRC doğrulamalı kontrol noktaları yarım yüklemeyi sürdürür. Sonraki değişmeyen bağlantılarda Flash yazılmaz. Başarısız otomatik Picture Flash denemesi aynı süreçte tekrarlanmaz.

0/1 slotları, ekran/ses ayarları, NFC UID’leri ve Spoolman kayıtları taşınmaz. LCD SD güncellemesi gerekmez. Eski 3/7 kütüphane tabanlarının kayıtları yönetilen 2 tabanında kullanılmaz. Eski yazılıma dönüldüğünde o yazılım kendi kaynaklarından kendi dizinini yeniden oluşturur.

Elle tanılama yüklemesinden önce Petrel’i durdurun. `tools/reload_icons.py` güncel kaynakları kontrol noktalı olarak zorla eşitler. `tools/flash_icon_library.py` varsayılan olarak güncel kaynakları; açık `--file` seçeneğiyle belirtilen ICO’yu yükler. Tanılama yüklemesi eski metadata’yı geçersiz kılar; sonraki normal açılış yönetilen kaynakları geri getirir. [LCD görselleri](../README_TR.md) kılavuzuna bakın.

## Güncel kaynaklar

| Amaç | ID’ler | Boyut / davranış |
|---|---|---|
| Dashboard hotend / tabla | 9 / 10 | 18×18; kullanılmayan eski 20×20 ayar sürümleri kaldırıldı |
| MMU normal / seçili | 108 / 109 | 110×100 |
| Ekran normal / seçili | 59 / 60 | 110×100 |
| Klasör; MCU; makine; sunucu; yazılım; güç | 110; 111; 112; 113; 57; 58 | Klasör 20×18, diğerleri 20×20 |
| Makara flanşları / boş makara | 61–74 / 75 | 1–7 genişlik, 52 yükseklik / 42×52 |
| Bakım kontrol / tanılama / öneri / servis | 114–117 | 20×20 |
| Wi-Fi zayıf / orta / güçlü | 118–120 | 20×20, filtrelenen koyu arka plan |
| NFC ayarları; arayüz; port | 121; 106; 107 | 20×20 |
| RFID ana menü normal / seçili | 122 / 123 | 110×100 |
| Telefon yaklaştırma | 124–135 | 12 opak 160×160 kare, kanal 2, 200 ms/kare |
| Küçük NFC paylaşım normal / seçili | 136 / 137 | 20×20 kontrol, 16×16 sembol |
| Makara yaklaştırma | 138–149 | 12 opak 160×160 kare, kanal 3, 200 ms/kare |
| Acil durum; makara; ata; kaldır; ileri; yeniden dene | 27; 36; 37; 38; 39; 40 | Ortak 20×20 amaç ikonları |
| Kart yaklaştırma | 45–56 | 12 opak 160×160 kare, kanal 3, 200 ms/kare |
| Bed Mesh menüsü | 153 | `ICON_BED_MESH` sabiti |
| Fan; açılış | 180–187; 195–199 | Native animasyon kanalları 1 / 0 |

Telefon paylaşımı sunucuda kare zamanlayıcısı olmadan 2,4 saniyede döner. Okuma, hata, iptal ve pencere değişimi animasyonu durdurur. Yetenek keşfi Software bölümündeki Petrel sürümünden önceki küçük NFC kontrolünün görünürlüğünü belirler; QR altında ek paylaşım satırı yoktur. Paylaşım hatasında ilk kare sabit gösterilir.

Makara ve genel kart ataması ortak yakalama popup’ını kullanır. Emergency Assign/Replace kart karelerini, makara ataması makara karelerini kullanır. Tıklama iptal eder; okuma, açık UID/kayıt onayından önce animasyonu durdurur. Yalnız okuma Spoolman ataması yazmaz. Güç pencereleri, bağlantı kapanması ve ekran değişimi animasyonu durdurur/temizler; bekleyen yakalama kaynak ekrana dönüldüğünde sürer veya tamamlanır. Yeniden çizim ve enkoder hareketi yakalamayı baştan başlatmaz.

## Görsel üretimi

- `python tools/render_icon_sources.py --ids 136 137` seçilen SVG ID’lerini üretir; `--ids` olmadan yalnız bilinçli tam yeniden üretim yapın. Fiziksel panel baseline 4:2:0 ister; 4:4:4 daha önce görselleri bozdu.
- `python tools/render_button_backings.py` güncel buton zemini ID’lerini kullanır.
- `python assets/icon-source/nfc-settings/render.py` ve `python assets/icon-source/rfid/render.py` güncel amaç ikonlarını ve SVG’lerini üretir.
- `python assets/icon-source/nfc-card/render.py`: kalite 65, optimize Huffman tabloları, baseline 4:2:0.
- `python assets/icon-source/nfc-spool/render.py`: özgün kayıpsız PNG’ler, kalite 84, optimize Huffman tabloları, baseline 4:2:0.
- `python assets/icon-source/nfc-share/render.py`: onaylanan telefon çizimi ve NFC N-Mark. Bütün üreticiler artık sıkıştırılmış ID’leri hedefler.

Ortak Graphite çizgileri, filtrelenen siyah arka planlar ve normal/seçili durumları korunur. N-Mark atfı [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt), Lucide atfı [Lucide-LICENSE.txt](../icon-source/Lucide-LICENSE.txt) içindedir.

## Print butonları, switchler ve fan görselleri

Print Tune/Pause/Resume/Stop/MMU kontrolleri normal 188–192, seçili 76–80 ID’lerini kullanır. Geniş Tune 81/82, Close 83/84; iş anahtarları 193/194 ID’lerindedir. Etiketler şeffaf yuvarlatılmış görseller üzerinde çalışma zamanında native metinle yazılır. 180–187 fan kareleri dashboard rengindeki opak arka planı ve native animasyonu korur; üretici yeni aralıkları JPEG kalitesini değiştirmeden tanır.

## Native onay etiketleri

Soğuk ekstrüzyon uyarısı mevcut 104×36 yazısız seçili buton zeminini (`ICON_STOP_BUTTON_SELECTED`) (84, 280) konumunda ortalı kullanır. `Confirm` etiketi (108, 290) konumunda native 8×16 metinle, cyan üzerine koyu renkte yazılır. JPEG içinde kelime bulunmaz. Eski 49 numaralı yazılı JPEG/SVG ve `ICON_Confirm_E` sabiti kaldırıldı; kalan ID’ler sıkıştırıldı ve görsellerin baytları korundu. Onay, ekstrüzyon komutu göndermeden Move ekranına döner. Yeni bir çeviri altyapısı eklenmez; etiketler ileride yerelleştirilebilecek çalışma zamanı metni olarak tutulur.

## Kaldırılan eski Print kontrolleri

Eski 16–23 ID’leri (Tune, Pause, Continue ve Stop; normal/seçili) yalnız çağrılmayan eski çizim yardımcılarında referanslıydı. Sekiz JPEG/SVG çifti, sabitleri ve beş eski yardımcı kaldırıldı. Eski yardımcıyı doğrudan çağıran regresyon testi artık etkin `_focus_draw_buttons` yolundaki native Resume metnini doğrular. Eski onay görseliyle birlikte bu güncellemede toplam **22.697 JPEG baytı** tutan dokuz kaynak kaldırıldı. Ayrılmış Picture Flash aralığı 2–15 olarak kalır; daha az dolu blok, yeni kaynaklar için daha fazla alan bırakır.
