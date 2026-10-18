# Bakım değerlendirmesi

Yalnız backend geliştirmesi; nihai UI ayrı dalda yapılır. Immutable ölçüm, kanıt ve bulgular gözlem ile teşhisi ayırır. Baseline karşılaştırması aynı cihaz, yöntem, yapılandırma ve açık test koşullarını gerektirir. Koşulları bulunmayan eski sonuçlar performans trendi oluşturamaz. Otomatik donanım eylemi veya yapılandırma kaydı yoktur.

Kayıtlı planlar güncel kabiliyetlerle kesiştirilip konu/cihaz bazında gruplanır. H01 yedi termal sonuç sağlar. Bulgular kullanıcı doğrulamasını korur; tamamlanamayan kontrolü başarısız ölçütten ayırır. Yalnız mevcut PID adaptörü önerilebilir; otomatik teşhis veya komut gönderimi yoktur.

Açıkça seçilen baseline ve onaylanan bakım kayıtları sınırlı, atomik, sürümlü depoda saklanır. Parça değişimi baseline kayıtlarını geçersiz kılar. Bakım aralığı kaynak gerektirir; varsayılan süre uydurulmaz. Sayaç sıfırlanması veya kimlik değişimi bilinmeyen sonuç üretir. Örneklenmiş açık kalma süresinin aralığın altında olması bakım gerekmediğini kanıtlamaz.

Petrel tamamlanan sonuçları sınırlı epoch/config kapsamlı değerlendirme önbelleğine alır. maintenance_assessment_report() istek üzerine çalışan backend API'sidir ve test başlatmaz. Termal sonuçlar işlem kimliği, hedef, süre ve başlangıç sıcaklığını taşır; bilinmeyen fan/ortam/donanım koşulları uydurulmaz, bu nedenle kayıtlar tek başına karşılaştırılabilir baseline değildir. Geçmiş koşulları ve geri yüklemeyi ayrı saklar.

Firmware bulguları aktif throttling ile geçmiş bayrakları, Klipper durumunu ve desteklenen sürücü hatalarını ayırır. Sayısal politikalar açık kaynak/sürüm ve sonlu sınırlar gerektirir. Trend karşılaştırması gösterge niteliğindedir; arızalı parçayı teşhis etmez. Eksik kanıt kuralı sağlamaz.
