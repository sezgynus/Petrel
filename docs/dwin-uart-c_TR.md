# Native C broker kurulum ve kurtarma

[Yardımcı UART](dwin-uart_TR.md) · [English](dwin-uart-c.md)

`master` üzerindeki isteğe bağlı UART installer'ı native C broker'ı derleyip kurar.
Python referans uygulaması kaynak ağacında korunur; güncel master'da seçilebilir
bir çalışma zamanı değildir. TTY, takma ad, kernel modülü, ekran soketi handshake'i
ve ortak bağlantı sınırları değişmez.

## Kurulum veya geçiş

Yardımcı UART kullanan programları kapatıp çalıştırın:

```bash
cd ~/Petrel
git fetch origin
git switch master
git pull --ff-only
./configure.sh
```

**DWIN auxiliary UART as a Linux serial port** işaretli kalsın; kaydedin, çıkın ve
uygulayın. Kurulum, servisleri durdurmadan önce native binary'yi derler, ardından
`Petrel-dwin.service` komutunu sürümlenmiş binary'ye geçirir. Python kurulum manifesti
otomatik taşınır. Ek Kconfig seçeneği veya elle derleyici komutu gerekmez.
[UART güncelleme rehberindeki](dwin-uart_TR.md) başlangıç ön kontrolünü kurmak için
bir kez uygulayın. Sonraki Petrel restart işlemleri değişen native kaynakları otomatik
derler; broker yine kurulmuş binary üzerinden çalışır.

Kurulum, configure'ın özel `umask 077` ayarından bağımsız olarak binary dizinlerini
erişilebilir yapar ve servisleri durdurmadan önce servis kullanıcısıyla `--help`
çalıştırır. Yeniden uygulama, ilk C installer'ındaki dizin izinlerini de onarır.

```bash
systemctl show Petrel-dwin.service -p ExecStart
systemctl is-active Petrel.service Petrel-dwin.service
```

`ExecStart`, Python yerine `/usr/local/libexec/petrel-dwin/broker-…` göstermelidir.
İki servis de aktifse Python için kullanılan aynı ikili TX ve PSS/USS/SwapPss ölçümünü,
aynı ekran durumu ve trafik ile tekrarlayın. Karşılaştırma yapılmadan Pi'de ölçülmüş
bellek kazancı iddia edilmez. Başka mimarideki CI bellek değeri bu ölçümün yerine geçmez.

## Yardımcı transport'u kapatma

Yardımcı UART uygulamalarını kapatıp çalıştırın:

```bash
cd ~/Petrel
./configure.sh
```

**DWIN auxiliary UART as a Linux serial port** seçeneğinin işaretini kaldırın,
kaydedin, çıkın ve uygulayın. Kaldırma, Petrel'in ekranla doğrudan haberleşmesini
geri getirir ve yardımcı TTY'yi kaldırır. C transport'u yeniden kurmak için
master üzerinde seçeneği tekrar etkinleştirin.

Eski `feature/dwin-aux-uart` ve `feature/dwin-aux-uart-c` dalları tarihsel geliştirme
kopyalarıdır. Bu dallara geçmek yeni NFC ve Maintenance özellikleri dahil bütün
uygulamayı değiştirir; yalnız transport'u geri almak değildir. Başarısız installer
geçişi ise önceki servis birimini ve yürütülebilir dosyayı otomatik geri yükler.
Yeniden denemeden önce günlüğü inceleyin; güncel UART'ı açmak veya onarmak için
dal değiştirmeyin.

## Doğrulama sınırı

CI, release ve AddressSanitizer/UndefinedBehaviorSanitizer varyantlarını derler. PTY
ve paket soketi testleri; çerçeve baytları içeren ikili veriyi, baud komutlarını,
uzunluğa duyarlı yanıtları, arayüz izolasyonunu, bozuk girdiyi ve heartbeat toparlanmasını
kapsar. Test paket backend'i yalnız bu kontroller için derlenir; kurulan yürütülebilir
dosya kernel misc aygıtını kullanır. Linux 6.1/6.12 konukları üretim C broker'ını ve
gerçek TTY'yi ikili loopback, baud geri okuma, drain ve broker çıkışında hangup ile sınar.

Fiziksel Pi TX/RX, baud zamanlaması, ekran akıcılığı, kopma/toparlanma ve sürekli
bellek/CPU kabulü ayrıca yapılmalıdır. Mevcut ortak bağlantı hız sınırları geçerlidir.
