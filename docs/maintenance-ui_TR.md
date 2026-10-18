# Bakım kullanıcı deneyimi

Nihai UI feature/maintenance-ui-ux dalında geçici test UI'sından bağımsız geliştirilir. Saf deneyim modeli kayıtlı capability'leri amaç ve cihaz bazında gruplar; keşif veya donanım eylemi yapmaz. Birleşik termal kontrol yedi ayrı girişin yerini alır. Leveling offset, mesh ve vida akışları kopyalanmaz. Kalibrasyon işlev kontrollerinden ayrılır. Özetler ölçüm başarısızlığı, kullanıcı gözlemi, bilgi ve tamamlanamayan yürütmeyi ayırır. Sayısal kanıt ve geri yükleme bilgisi isteğe bağlı ayrıntıda kalır.

## Enkoder etkileşimi

Maintenance dört Graphite kutucuk açar: Check printer, Findings, Service plan ve More. Gruplar ve cihaz örnekleri kayıtlı controller planlarından gelir. Hazırlık donanımı sürmez; controller preflight ardından ayrı Start onayı vardır. Kullanıcı gözlemi, sensör geçişleri, harici ölçüm, F12 tam duruş ve workflow adımları açık seçimlerle ilerler. Back aynı cihaza döner. Bilgi okumaları istek üzerinedir. Recovery ekranı Maintenance'ı örttüğünde aktif işlemler poll edilmeye devam eder. Güvenlik durdurma metinleri ısıtıcı shutdown ile normal gezinmeyi ayırır.

Normal durum şeridi korunur. Kök kutucuklar yönetilen metinsiz 156–163 ikonlarını kullanır; alt ekranlar sınırlı kısmi çizilir. Sayısal kanıt isteğe bağlı kaydırılan Details ekranındadır. Destek kaydı ana ekranda değil More altındadır. Lokal test/emülatör gerekmez; yeni gezinmeyi Actions regresyon paketi doğrular.

## Bakım hatırlatıcıları ve geçmiş

Bakım kayıtları yalnız açık istekle yüklenir ve mevcut worker üzerinde işlenir. Hatırlatıcı eklerken desteklenen cihaz, görev ve temel seçilir: takvim günü, örneklenmiş baskı saati veya desteklenen bileşenlerde örneklenmiş açık kalma saati. Aralık kullanıcı tarafından belirlenir. Editörün ilk değeri kurulu politika değildir; kayıt inceleme ve açık onay gerektirir. Hatırlatıcı kaydı bakım yapıldığı anlamına gelmez. Gerçek tamamlanma ayrıca onaylanır. Son bakım tarihi yoksa bilinmeyen kalır. Kaldırılan cihazlar gizlenir ve yeni tamamlanma kaydı alamaz. Aşınma veya kalan ömür tahmini çıkarılmaz.

Son kontrol geçmişi ayrıca yüklenir ve tarihsel olarak işaretlenir. Baskı kullanımı, örneklenmiş kullanım ve ayıklanmış rapor aktarımı istek üzerine bilgi okumalarıdır. Kullanıcı tek termal kontrol çalıştırsa da Findings bağımsız termal alt sonuçları içerir. Maintenance girişinde çizim önbelleği geçersiz kılınır; diğer ekranlardan kalıntı kalmaz.

## Son etkileşim korumaları

Eylemler değişmişse yakalanan ENTER komut göndermek yerine ekranı yeniler. Controller faz değişimi odağı güvenli ilk eyleme döndürür. Uzun controller talimatları ayrı kaydırılan sayfadan okunur. Aynı cihazın bulguları gruplanır; açıklamalar korunur. Çizimler normal durum şeridinin üstünde kalır ve değişmeyen ekranlar yeni çizim paketi üretmez. Fiziksel backend'ler yetkili kalır; CI UI entegrasyonunu doğrular, yeni ekran düzeninin fiziksel kabulü değildir.

İptal edilen global güç penceresi dönüşünde Maintenance yüzeyi yeniden çizilir; kontrol tekrarlanmaz. Harici ölçüm hazırlığında ölçü aleti ve açık hareket yolu özellikle belirtilir.


## Ölçülen ısınma hızı referansı

Koşulları eksiksiz H01 sonucunda Heating speed reference açılır. Kullanıcı çalışan donanımla yapılan H05 ölçümünü ayrı onayla referans kaydeder. Compare ekranında yüzde değişim sınırını seçip aynı heater/nozzle ve soğutma kurulumunu doğrular. Hedef, süre, 5 °C başlangıç bandı, fan başlangıç durumu, firmware veya config uyuşmazsa karşılaştırma yapılmaz. Eski veya eksik koşullu kayıt referans yapılmaz. Donanım değiştiğinde eski referans açık onayla kaldırılır. Sonuç, ölçülen değişimi ve kontrol edilecek koşulları açıklar; heater cartridge arızası veya kalan ömür teşhisi koymaz. Sayılar isteğe bağlı ayrıntıda kalır.

## Güncel kayıtlar ve kullanım kapsamı

Takvim vadesi görünüm üretilirken güncel zamandan hesaplanır. Discovery değişikliği kayıt görünümünü geçersiz kılar; Refresh records mevcut worker üzerinde yeniler. Örneklenmiş sayaçlar yalnız gözlenen kesintisiz kısa aralıkları toplar ve alt sınırdır. Yeni hatırlatıcı bakım yapılmış sayılmaz; gerçek bakım sonrası tamamlandı onayı o andaki sayaç başlangıcını kaydeder. Sayaç kimliği değişirse önceki başlangıçla kıyas yapılmaz. Kullanım eşiğinin altında kalmak bakım gerekmediğini kanıtlamaz. Yüklenmiş kayıtlarda vadesi gelen hatırlatıcılar kök ekranda da belirtilir. Kayıt kuyruğu/disk hataları ekranda uyarılır.

Moonraker geçmiş toplamları kesin ömür veya sıfırlanmayacağı kanıtlanmış bakım sayacı olarak varsayılmaz. Doğrulanmış sürekliliği olmayan hareket mesafesi bakım ölçütüne dönüştürülmez. Bu kaynaklar bilgi ekranında kalır; mevcut fiziksel kabul yeni UI düzeninin kabulü sayılmaz.
