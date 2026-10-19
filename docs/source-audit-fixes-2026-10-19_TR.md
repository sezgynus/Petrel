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
| R02 | Worker üzerinde yeniden sıralama | Bekliyor |
| R03 | Dosya cache ömrü | Bekliyor |
| R04 | Tek bakım tick’i ve interval | Bekliyor |
| R05 | Kullanım sayacı kapasitesi | Bekliyor |
| R06 | Kabul edilmiş sonuç kayıtlarını boşaltma | Bekliyor |
| R07 | Güvenli thumbnail deneme bütçesi | Uygulandı |
