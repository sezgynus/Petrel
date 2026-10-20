# Bakım kullanıcı deneyimi

Maintenance; master ile aynı Graphite başlığı, bitmap menü fontunu, ortak çizgi ikonları, ince turkuaz enkoder seçim çizgisini ve dashboard'u kullanır. Yalnızca y=360 üzeri çizilir. Onaylanan giriş ekranında dört sabit hedef vardır: Care schedule, Check printer, Diagnostics ve Recommendations (adet). Plan, cihaz veya öneri sayısı arttığında ana ekrana satır eklenmez; başka bir giriş yerinden oynamaz.

## Bakım takvimi

Sabit özet en fazla iki kayıtlı hatırlatıcı gösterir: önce zamanı gelenler, ardından bilinen en yakın takvim tarihi, sonra kullanım takibi yapılanlar. Tüm takvim ayrı, enkoderle kayan bir görünümdür; üç satır ve konum çubuğu görünür. Beş veya daha fazla plana ulaşılabilir. Add reminder ve Refresh records aynı görünümde erişilebilir kalır. İlerleme, tanımlanan bakım aralığının geçen kısmıdır; aşınma, donanım sağlığı veya kalan ömür değildir.

Maintenance açıldığında kayıtlı politikalar mevcut worker üzerinde yüklenir. Çizim ve enkoder gezinmesi disk, keşif veya ağ işi yapmaz. Yükleme test başlatmaz, bakım yapılmış saymaz. Arka plan sonucu kullanıcının açtığı başka bir ekranı değiştirmez. Depolama hatası görünür kalır; Care schedule içinde açıkça yeniden denenir. READY/yapılandırma kimliği değiştiğinde önbellek geçersizleşir.

Plan, bakım aralığı veya son bakım tarihi uydurulmaz. Hatırlatıcı kaydedildiğinde mevcut takvim zamanı veya örneklenmiş sayaçla bağımsız, kalıcı bir takip başlangıcı oluşturulur; bu işlem bakım yapılmış sayılmaz. Geçerli tamamlanma/takip başlangıcı olmayan eski planların takibi ilk uygun worker okumasında başlar; önceki ölçülmemiş saatler geriye dönük eklenmez. Doğrulanan başlangıçtan beri örneklenmiş saatler, bakım eşiği dolmasa da "recorded" kullanım olarak çubuğu doldurur. Bu miktar gerçek kullanımın alt sınırıdır, kesin kalan ömür değildir. Sayaç sıfırlanır, okuma kaybolur veya sayaç kimliği değişirse uydurma ilerleme gösterilmez ve takip duraklatılır. Kaldırılmış cihazlar dışlanır. Hatırlatıcı için desteklenen cihaz, iş, sayaç temeli ve aralık seçilir; inceleme ve kayıt ayrıca onaylanır. Gerçek bakım tamamlandığında ayrıca onaylanarak yeni bakım dönemi açılır; toplam kullanım sayacı sıfırlanmaz.

## Öngörülebilir hedefler

Check printer kabiliyetlerden üretilen işlev gruplarını ve cihaz örneklerini içerir. Isıtma bileşenleri birleşik kalır; günlük ofset, vida ve mesh işlevleri Leveling içinde tutulur. Diagnostics ana ekrandan doğrudan erişilir ve kayıtlı salt okunur bilgi akışlarını amaca göre gruplar. Kullanım/geçmiş ve destek kaydı/dışa aktarım buradadır. Recommendations güncel dikkat/sorun bulgularını cihaz bazında toplar; yenileri yalnızca adedi ve bölüm içeriğini değiştirir. Kalibrasyon mevcut ek araçlar üzerinden erişilebilir kalır.

Testi hazırlamak donanım çalıştırmaz. Controller ön kontrolü ve açık Start onayı ayrı kalır. Gözlem, sensör geçişi, dış ölçüm, F12 fiziksel tam duruşu ve iş akışı seçimlerinde controller yetkisi korunur; kullanıcı yanıtına zaman aşımı uygulanmaz. Sonuçlar ölçümü, kullanıcı gözlemini ve tamamlanamayan işlemi ayırır. İsteğe bağlı ayrıntılar kayıtlı kanıtı korur; geçmiş açıkça tarihsel olarak belirtilir. Kalibrasyon ayarları otomatik kaydedilmez.

