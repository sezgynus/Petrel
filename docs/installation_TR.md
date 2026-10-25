# Kurulum ve yapılandırma

[English](installation.md) · [Türkçe](installation_TR.md) · [Dokümantasyon](README_TR.md)

## Kurulumdan önce

> **⚠️ LCD'nin kalıcı kaynakları değiştirilecektir:** Petrel ilk bağlantıda veya görseller değiştiğinde kendi açılış JPEG'ini, ortak slot-1 JPEG sayfasını ve ikon kütüphanesini DWIN LCD'nin kalıcı Picture Flash belleğine otomatik yazar. Stok görsellerin ilgili alanları değiştirilir; bu değişiklik güç kesilince veya Pi yazılımı kaldırılınca geri alınmaz. Petrel'in güncel simgeleri, animasyonları ve hızlı yerel çizim düzeni için bu işlem gereklidir. [Orijinal Creality DWIN_SET](../assets/stock-dwin/DWIN_SET) paketi ve [stok görsellere dönüş rehberi](restore-stock-dwin_TR.md) repoda yer alır. **Kurulumdan veya güncellemeden önce okuyun.**

Uyumlu DWIN T5UIC1 panel, UART/GPIO erişimli Linux SBC, Python 3.11+ ve çalışan Klipper/Moonraker kurulumu kullanın. [LCD uyumluluğunu](lcd-assets_TR.md) kontrol edin. Kurulum betiği LCD kernel firmware'ini veya fontunu yüklemez; Petrel ikonlarını uygulama ilk LCD bağlantısında otomatik eşitler.

## Bağlantı ve seri port hazırlığı

| Ekran bağlantısı | Raspberry Pi bağlantısı |
|---|---|
| RX | GPIO14 / UART TX |
| TX | GPIO15 / UART RX |
| Encoder A | GPIO21 |
| Encoder B | GPIO16 |
| Encoder düğmesi | GPIO20 |
| Donanımsal PWM buzzer | GPIO19 / fiziksel pin 35 (uygun sürücü ile) |
| VCC | 5 V |
| GND | GND |

GPIO numaraları **BCM numaralarıdır**. Aşağıdaki çizim güncel kurulum varsayılanlarını ve fiziksel konnektör konumlarını gösterir. Encoder pinleri yapılandırma sırasında değiştirilebilir; güncellerken mevcut kablolamanızı koruyun.

![BCM ve fiziksel konnektör pin numaralarıyla güncel Petrel varsayılan bağlantısı](../images/petrel-wiring.svg)

Eski [bağlantı fotoğrafları ve GPIO çizimi](../images/README_TR.md), farklı pin atamaları kullanan tarihsel kurulum örnekleridir; yeni varsayılan kablolama için yukarıdaki çizimi kullanın.

`sudo raspi-config` içinde seri donanımı etkinleştirin, seri giriş konsolunu kapatın ve yeniden başlatın. Pi ve işletim sisteminizde GPIO14/15'i hangi UART aygıtının kullandığını doğrulayın. Kurulum `/dev/ttyS0` önerir; kendi kurulumunuza uygun aygıtı seçin.

## Kurulum

Servisin sahibi olacak kullanıcıyla çalıştırın. Repo temiz olmalı ve `~/Petrel` konumunda bulunmalıdır:

```bash
cd ~
git clone https://github.com/sezgynus/Petrel.git
cd ~/Petrel
./install.sh
```

İlk kurulum Kconfig menüsünü açar. Bu varsayılanları gözden geçirip kaydedin, çıkın ve Apply sorusunu onaylayın:

![İlk kurulum Kconfig menüsü](assets/configuration/main-menu.png)

