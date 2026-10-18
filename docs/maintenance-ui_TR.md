# Bakım kullanıcı deneyimi

Maintenance; master ile aynı Graphite başlığı, bitmap menü fontunu, ortak çizgi ikonları, ince turkuaz enkoder seçim çizgisini ve dashboard'u kullanır. Yalnızca y=360 üzeri çizilir. Onaylanan giriş ekranında dört sabit hedef vardır: Care schedule, Check printer, Diagnostics ve Recommendations (adet). Plan, cihaz veya öneri sayısı arttığında ana ekrana satır eklenmez; başka bir giriş yerinden oynamaz.

## Bakım takvimi

Sabit özet en fazla iki kayıtlı hatırlatıcı gösterir: önce zamanı gelenler, ardından bilinen en yakın takvim tarihi, sonra kapsamı bilinmeyenler. Tüm takvim ayrı, enkoderle kayan bir görünümdür; üç satır ve konum çubuğu görünür. Beş veya daha fazla plana ulaşılabilir. Add reminder ve Refresh records aynı görünümde erişilebilir kalır. İlerleme, tanımlanan bakım aralığının geçen kısmıdır; aşınma, donanım sağlığı veya kalan ömür değildir.

Maintenance açıldığında kayıtlı politikalar mevcut worker üzerinde yüklenir. Çizim ve enkoder gezinmesi disk, keşif veya ağ işi yapmaz. Yükleme test başlatmaz, bakım yapılmış saymaz. Arka plan sonucu kullanıcının açtığı başka bir ekranı değiştirmez. Depolama hatası görünür kalır; Care schedule içinde açıkça yeniden denenir. READY/yapılandırma kimliği değiştiğinde önbellek geçersizleşir.

Plan, bakım aralığı veya son bakım tarihi uydurulmaz. Eksik veya gelecekteki takvim tarihi için çubuk doldurulmaz. Örneklenen sayaç aralığın dolduğunu kanıtlayabilir; sınır altındayken kesin kalan süreyi kanıtlayamaz. Kaldırılmış cihazlar dışlanır. Hatırlatıcı için desteklenen cihaz, iş, sayaç temeli ve aralık seçilir; inceleme ve kayıt ayrıca onaylanır. Gerçek bakımın tamamlanması ayrı bir onaydır. Ancak bundan sonra bakım tarihi/sayaç başlangıcı yazılır.

## Öngörülebilir hedefler

Check printer kabiliyetlerden üretilen işlev gruplarını ve cihaz örneklerini içerir. Isıtma bileşenleri birleşik kalır; günlük ofset, vida ve mesh işlevleri Leveling içinde tutulur. Diagnostics ana ekrandan doğrudan erişilir ve kayıtlı salt okunur bilgi akışlarını amaca göre gruplar. Kullanım/geçmiş ve destek kaydı/dışa aktarım buradadır. Recommendations güncel dikkat/sorun bulgularını cihaz bazında toplar; yenileri yalnızca adedi ve bölüm içeriğini değiştirir. Kalibrasyon mevcut ek araçlar üzerinden erişilebilir kalır.

Testi hazırlamak donanım çalıştırmaz. Controller ön kontrolü ve açık Start onayı ayrı kalır. Gözlem, sensör geçişi, dış ölçüm, F12 fiziksel tam duruşu ve iş akışı seçimlerinde controller yetkisi korunur; kullanıcı yanıtına zaman aşımı uygulanmaz. Sonuçlar ölçümü, kullanıcı gözlemini ve tamamlanamayan işlemi ayırır. İsteğe bağlı ayrıntılar kayıtlı kanıtı korur; geçmiş açıkça tarihsel olarak belirtilir. Kalibrasyon ayarları otomatik kaydedilmez.

## Çizim ve etkileşim

Back satırı master ile aynı y=31–83 alanındadır. Önceki seçim/cihaza döner; kökteki Back ana menüde Maintenance kutusunu geri seçer. Ana satırlar sabit kalırken bakım alt görünümü kayar. Eski büyük Maintenance kutuları yerine mevcut küçük Graphite ikonları yeniden kullanılır. Girişte büyük yazıcı çizimi yer kaplamaz.

Metin, çubuk ve seçim çizgisi ayrı imzalarla önbelleklenir. Değişmeyen seçimler arasında enkoder yalnızca eski/yeni ince seçim çizgisini çizer; ikon ve metni tekrar göndermez, tüm ekranı temizlemez. Görünür pencere değiştiğinde yalnızca dashboard üzerindeki içerik yenilenir. Çubuk imzası panel pikseline yuvarlanır. Eylem kimliği değişmiş ENTER yanlış hedefi çalıştırmak yerine yeniden çizer. Controller aşaması değişince güvenli ilk seçim geri gelir. Genel güç/kurtarma ve etkin işlem polling davranışı korunur.

## Referans ve kayıtlar

Tam H01 sonucundan Heating speed reference açılır. Bilinen sağlam donanım ve açık onay olmadan referans kaydedilmez. Karşılaştırma, seçilmiş inceleme sınırı ve aynı donanım/soğutma koşullarını gerektirir. Hedef, süre, ilk sıcaklık bandı, fan durumu, firmware/yapılandırma farkı ve eski kanıt geçersiz karşılaştırmayı önler. Donanım değişiminde referans açıkça silinir. Isıtıcı eskimesi veya kalan ömür tanısı konmaz.

Regresyonlar her imzalı commit için GitHub Actions'ta çalışır. Yerel test veya geliştirme emülatörü çalıştırılmaz. CI arayüz entegrasyonunu ve sınırlı çizimi doğrular; fiziksel panel kabulünün yerine geçmez.
