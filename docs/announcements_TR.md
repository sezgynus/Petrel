# Çevrimiçi proje duyuruları

[English](announcements.md) · [Türkçe](announcements_TR.md) · [Dokümantasyon](README_TR.md)

Petrel, proje ekibinin yeni sürüm haberleri ve kullanıcıları ilgilendiren önemli bilgilendirmeler gibi duyurularını yazıcının ekranında gösterir. Çevrimiçi duyurular varsayılan olarak açıktır.

## Duyuruları alma ve okuma

Özellik açıkken Petrel, GitHub'daki projenin `master` dalında yayımlanan [herkese açık duyuru dosyasını](https://raw.githubusercontent.com/sezgynus/Petrel/master/announcements.json) açılışta ve beş dakikada bir indirir. Yayın zamanı belirtilmeyen yeni duyurular başarılı indirmeden sonra görünür. Zamanlanmış duyurularda Petrel'in çalıştığı Linux cihazının yerel tarihi ve saati kullanılır. Duyuru önceden indirilmişse belirlenen saat geldiğinde görünür. Petrel o saatten sonra açılırsa veya duyuruyu ilk kez o saatten sonra indirirse duyuru indirme tamamlandığında görünür.

Duyuruyu okumak için üst çubuktaki zil simgesini açın. Duyuruyu seçip enkodere bastığınızda okundu olarak işaretlenir ve listeden çıkar. Petrel bu tercihi yeniden başlatma sonrasında da hatırlar. Aynı duyuru dosyada kaldığı sürece tekrar gösterilmez. Henüz okunmamış duyurular da yeniden başlatma sonrasında korunur.

## Ağ erişimi ve gizlilik

Petrel, GitHub'daki aynı herkese açık dosyayı her kurulumda HTTPS üzerinden ister. Bu istek için GitHub hesabı gerekmez. İstekle yazıcı bilgisi, cihaz kimliği veya okundu durumu gönderilmez. GitHub, genel IP adresi ve istek zamanı gibi standart bağlantı bilgilerini alır. Okundu kayıtları Petrel'in çalıştığı Linux cihazında saklanır.

## Çevrimiçi duyuruları kapatma

Ekranda **Device settings → Announcements** seçeneğini kapatın. Petrel, GitHub'da duyuru kontrolünü durdurur ve zamanlanmış duyuruları göstermeyi askıya alır. Daha önce alınan duyurular ve okundu kayıtları korunur. Ayar Linux cihazında saklanır ve yeniden başlatma sonrasında geçerliliğini korur. Kontrolleri sürdürmek için aynı menüden seçeneği açabilirsiniz.