| Ayar | Kurulum varsayılanı |
|---|---|
| Moonraker URL | `http://127.0.0.1:7125` |
| UART | `/dev/ttyS0` |
| Encoder A/B | `21 16` |
| Encoder düğmesi | `20` |
| Moonraker güç aygıtı | `Printer` |
| Güç açma basılı tutma süresi | `2000` ms (2 saniye) |
| Eksen mesafesi sayaçları | Açık; istemiyorsanız Space ile kapatın |
| Klipper deposu (açıksa) | `~/klipper` |
| Ana Klipper config dosyası (açıksa) | `~/printer_data/config/printer.cfg` |
| Emülatör / ekran görüntüsü yakalama | `0` kapalı |
| Remote display | `0` kapalı |

Kurulum `~/petrel-env` ortamını hazırlar, bağımlılıkları yükler ve `Petrel.service` servisini etkinleştirir. Ayarlar `~/.config/Petrel/Petrel.env` içinde tutulur; `moonraker.conf` yanına `Petrel.conf` include dosyası eklenir ve servis Moonraker güncellemelerine kaydedilir. Kurulum tekrarlandığında mevcut ayarlar korunur.

Moonraker yapılandırmanız farklı konumdaysa:

```bash
MOONRAKER_CONFIG=/path/to/moonraker.conf ./install.sh
```

## İsteğe bağlı eksen mesafesi sayaçları

Kconfig menüsünde **Maintenance usage counters → Axis travel and event-based sensor counters** seçeneği bulunur. İlk yapılandırmada açıktır; Space ile değiştirilir. Sonraki çalıştırmalarda kaydedilmiş tercih korunur. Mevcut kurulumlar güncellemede sessizce değiştirilmez: bu özelliği seçmek için `./configure.sh` çalıştırın.

Açıldığında `klippy/extras/petrel_axis_travel.py`, Petrel deposundaki extra'ya symlink olarak bağlanır. Ana Klipper config dosyasının yanına `petrel-axis-travel.cfg` oluşturulur ve ana config dosyasının başına işaretli include bloğu eklenir; mevcut wildcard include parçayı zaten kapsıyorsa ikinci include eklenmez. Klipper'ın takip edilen kaynakları veya `.gitignore` değiştirilmez; yalnız ilgili symlink'in tam yolu deponun yerel Git exclude dosyasına eklenir. Kullanıcının mevcut istisnaları korunur; çakışan yabancı dosyanın üzerine yazılmaz. Bağlantı, enkoder, güç ve isteğe bağlı entegrasyon ayarları ilgili Kconfig menülerinden değiştirilir.

**Açtıktan veya kapattıktan sonra yazıcı boştayken Klipper'ı yeniden başlatın**, ardından keşfi yenilemek için Petrel'i yeniden başlatın. Yapılandırıcı Klipper'ı otomatik yeniden başlatmaz. X/Y/Z mesafe cihazları ve **Recorded travel (metres)** hatırlatıcıları yalnız extra gerçekten yüklüyse sunulur. Ölçüm sınırları ve kaynak bütçesi için [kullanım takibine](maintenance-usage_TR.md) bakın.

Kapatmak için `./configure.sh` çalıştırın, sayaç seçeneğinin işaretini kaldırıp kaydedin ve uygulayın. Yalnız Petrel'in yönettiği config parçası/include, symlink ve kendisinin eklediği Git istisnası kaldırılır. Sayaçlar ve bakım geçmişi korunur; kayıtlı mesafe hatırlatıcıları duraklar. Aynı şekilde boşta Klipper restart uygulayın. Symlink sayesinde extra Petrel ile güncellenir; çalışan Klipper yeni kodu sonraki restart sırasında yükler. Klipper yeniden kurulumu/sert kurtarma bağlantıyı silebilir: onarmak için `configure.sh` tekrar çalıştırılır.

## Donanımsal PWM buzzer

Kconfig **Buzzer hardware PWM** menüsü GPIO12/13/18/19 arasından seçim yapar; varsayılan buzzer GPIO19, encoder B GPIO16'dır. Kurucu uygun device-tree PWM overlay'i yazar veya mevcut uyumlu overlay'i korur; çakışan analog PWM sesini kapatır. Root yetkili systemd ön hazırlık adımı, yalnız ilgili PWM kanalına Petrel kullanıcısının erişmesini sağlar. Boot overlay'i değişirse Pi reboot gereklidir; Klipper restart gerekmez.

