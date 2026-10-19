# Kaynak audit düzeltmeleri

[English](source-audit-fixes-2026-10-19.md) · [Türkçe](source-audit-fixes-2026-10-19_TR.md)

Branch: `fix/source-audit-2026-10-19`. Taban: `bc5e395`. Donanım kabulü bekleniyor; master değişmedi. Regresyon kontrolleri yalnız GitHub Actions üzerinde çalışır.

| ID | Madde | Uygulama |
| --- | --- | --- |
| K01 | Katmanlar ve UART kaybında bakım ilerlemesi | Uygulandı |
| K02 | Taşıma kapanmadan acil durdurmayı gözleme | Uygulandı |
| K03 | İsteğe bağlı fan/ısıtıcı sayaç kapsamı | Uygulandı |
| K04 | Düzenli kapanışta kullanım kaydı | Uygulandı |
| K05 | Küçük input/read/buzzer snapshot’ları | Uygulandı |
| K06 | Büyük dosya listelerini UI dışında hazırlama | Uygulandı |
| K07 | Hedefli baskı metadata geçersizleştirme | Uygulandı |
| K08 | Remote bağlantı ve okuma süre sınırları | Uygulandı |
| K09 | Kooperatif worker kapanışı ve update yalıtımı | Uygulandı |
| K10 | Animasyona duyarlı ortak remote JPEG cache’i | Uygulandı |
| K11 | Kısmi recovery çizimi | Uygulandı |
| K12 | Negatif thumbnail cache’i | Uygulandı |
| K13 | Alternatif thumbnail adayları | Uygulandı |
| K14 | Tek istemci sürüm kaynağı | Uygulandı |
| K15 | Remote Enter kısayolu | Uygulandı |

## Donanım kabulü

15 maddenin tamamı bu branch üzerinde uygulandı. Donanım kabulü bekleniyor; otomatik merge istenmiyor. Her mantıksal değişiklik, imzalı HEAD üzerinde tam branch regresyon workflow'u ile kontrol edilir. Yerel test veya geliştirme emülatörü çalıştırılmadı.

1. Yazıcı boşta yapılan bir Maintenance testi sırasında basılı tutup bırakma güç penceresini açıp iptal et. Kontrol ilerlemeli ve pencere kapandığında sonuç görünmeli. Servis durdurma/başlatma ve LCD yeniden bağlantısını kontrollü koşullarda doğrula.
2. Gözlenen kullanımın arttığını ve normal Petrel restart'ından sonra korunduğunu doğrula. Telemetrisi olmayan cihazlara uydurma sıfır sayaç veya açık kalma saatine dayalı hatırlatma seçeneği eklenmemeli.
3. Büyük ve iç içe dosya ağacında gezinip sıralamayı değiştir. Thumbnail, geri gezinme, preview onayı, silinen dosyalar ve baskı başlatma doğrulamasını kontrol et.
4. Baskı sırasında başka bir G-code yükle. Remaining/Finish mevcut metadata kaynağını korumalı. Asıl dosyanın değiştirilmesi veya yeniden bağlantı doğru metadatayı yine yenilemeli.
5. İki remote izleyici açıkken enkoder kontrollerini, klavye Enter'ını, sabit kareyi ve fan animasyonunu kontrol et. Odaktaki butonların normal Enter davranışı korunmalı.
6. Recovery ekranında butonlar arasında gezin ve uzun mesajı kaydır. Yalnız değişen buton/metin çizilmeli; kısalan mesaj ve silinen bildirim kalıntı bırakmamalı.
7. Thumbnail olmayan, ilk thumbnail adayı bozuk olan ve geçici indirme hatası veren dosyaları aç. Eksik görsel sürekli sorgulanmamalı; alternatif adaylar ve geçici hata tekrarları çalışmalı.

İstemci kimliği artık kurulu checkout'un önbelleğe alınmış `git describe --tags --always --dirty` değerini kullanır. Git metadatası okunamıyorsa `unknown` bildirir; sürüm etiketi uydurmaz. Gönderilmiş bir yazılım güncellemesi UI kapatılarak geri alınamaz; kapanış sonraki istekleri engeller ve mevcut istek döndüğünde özel taşıma kaynağını serbest bırakır.

## İkinci audit

