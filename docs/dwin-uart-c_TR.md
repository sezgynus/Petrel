# Native C broker denemesi

[Yardımcı UART](dwin-uart_TR.md) · [English](dwin-uart-c.md)

`feature/dwin-aux-uart-c`, Python sürümünün `4edee47` commit'inden başlar. Asıl
`feature/dwin-aux-uart` dalı korunur. Yalnız broker çalışma zamanı değişir:
`/dev/ttyDWIN0`, takma adı, kernel modülü, ekran soketi handshake'i ve UART sınırları
uyumlu kalır. Python referans uygulaması kaynak ağacında tutulur.

## Kurulum veya geçiş

Yardımcı UART kullanan programları kapatıp çalıştırın:

```bash
cd ~/Petrel
git fetch origin
git switch feature/dwin-aux-uart-c
git pull --ff-only
./configure.sh
```

**DWIN auxiliary UART as a Linux serial port** işaretli kalsın; kaydedin, çıkın ve
uygulayın. Kurulum, servisleri durdurmadan önce native binary'yi derler, ardından
`Petrel-dwin.service` komutunu sürümlenmiş binary'ye geçirir. Python kurulum manifesti
otomatik taşınır. Ek Kconfig seçeneği veya elle derleyici komutu gerekmez. Native
kaynak güncellemelerinden sonra yapılandırmayı yeniden uygulayın; servis çalışma
dizinindeki kaynak dosyalar yerine kurulmuş binary'yi çalıştırır.

```bash
systemctl show Petrel-dwin.service -p ExecStart
systemctl is-active Petrel.service Petrel-dwin.service
```

`ExecStart`, Python yerine `/usr/local/libexec/petrel-dwin/broker-…` göstermelidir.
İki servis de aktifse Python için kullanılan aynı ikili TX ve PSS/USS/SwapPss ölçümünü,
aynı ekran durumu ve trafik ile tekrarlayın. Karşılaştırma yapılmadan Pi'de ölçülmüş
bellek kazancı iddia edilmez. Başka mimarideki CI bellek değeri bu ölçümün yerine geçmez.

## Python'a geri dönme

```bash
cd ~/Petrel
git switch feature/dwin-aux-uart
./configure.sh
```

Yardımcı UART açık kalsın ve uygulayın. Kurulum manifesti farklı olduğu için Python
dalının installer'ı Python servis komutunu geri getirir. Yalnız Git dalını değiştirmek
veya restart yapmak kurulu servis komutunu değiştirmez. Eski Python installer'ı artık
kullanılmayan C binary'sini diskte bırakabilir; bu dosya çalıştırılmaz.

## Doğrulama sınırı

CI, release ve AddressSanitizer/UndefinedBehaviorSanitizer varyantlarını derler. PTY
ve paket soketi testleri; çerçeve baytları içeren ikili veriyi, baud komutlarını,
uzunluğa duyarlı yanıtları, arayüz izolasyonunu, bozuk girdiyi ve heartbeat toparlanmasını
kapsar. Test paket backend'i yalnız bu kontroller için derlenir; kurulan yürütülebilir
dosya kernel misc aygıtını kullanır. Linux 6.1/6.12 konukları üretim C broker'ını ve
gerçek TTY'yi ikili loopback, baud geri okuma, drain ve broker çıkışında hangup ile sınar.

Fiziksel Pi TX/RX, baud zamanlaması, ekran akıcılığı, kopma/toparlanma ve sürekli
bellek/CPU kabulü ayrıca yapılmalıdır. Mevcut ortak bağlantı hız sınırları geçerlidir.