GPIO19'u encoder B için kullanan eski kurulumlar korunur: `./configure.sh` ile çakışmayan pinler seçilene kadar otomatik PWM kurulumu atlanır. Eski pin çakışması UI'ı durdurmaz, yalnız buzzer susturulur. Akım Pi GPIO sınırını aşıyorsa transistörlü buzzer sürücüsü kullanın.

## İsteğe bağlı Klipper sanal buzzer

`./configure.sh` içindeki **Virtual SET_PIN Buzzer Klipper extra** varsayılan açıktır. Yönetilen include üzerinden `[petrel_buzzer Buzzer]` oluşturur ve G-code makrolarına dokunmadan Klipper extra'sını kurar. **Klipper restart öncesi eski `[pwm_cycle_time Buzzer]` bölümünü elle silin**; aynı `SET_PIN PIN=Buzzer` adına iki modül kaydolamaz. Klipper otomatik yeniden başlatılmaz; yazıcı boşta iken restart edin.

Extra fiziksel Klipper pinine değil, Petrel'in `~/.config/Petrel/klipper-buzzer.sock` yerel socket adresine bağlanır. Klipper ve Petrel farklı Linux kullanıcılarıyla çalışıyorsa özel socket erişimini ayrıca yapılandırmak gerekir. Parametreler ve öncelikler için [kullanım rehberi](user-guide_TR.md#klipper-sanal-buzzer-isteğe-bağlı-extra) bölümüne bakın.

## LCD kaynakları ve ilk açılış

**LCD fontunu değiştirmek isteğe bağlıdır.** Petrel stok DWIN fontuyla çalışır. Petrel'in ekran görüntülerindeki yazı görünümünü isteyenler [paketle sunulan LCD fontunu](lcd-assets_TR.md#lcd-fontu) ekranın SD yuvasından isteğe bağlı yükleyebilir. İkonlar ve açılış görseli UART üzerinden otomatik eşitlenir.

1. Petrel açılış ilerlemesi tamamlanıp **Home** görünene kadar bekleyin.
2. Enkoderi çevirip bir menü açın; sıcaklıkların web arayüzüyle uyuştuğunu kontrol edin.
3. Yazılar/ikonlar yanlışsa [LCD kaynak rehberini](lcd-assets_TR.md), bağlantı hatası varsa aşağıdaki sorun giderme tablosunu izleyin.

