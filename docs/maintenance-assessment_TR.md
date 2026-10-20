# Bakım değerlendirmesi

Değerlendirme backend’i nihai UI’dan bağımsızdır; UI mevcut API üzerinden bağlanır. Immutable ölçüm, kanıt ve bulgular gözlem ile teşhisi ayırır. Baseline karşılaştırması aynı cihaz, yöntem, yapılandırma ve açık test koşullarını gerektirir. Koşulları bulunmayan eski sonuçlar performans trendi oluşturamaz. Otomatik donanım eylemi veya yapılandırma kaydı yoktur.

Kayıtlı planlar güncel kabiliyetlerle kesiştirilip konu/cihaz bazında gruplanır. H01 yedi termal sonuç sağlar. Bulgular kullanıcı doğrulamasını korur; tamamlanamayan kontrolü başarısız ölçütten ayırır. Yalnız mevcut PID adaptörü önerilebilir; otomatik teşhis veya komut gönderimi yoktur.

Açıkça seçilen baseline ve onaylanan bakım kayıtları sınırlı, atomik, sürümlü depoda saklanır. Parça değişimi baseline kayıtlarını geçersiz kılar. Bakım aralığı kaynak gerektirir; varsayılan süre uydurulmaz. Sayaç sıfırlanması veya kimlik değişimi bilinmeyen sonuç üretir. Örneklenmiş açık kalma süresinin aralığın altında olması bakım gerekmediğini kanıtlamaz.

Petrel tamamlanan sonuçları sınırlı epoch/config kapsamlı değerlendirme önbelleğine alır. maintenance_assessment_report() istek üzerine çalışan backend API'sidir ve test başlatmaz. Termal sonuçlar işlem kimliği, hedef, süre, başlangıç sıcaklığı, doğrulanmış fan başlangıç durumu ve firmware kimliğini taşır. Fan kanıtı yoksa referans oluşturulmaz. Kullanıcı aynı donanım ve soğutma koşullarını açıkça onaylar; ortam veya parça ömrü varsayılmaz. Geçmiş koşulları ve geri yüklemeyi ayrı saklar.

Firmware bulguları aktif throttling ile geçmiş bayrakları, Klipper durumunu ve desteklenen sürücü hatalarını ayırır. Sayısal politikalar açık kaynak/sürüm ve sonlu sınırlar gerektirir. Trend karşılaştırması gösterge niteliğindedir; arızalı parçayı teşhis etmez. Eksik kanıt kuralı sağlamaz.

Backend detailed_report API'si kaynaklı metrik politikaları, capability'ye bağlı bakım görevleri ve karşılaştırılabilir trend kanıtlarını kabul eder. Desteklenmeyen hedefler dışarıda kalır. Güncel gözlemler yapılandırılabilir tazelik süresinden sonra bilinmeyen olur; bu kullanıcı etkileşimi zaman aşımı değildir. Depolama istekleri mevcut worker ve izinli işlem listesiyle çalışır. Otomatik test başlatma veya fiziksel komut yoktur.

Bakım politikaları onaylanmış bakım olaylarından ayrı saklanır. Kalibrasyonun tamamlanması donanım sağlığı anlamına gelmez. Anlam metinleri UI tasarımı dayatmadan EN/TR eşli sunulur. Dışa aktarım işlem, koşul ve geri yükleme kanıtını korur. Petrel ayrıntılı backend raporu için maintenance_assessment_details sunar.

Birim kayıt tablosu canlı gözlem ve kayıtlı sonuçları tipli kanıta dönüştürür. Bilinmeyen birimler atlanır. Çağıranın doğruladığı karşılaştırma koşulları ölçülen koşulları değiştiremez. Eksik veya bilinmeyen koşullar baseline karşılaştırmasını engeller. F12 açıklama metni ayrıştırılmadan yapılandırılmış PWM sınırları üretir. Isınma hızı referansı, karşılaştırma ve kaldırma UI üzerinden ayrıca onaylanır. Yeni ölçüm veya referans değişikliği eski karşılaştırma bulgusunu geçersiz kılar.


Örneklenmiş baskı ve bileşen açık kalma süreleri kalıcı sayaç kimliğiyle ayrı takip başlangıçlarına ve onaylanan bakım olaylarına bağlanır. Plan kaydı mevcut saat/sayaç değerinden bağımsız bir takip başlangıcı oluşturur; bakım tamamlanmış sayılmaz. İki tür referansı da olmayan eski planlar ilk uygun worker okumasında takibe başlar; önceki kullanım uydurulmaz. Onaylanan tamamlanma tarihi, sayacı ve kimliği saklanır ve sonraki bakım döneminin referansı olur. Kimlik değişimi, eksik sayaç veya geriye gidiş ölçülen ilerleme oluşturmaz. Eşik dolmadan da örneklenmiş alt sınır oranı "recorded" ilerleme olarak gösterilir ancak bakım gerekmediği iddia edilmez; eşik aşılınca bakım zamanı doğrulanır. Takvim ve kullanım temelleri farklı tamamlanma geçmişlerini korur.

Yapılandırma kimliği, iç içe donmuş sözlükler normal JSON nesnelerine dönüştürülerek kanonik biçimde üretilir; anahtar eklenme sırası kimliği değiştirmez. Eski özet birebir eşleşiyorsa uyumlu ısıtma referansı kendiliğinden yeniden yazılmadan okunabilir. Yeni genişlik kaydı, birebir eşleşen eski anahtarı kanonik kimliğe taşır.
