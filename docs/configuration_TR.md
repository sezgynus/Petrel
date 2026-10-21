# Kconfig yapılandırma menüsü

[Dokümantasyon](README_TR.md) · [English](configuration.md)

Terminal menüsünü açmak için `~/Petrel` içinde `./configure.sh` çalıştırın.
`install.sh`, ilk kurulumda aynı menüyü kullanır. Kconfiglib 14.1.0 yalnız yapılandırma
bağımlılığıdır; eksikse betik mevcut Petrel sanal ortamına kurar. Bu ortam yoksa ayrı
ve özel bir yapılandırma sanal ortamı oluşturur. Yapılandırıcı çalışan arayüze arka
plan işi eklemez.

## Gezinme ve uygulama

Oklar ve Enter ile gezinin/düzenleyin, Space ile seçenek değiştirin, `?` ile yardımı
açın, `S` ile kaydedin, `Q` ile çıkın. Bağlantı/güç, enkoder/preset, bakım sayaçları,
ekran araçları, DWIN yardımcı UART ve uygulama seçenekleri menüleri bulunur.
Kapalı özelliğe bağlı ayarlar gizlenir; tekrar açıldıklarında kayıtlı değerleri korunur.

Mevcut ayarlar `~/.config/Petrel/Petrel.env` dosyasından alınır. Menuconfig içinde
kaydetmek yalnız seçimi hazırlar. Menüden çıkınca **Apply saved configuration**
sorusuna `y` yanıtı vermek kurulumu/kaldırmayı uygular ve ortam dosyasını atomik olarak
kaydeder. Kaydetmeden çıkmak veya Apply sorusuna `n` demek çalışma ayarlarını ve
isteğe bağlı kurulumları değiştirmez. İlk kurulum iptal edilirse servis kaydından önce
installer durur. Bağımlılık hazırlığı o aşamada tamamlanmış olabilir.

**Restart running Petrel after applying** varsayılan açıktır. Son yeniden başlatmayı
atlamak için kapatın; ortak UART bağlantısını değiştirmek, bileşen installer'ının
içinde yine restart gerektirebilir. Klipper otomatik yeniden başlatılmaz. Sayaç
extra'sını değiştirdikten sonra Klipper'ı boşta iken elle yeniden başlatın.

## Koruma ve hatalar

Özel anahtarlar ve gizli `MOONRAKER_API_KEY` kayıtları ortam dosyasında korunur;
API anahtarı menüde gösterilmez ve Kconfig dosyasına aktarılmaz. Preset yolu ve özel
remote adresi/portu içeri alınır. Ortam dosyası `0600` izniyle korunur; Git çalışma
dizinine `.config` veya kuruluma özel dosya eklenmez.

Uygulama adımı installer'ları çağırmadan önce bütün alanları doğrular. Menü açıkken
başka süreç ortam dosyasını değiştirmişse üzerine yazmak yerine menüyü yeniden açın.
Installer hataları ortam dosyasını değiştirmez ve önceki başarılı bileşen değişiklikleri
geri alınmaya çalışılır; geri alma hatası açıkça bildirilir. İsteğe bağlı bileşenlerin
kendi kurulum kontrolleri korunur; kullanımda yardımcı UART'ın kaldırılmasını
reddetme de buna dahildir.

## Açıkça seçilen otomatik yapılandırma

Eski soru dizisine boru üzerinden yanıt gönderme desteklenmez. Hiçbir şey uygulamadan
mevcut ayarları dışarı aktarın:

```bash
./configure.sh --export-config ~/petrel-settings.config
```

Özel izinli bu dosyayı Kconfig biçimiyle düzenleyin (`CONFIG_PETREL_AUX_UART=y`,
`CONFIG_PETREL_AXIS_TRAVEL=n`, tırnaklı metinler), ardından açıkça uygulayın:

```bash
./configure.sh --apply-config ~/petrel-settings.config --no-restart
```

Verilen dosya kısmi olabilir: bulunmayan semboller içeri alınan değerlerini korur.
Geçersiz/bilinmeyen ayarlar uygulama öncesinde reddedilir. `--no-restart`, bileşen
installer'ının gerektirdiği bağlantı değişimini değil, yalnız son Petrel restart'ını
atlar. API anahtarı ve menüde yer almayan diğer ayarlar hedef makineden korunur.