## Çizim ve etkileşim

Back satırı master ile aynı y=31–83 alanındadır. Önceki seçim/cihaza döner; kökteki Back ana menüde Maintenance kutusunu geri seçer. Ana satırlar sabit kalırken bakım alt görünümü kayar. Eski büyük Maintenance kutuları yerine mevcut küçük Graphite ikonları yeniden kullanılır. Girişte büyük yazıcı çizimi yer kaplamaz.

Metin, çubuk ve seçim çizgisi ayrı imzalarla önbelleklenir. Değişmeyen seçimler arasında enkoder yalnızca eski/yeni ince seçim çizgisini çizer; ikon ve metni tekrar göndermez, tüm ekranı temizlemez. Görünür pencere değiştiğinde yalnızca dashboard üzerindeki içerik yenilenir. Çubuk imzası panel pikseline yuvarlanır. Eylem kimliği değişmiş ENTER yanlış hedefi çalıştırmak yerine yeniden çizer. Controller aşaması değişince güvenli ilk seçim geri gelir. Genel güç/kurtarma ve etkin işlem polling davranışı korunur.

## Referans ve kayıtlar

Tam H01 sonucundan Heating speed reference açılır. Bilinen sağlam donanım ve açık onay olmadan referans kaydedilmez. Karşılaştırma, seçilmiş inceleme sınırı ve aynı donanım/soğutma koşullarını gerektirir. Hedef, süre, ilk sıcaklık bandı, fan durumu, firmware/yapılandırma farkı ve eski kanıt geçersiz karşılaştırmayı önler. Donanım değişiminde referans açıkça silinir. Isıtıcı eskimesi veya kalan ömür tanısı konmaz.

Regresyonlar her imzalı commit için GitHub Actions'ta çalışır. Yerel test veya geliştirme emülatörü çalıştırılmaz. CI arayüz entegrasyonunu ve sınırlı çizimi doğrular; fiziksel panel kabulünün yerine geçmez.

Kanıt yokken giriş ekranı değerlendirme raporu veya controller planı üretmez. Bakım hedefleri, keşif cihaz adından farklı olabilen eksen adları dahil kayıtlı planları izler.

## Teşhis sunumu ve ortak görseller

Başarılı bilgi okumaları, ayrıca Details seçtirmeden ölçülen veriyi doğrudan açar. İç kanıt anahtarları yerine anlaşılır adlar ve tanımlı birimler gösterilir. Pi uyarı bitleri güncel/geçmiş host uyarısı olarak açıklanır; 24 V güç kaynağı tanısı sayılmaz. Sonuç/geçmiş durumları ve geri yükleme bayrakları sade metinle sunulur; kayıtlı diagnostik alanları açık etiket ve birimlerle sunulur. Uzun metin sarılır ve tam yönergeler erişilebilir kalır. Eski 156–163 kutu ikonları SVG/JPEG kaynaklarından ve paketten kaldırılır; Maintenance master ikonları 13, 45 ve 218 kullanır. Eşleşen çıktı/manifest 9 bloktur (288 KiB); önceki bakım UI paketinden bir blok küçüktür.

## Tüm alt menülerde artımlı güncelleme

Enkoder dönüşü çizilmiş modeli kullanır; ENTER eylem kimliğini göndermeden önce güncel modelle doğrular. Master listeleri gibi kaydırma native move_area kullanır; ortak satırlar korunur, yalnız yeni açılan satır çizilir. Bakım satırı, açıklama, etiket, çubuk pikselleri ve eylem penceresi ayrı imzalar tutar. Değer veya eylem adedi değişince tüm ekran geçersizleşmez. Çubuk artışı/azalışı yalnız değişen aralığı boyar.

## Anlamlı ikonlar

Küçük 20x20 Graphite ikonları 164–167; Check printer, Diagnostics, Recommendations ve Care schedule girişlerini ayırır. Master çizgi kalınlığı/uçları ve paleti, baseline 4:2:0 JPEG kaynakları, mevcut kütüphane ID’si ve değişmeyen 9 blok alanı kullanılır. Alt menü ikonları eylem, konu, test özelliği ve bakım işi sözleşmelerinden seçilir: ısıtıcı, tabla, fan, eksen/homing, prob, filament, sürücü, host, buzzer, ışık, geçmiş ve depolama ilgili mevcut ikonu kullanır. Info yalnız gerçek Details için kullanılır; bilinmeyen eyleme ve sayısal veriye Info atanmaz. Bakım/menü etiketleri LCD’nin native metnidir.

