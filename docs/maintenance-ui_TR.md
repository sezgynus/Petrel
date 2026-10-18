# Bakım kullanıcı deneyimi

Nihai UI feature/maintenance-ui-ux dalında geçici test UI'sından bağımsız geliştirilir. Saf deneyim modeli kayıtlı capability'leri amaç ve cihaz bazında gruplar; keşif veya donanım eylemi yapmaz. Birleşik termal kontrol yedi ayrı girişin yerini alır. Leveling offset, mesh ve vida akışları kopyalanmaz. Kalibrasyon işlev kontrollerinden ayrılır. Özetler ölçüm başarısızlığı, kullanıcı gözlemi, bilgi ve tamamlanamayan yürütmeyi ayırır. Sayısal kanıt ve geri yükleme bilgisi isteğe bağlı ayrıntıda kalır.

## Enkoder etkileşimi

Maintenance dört Graphite kutucuk açar: Check printer, Findings, Service plan ve More. Gruplar ve cihaz örnekleri kayıtlı controller planlarından gelir. Hazırlık donanımı sürmez; controller preflight ardından ayrı Start onayı vardır. Kullanıcı gözlemi, sensör geçişleri, harici ölçüm, F12 tam duruş ve workflow adımları açık seçimlerle ilerler. Back aynı cihaza döner. Bilgi okumaları istek üzerinedir. Recovery ekranı Maintenance'ı örttüğünde aktif işlemler poll edilmeye devam eder. Güvenlik durdurma metinleri ısıtıcı shutdown ile normal gezinmeyi ayırır.

Normal durum şeridi korunur. Kök kutucuklar yönetilen metinsiz 156–163 ikonlarını kullanır; alt ekranlar sınırlı kısmi çizilir. Sayısal kanıt isteğe bağlı kaydırılan Details ekranındadır. Destek kaydı ana ekranda değil More altındadır. Lokal test/emülatör gerekmez; yeni gezinmeyi Actions regresyon paketi doğrular.

## Bakım hatırlatıcıları ve geçmiş

Bakım kayıtları yalnız açık istekle yüklenir ve mevcut worker üzerinde işlenir. Hatırlatıcı eklerken desteklenen cihaz, görev ve takvim aralığı seçilir. Editörün ilk değeri kurulu politika değildir; kayıt inceleme ve açık onay gerektirir. Hatırlatıcı kaydı bakım yapıldığı anlamına gelmez. Gerçek tamamlanma ayrıca onaylanır. Son bakım tarihi yoksa bilinmeyen kalır. Kaldırılan cihazlar gizlenir ve yeni tamamlanma kaydı alamaz. Aşınma veya kalan ömür tahmini çıkarılmaz.

Son kontrol geçmişi ayrıca yüklenir ve tarihsel olarak işaretlenir. Baskı kullanımı, örneklenmiş kullanım ve ayıklanmış rapor aktarımı istek üzerine bilgi okumalarıdır. Kullanıcı tek termal kontrol çalıştırsa da Findings bağımsız termal alt sonuçları içerir. Maintenance girişinde çizim önbelleği geçersiz kılınır; diğer ekranlardan kalıntı kalmaz.