| ID | Madde | Uygulama |
| --- | --- | --- |
| R01 | Foreground preview kimliği | Uygulandı |
| R02 | Worker üzerinde yeniden sıralama | Uygulandı |
| R03 | Dosya cache ömrü | Uygulandı |
| R04 | Tek bakım tick’i ve interval | Uygulandı |
| R05 | Kullanım sayacı kapasitesi | Uygulandı |
| R06 | Kabul edilmiş sonuç kayıtlarını boşaltma | Uygulandı |
| R07 | Güvenli thumbnail deneme bütçesi | Uygulandı |

### İkinci audit doğrulaması ve davranış

- İlk beş ön yükleme girdisi dışındaki soğuk preview hemen geçerlidir; gerçek dosyanın değiştirilmesi veya silinmesi yine onu geçersizleştirir. Güvensiz görsel yolları dört indirmelik deneme bütçesini tüketmez.
- Sıralama tercihi değişikliği, özel liste ve yolları read worker üzerinde hazırlar. Yayın için kaynak liste, epoch, dosya revizyonu ve sıralama revizyonu aynı kalmalıdır. Disconnect/epoch değişiminde backend indeksleri ve UI alias’ları birlikte bırakılır; başlamış bir iş, bitene kadar kendi girdilerini tutabilir.
- Bir UI tick’i tek model güncellemesini paylaşır. Aktif Maintenance, daha hızlı çizim işini yavaşlatmadan nihai aralığı en fazla 100 ms tutar; tick dışındaki giriş olayları hâlâ güncel durumu ister. Hold, popup ve UART kaybı yollarında kontroller ilerler.
- Yeni kullanım kayıtları en fazla 32 adlandırılmış sayaç kabul eder. Dolu kayıt mevcut değerleri ve kimliğini korur, baskı süresi/mevcut sayaç güncellemelerini sürdürür; yeni adların reddini kayıt hataları ve journal üzerinden bildirir. En fazla 64 ad içeren eski taşmış kayıt grupları okunabilir kalır ve mevcut sayaçlarını korur; daha fazla büyüyemez. Sayaçlar sessizce silinmez veya sıfırlanmaz.
- Düzenli kapanış, worker kapanırken kuyruktaki Future’ları iptal edilmiş olsa bile kabul edilmiş en fazla sekiz yerel sonuç grubunu tamamlar. Başlamış yerel yazı transaction kilidi üzerinden beklenir; başarılı veya hatalı denemeden sonra tekrar denenmez. Disk hatası açık kayıt hatası/journal uyarısı olarak kalır. Yazıcı komutu yeniden oynatılmaz.

Donanım kabulü bekleniyor. Önceki listeye ek olarak daha önce açılmamış altıncı/sonraki dosyayı, gezinirken sıralama değişimini ve kontrol sonucu hemen ardından normal restart’ı dene. Bu değişiklikler için master merge yetkisi yoktur.

## Üçüncü audit

| ID | Madde | Uygulama |
| --- | --- | --- |
| A01 | Sonuç geçmişi byte bütçesi | Uygulandı |
| A02 | Kabul edilmiş yerel yazılarda süre aşımı | Uygulandı |
| A03 | Durağan preview tick aralığı | Bekliyor |
| A04 | Hata beklemesinde dosya snapshot’ı | Bekliyor |

Sonuç geçmişi en fazla 64 girdi ve 64 KiB tutar; en eski girdiler çıkarılırken en yeni sonuç grubu bütün olarak korunur. Tek başına sığmayan grup kayıt hatasıyla reddedilir; önceki dosya korunur. Kabul edilmiş yerel sonuç yazıları mevcut sınırlı worker kuyruğunda kabul süresi aşımı olmadan bekler. Ağ okumaları süre sınırlarını korur, dolu kuyruk reddi açıkça bildirilir ve düzenli kapanış iptal edilen yerel yazıları hâlâ yalnız bir kez tamamlar. Normal UI tick’lerine disk işi taşınmaz ve yazıcı komutu yeniden oynatılmaz. Regresyon kapsamı geniş sonuçları, grup bütünlüğünü, sonraki yazıları, kuyruk yaşlanmasını ve ağ okuması süre aşımının korunmasını içerir. Donanım kabulü bekleniyor.
