# Bildirim altyapısı

PetrelDisplay başlangıçta boş olan bir NotificationStore tutar. Depo
bellekte çalışır. Özellikler panel komutu çağırmadan Notification kaydı
yayımlayabilir. Kayıt kimliği kaynak ve anahtar çiftinden oluşur. Bir koşul
etkin kaldığı sürece aynı anahtarı, her yeni tek seferlik olay için yeni bir
anahtarı kullanın. Özdeş kayıtlar listeyi değiştirmez. Yeni kayıtlar en üstte
görünür. Özellikler açılışta çözülmemiş koşulları yeniden yayımlayabilir.

- Aksiyonu olmayan DISMISSIBLE kayıtlar satıra basıldığında listeden çıkar.
- UNTIL_RESOLVED kayıtlar, kaynağı resolve(source, key) çağırana kadar kalır.
  Satırın aksiyonu yoksa basmak kaydın durumunu değiştirmez.
- İsteğe bağlı aksiyon kimlikleri, PetrelDisplay.notification_actions
  üzerinden arayüz iş parçacığında çalışan işleyicilere bağlanır.
  İşleyiciye seçili kayıt verilir. Temizlenebilir bir aksiyon kabul
  edilemediyse False döndürün. Kalıcı kaydı, koşul ortadan kalktığında
  bildirimin kaynağı çözümler.

Zil, Home, Info ve ortak Prepare, Control, Move, Temperature ve Motion
menülerinde encoder sırasının başındadır. İlk öğedeyken bir adım geri
çevirerek zile odaklanın. Panel mevcut ekranın üstüne açılır, ilk odağı
Back düğmesine verir ve bilgi satırları dahil tüm kayıtları kaydırır.
Liste boşaldığında zil gizlenir ve odak sırasından çıkar. Bu altyapıyla
bildirim kaynağı, aksiyon kaydı veya ağ sorgusu eklenmez.

Her iki panel ailesinde zil, rozet ve satır simgeleri ortak ikon
kütüphanesinden çizilir. Rozet sayısı panel yazısıdır. Çizim önbelleği
değişen düğmeyi, satırları ve kaydırma çubuğunu günceller. Paneli
kapatırken mevcut menü çizicisi, panelin altındaki menüyü geri getirir.