Olağan soğuk açılış MCU bağlantı gecikmesinde boot ekranı 30 saniyeye kadar korunur; açık hata/shutdown kurtarmayı hemen açar. Yenileme/restart için [bağlantı ve kurtarma](user-guide_TR.md#yazıcı-bağlantısı-ve-kurtarma) bölümüne bakın.

Moonraker, Petrel bağlantısına izin vermelidir. Kimlik doğrulama gerekiyorsa `MOONRAKER_API_KEY` ayarlayın. Seri port ve GPIO erişimi için servis kullanıcısının izinlerini kontrol edin; installer `dialout` ve `gpio` gruplarını yapılandırır.

## Ayarları değiştirme

```bash
cd ~/Petrel
./configure.sh
```

`configure.sh`, Kconfig terminal menüsünü açar. Mevcut değerler `Petrel.env` dosyasından
alınır; yeni emülatör, remote display ve yardımcı UART seçenekleri kapalı gelir.
Oklar/Enter ile gezinin, Space ile açıp kapatın, `?` ile yardımı açın, `S` ile kaydedin,
`Q` ile çıkın. Kaydettikten sonra **Apply saved configuration** sorusunu onaylamak,
seçilen bileşenleri kurar/kaldırır ve ayarları yazar. Kaydetmeden çıkmak veya Apply
sorusunu reddetmek mevcut kurulumu korur. **Apply options** menüsü çalışan Petrel'in
son yeniden başlatmasını denetler; Klipper otomatik yeniden başlatılmaz. Otomatik
kurulum, koruma ve hata davranışı için [yapılandırma rehberine](configuration_TR.md)
bakın. Parlaklık/kısma ayarları LCD'de **Home → Device** altında kalır.

Menüde bulunmayan ayarlar için harici ortam dosyasını düzenleyin. `export` kullanmadan düz `KEY=value` satırları yazın:

| Ayar | Amaç / varsayılan |
|---|---|
| `MOONRAKER_URL` | Moonraker adresi / `http://127.0.0.1:7125` |
| `MOONRAKER_API_KEY` | Gerekiyorsa kimlik doğrulama anahtarı / boş |
| `PETREL_REQUEST_TIMEOUT` | Saniye cinsinden istek zaman aşımı / `5` |
| `PETREL_SERIAL_PORT` | Yapılandırılmış UART / kurulum `/dev/ttyS0` önerir |
| `PETREL_ENCODER_PINS` | BCM numaralarıyla encoder A/B / `21 16` |
| `PETREL_BUTTON_PIN` | BCM numarasıyla encoder düğmesi / `20` |
| `PETREL_BUZZER_GPIO` | Donanımsal PWM buzzer GPIO12/13/18/19, varsayılan `19` |
| `PETREL_SETTINGS_FILE` | Yerel preset yedeği / `~/.config/Petrel/presets.json` |
| `PETREL_POWER_DEVICE` | Moonraker güç aygıtınızın adı / `Printer` |
| `PETREL_POWER_ON_HOLD_MS` | Milisaniye cinsinden güç açma süresi / `2000`; `0` anında açar |
| `PETREL_EMULATOR` | Ekran görüntüsü alma / `0` kapalı, `1` açık; Kconfig menüsünden seçilir |
| `PETREL_REMOTE` | Tarayıcı görüntüsü ve enkoder kontrolü / `0` kapalı, `1` açık; emülatörü de başlatır |
| `PETREL_REMOTE_HOST` | Remote dinleme adresi / `0.0.0.0`; yapılandırıcı korur |
| `PETREL_REMOTE_PORT` | Remote portu / `8088`; yapılandırıcı korur |
| `PETREL_NFC` | İsteğe bağlı libnfc çalışma zamanı bağımlılığı / `0` kapalı; `configure.sh` ile açıp kapatın; DWIN yardımcı UART'ından bağımsızdır |
| `PETREL_AXIS_TRAVEL` | İsteğe bağlı extra kurulum tercihi / ilk yapılandırmada `1`; yalnız bu anahtarı düzenlemek yerine `configure.sh` kullanın |
| `PETREL_KLIPPER_DIR` | `klippy/extras` içeren Klipper deposu / `~/klipper` |
| `PETREL_PRINTER_CONFIG` | Yönetilen include eklenecek ana config / `~/printer_data/config/printer.cfg` |

Düzenleme sonrası `sudo systemctl restart Petrel.service` ile yeniden başlatın. Özel anahtarları ve makine ayarlarını takip edilen repo dosyalarının dışında tutun. Görüntü almaya özel seçenekler için [emülatör rehberine](ui-emulator_TR.md) bakın.

## Güncelleme

### Güncelleme ve eski kurulumdan geçiş

Mevcut kurulum, sonraki Moonraker güncellemesinden sonra otomatik taşınır: eski updater bu sürümü indirir ve ilk servis açılışı ayrı bir geçiş işi başlatır. Ayarlar korunur, repo `~/Petrel` konumuna taşınır, `~/petrel-env` hazırlanır, `Petrel.service` kurulur ve Moonraker yeni updater kaydıyla yeniden başlatılır. Python bağımlılıkları için birkaç dakika bekleyin. Otomatik geçiş Pi üzerinde şifresiz sudo erişimi gerektirir; bu yoksa bir kez `sudo python3 ~/KlipperDWIN/petrel_migration.py --user "$USER"` çalıştırın. Mevcut bir Petrel kurulumunun üzerine yazılmaz. Servis geçişi başarısız olursa önceki kurulum geri yüklenir; ayrıntılar `journalctl -u Petrel-migration.service` içindedir.

Moonraker yapılandırmasını yeniden okuduktan sonra **Mainsail → Machine → Update Manager → Petrel** yolunu kullanın. Listeyi yenileyip güncelleyin; bağımlılıklar ve servis yeniden başlatması otomatik yapılır. Update Manager `master` dalını takip eder.

Yazıcı boşta iken LCD'deki **Info** bölümünden de Petrel güncellemelerini kontrol edip yükleyebilirsiniz. [Info ve güncellemeler](user-guide_TR.md#info-ve-güncellemeler) bölümüne bakın. Takip edilen repo dosyalarındaki yerel değişiklikler güncellemeyi engelleyebilir; kurtarma bunları silmeden önce inceleyin veya yedekleyin.

## Sorun giderme

```bash
sudo systemctl status Petrel.service --no-pager
journalctl -u Petrel.service --since "10 minutes ago" --no-pager
sudo systemctl restart Petrel.service
```

| Belirti | Kontrol edilecekler |
|---|---|
| Ekran boş veya sürekli yeniden bağlanıyor | Panel gücü, çapraz TX/RX, seçilen UART, seri giriş konsolu ve izinler |
| Encoder yanıt vermiyor | BCM pin ayarları ve bağlantılar |
| Açılış bir aşamada kalıyor | Klipper/Moonraker hazır durumu, ekran kaynakları ve servis günlükleri |
| İsteğe bağlı menü yok veya kilitli | Gerekli Klipper/Happy Hare yapılandırması, bağlantı ve mevcut yazıcı durumu |
| Önizleme görseli veya metadata yok | Slicer thumbnail'ları ve Moonraker'daki metadata |
| Wi-Fi bilgisi kullanılamıyor | Kablosuz bağlantı ve Linux `iw` komutunun bulunması |
| Güncelleme engelleniyor | Yerel repo değişiklikleri ve Moonraker Update Manager durumu |
| İşlem başarısız veya zaman aşımına uğradı | Tekrarlamadan önce Mainsail'den gerçek yazıcı durumunu kontrol edin |

Hata bildirimine yazılım revizyonunu, Pi/işletim sistemini, ilgili yapılandırmayı ve günlük bölümünü ekleyin. Görsel sorunlarda fotoğraf veya [emülatör ekran görüntüsü](ui-emulator_TR.md) ekleyin; paylaşmadan önce kimlik bilgilerini kaldırın.

### Extra güncellemesinde sensör olay sayaçları

Mevcut isteğe bağlı axis-travel extra’sı artık olay tabanlı sensör sayaçlarını da sunar. `configure.sh` içindeki ortak seçeneğin mevcut `PETREL_AXIS_TRAVEL` anahtarı korunur. Yeni eklenti dosyası/include eklemek gerekmez. Kurulu symlink güncel dosyayı izler; yüklemek için yazıcı boşta iken Klipper’ı yeniden başlatın, ardından Petrel’i yeniden başlatın. Otomatik Klipper restart yapılmaz. Extra eski/kapalı/eksikse sensör olay reminder’ları duraklar, geçmişler silinmez. Kaynaklar ve sayım kapsamı için [kullanım sayaçları rehberine](maintenance-usage_TR.md#olay-tabanlı-sensör-sayaçları) bakın.

## İsteğe bağlı yardımcı UART

DWIN yardımcı UART üzerinden sunulan isteğe bağlı Linux seri portunu kurmak veya
kaldırmak için `./configure.sh` çalıştırın. Varsayılan kapalıdır. [Kurulum ve sınırlar](dwin-uart_TR.md).