## Salt okunur raporlar

Diagnostik okumaları, sonuçlar, kanıt ayrıntıları, geçmiş kanıtlar, öneriler ve tam yönergeler ortak, sürekli enkoder kaydırmalı raporu kullanır. Back/durum/başlık sabittir; iki sütunlu ölçümler ve açıklamalar sekiz satırlık pencerede 24 piksellik bantlarla kayar. Küçük kaydırmada Info ile aynı DWIN alan taşıma komutu korunacak pikselleri kopyalar; yalnız açılan/değişen hücreler çizilir. Büyük atlama ve başa dönüş yalnız içerik penceresini yeniler; başlık/dashboard çizilmez. İki yönde döngüsel kaydırılır; gerçek işlemler bilgiden sonra gelir ve odaklandığında görünür kalır. Ölçümler seçilebilir işlem değildir. Satır sarımı içerik değişene kadar önbelleklidir; çıkarken bırakılır. CI ileri/geri/başa dönüşü, işlem odağını, değer güncellemesini ve rapor kısalmasını temiz framebuffer ile karşılaştırır. Örnek görseller fiziksel test kanıtı değildir.

## Diagnostik alan kapsamı

Kayıtlı her bilgi okuyucusunun artık adlandırılmış LCD raporu ve açık alan sunumu vardır. Sürücü register yanıtları anlaşılır uyarı, duruş, sürüş modu ve akım ölçeği değerlerini gösterir; bilinmeyen çip düzenlerinde register değeri korunur, temiz durum uydurulmaz. Motor etkinliği/akımı, home edilmiş eksenler/komut koordinatları, carriage modları, çevresel okumalar, MCU zamanlaması, CAN sayaçları, UART/enkoder sayaçları, panel kaynakları, kayıtlı geçmiş, örneklenmiş kullanım ve bileşen bazında güncelleme bilgileri LCD'de gösterilir. Sıfır sayaçlar ve false durumlar da sunulur. Önceki genel destek raporuna yönlendirme mesajı kaldırılmıştır.

MCU ortalama/değişkenlik değerleri saniyeden mikrosaniyeye çevrilir; yapılandırılmış sürücü akımları amperdir. Klipper BME çevresel basıncı hPa, gaz direnci ohm birimindedir. Kayıtlı kullanım süreleri okunabilir zaman aralıklarıdır; örneklenmiş kapsam açıkça alt sınır olarak belirtilir. Eksik veya geçersiz okuma yerine değer uydurulmaz. İç olay zamanları ve bilinmeyen backend kayıt alanları ölçüm olarak sunulmaz. CI her kayıtlı okuyucuyu, gerçek TMC/MCU/hareket ayrıştırıcılarını ve yerel panel/kullanım/geçmiş çıktı sözleşmelerini kapsar.

Bakım kayıtları Maintenance menüsüne her girişte ve bakım görünümü boşta ve görünürken en fazla dakikada bir asenkron yenilenir. Yenileme sırasında mevcut plan görünür kalır; örneklenmiş saatlere bağlı vade durumu ve açık hatırlatıcı, tamamlanan worker sonucuyla güncellenir.

Komponente özgü hatırlatıcı seçenekleri, desteklenen telemetri ve kapasite durumları [Komponent kullanım takibi](maintenance-usage_TR.md) belgesindedir.

Kayıtlı hatırlatıcıyı kaldırmak için **Care schedule** içinde açın, **Remove reminder** seçin ve ayrı **Remove reminder?** ekranında onaylayın. İlk seçili eylem **Keep reminder** olur. Silme mevcut worker üzerinde çalışır ve yenilenmiş takvime döner. Kayıtlı politika ve ona ait aktif takip başlangıcı kaldırılarak iki kayıt alanı da serbest bırakılır; kullanım sayaçları ve tamamlanan bakım geçmişi korunur. Onay ekranı açıldıktan sonra düzenlenen hatırlatıcı eski onayla silinemez.
