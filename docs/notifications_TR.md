# Bildirim altyapısı

PetrelDisplay bir NotificationStore tutar. Özellikler panel komutu
çağırmadan Notification kaydı
yayımlayabilir. Kayıt kimliği kaynak ve anahtar çiftinden oluşur. Bir koşul
etkin kaldığı sürece aynı anahtarı, her yeni tek seferlik olay için yeni bir
anahtarı kullanın. Özdeş kayıtlar listeyi değiştirmez. Yeni kayıtlar en üstte
görünür. persistence alanının varsayılanı PERSISTENT değeridir. Bu
kayıtlar servis yeniden başladığında veya enerji geri geldiğinde
XDG_CONFIG_HOME (genellikle ~/.config) altındaki Petrel/notifications.json
dosyasından yüklenir. VOLATILE kayıtlar bellekte kalır. Her iki seçenek
aşağıdaki temizleme kurallarından bağımsızdır. Kalıcı bir kayıt
temizlendiğinde veya çözümlendiğinde önce disk güncellenir. Yazma başarısız
olursa kayıt listede kalır.

- Aksiyonu olmayan DISMISSIBLE kayıtlar satıra basıldığında listeden çıkar.
- UNTIL_RESOLVED kayıtlar, kaynağı resolve(source, key) çağırana kadar kalır.
  Satırın aksiyonu yoksa basmak kaydın durumunu değiştirmez.
- İsteğe bağlı aksiyon kimlikleri, PetrelDisplay.notification_actions
  üzerinden arayüz iş parçacığında çalışan işleyicilere bağlanır.
  İşleyiciye seçili kayıt verilir. Temizlenebilir bir aksiyon kabul
  edilemediyse False döndürün. Kalıcı kaydı, koşul ortadan kalktığında
  bildirimin kaynağı çözümler.

Geri düğmesi olan alt menülerde encoder sırası Geri, zil ve menü içeriğidir.
Ana ekranda ve Geri düğmesi olmayan ekranlarda zil ilk öğeden önce gelir.
Değer düzenleme ve onay pencereleri encoder odağını korur. Panel mevcut ekranın üstüne açılır, ilk odağı
Back düğmesine verir ve bilgi satırları dahil tüm kayıtları kaydırır.
Liste boşaldığında zil gizlenir ve odak sırasından çıkar. Moonraker bir Petrel
güncellemesi bildirdiğinde Petrel tek bir kalıcı bildirim oluşturur. Bildirime
basınca Info ekranı **Update** seçili olarak açılır. Güncelleme başka bir
istemciden de kurulsa, Moonraker artık güncelleme olmadığını bildirdiğinde
kayıt kalkar.

Vadesi dolan bakım planları da her etkin bakım döngüsü için bir kalıcı
bildirim oluşturur. Bildirime basınca Maintenance altında ilgili plan
açılır. Bakım tamamlandı olarak kaydedildiğinde veya plan kaldırıldığında
bildirim silinir. Sayaç verisi geçici olarak eksikse mevcut bildirim kalır.

Her iki panel ailesinde zil, rozet ve satır simgeleri ortak ikon
kütüphanesinden çizilir. Rozet sayısı panel yazısıdır. Çizim önbelleği
değişen düğmeyi, satırları ve kaydırma çubuğunu günceller. Paneli
kapatırken mevcut menü çizicisi, panelin altındaki menüyü geri getirir.

## Proje duyuruları

Petrel, `master` dalındaki herkese açık `announcements.json` dosyasını açılışta
ve saatte bir kontrol eder. Dosyada sürüm 1 ve bir `announcements` dizisi
kullanılır. Her kayıtta benzersiz bir `id`, bir `title` ve isteğe bağlı `detail`
alanı bulunur. ID 1–64 karakter uzunluğundadır. ASCII harf, rakam, nokta, alt
çizgi ve tire kullanılabilir. İlk karakter harf veya rakam olmalıdır. Başlığı
ve açıklamayı panele sığacak kadar kısa tutun.

Duyuruya basmak onu o kurulumda okundu olarak işaretler. Okunmamış duyurular
servis yeniden başladığında ve dosyadan kaldırıldığında listede kalır. Geçerli
bir dosya alındığında artık listede bulunmayan ID'lerin okundu kayıtları silinir.
Dosya alınamazsa veya geçersizse yerel kayıtlar korunur. Her yeni duyuruya yeni
bir ID verin ve kaldırılan ID'leri tekrar kullanmayın.
