# Katkıda bulunma

[English](CONTRIBUTING.md) · [Türkçe](CONTRIBUTING_TR.md) · [Dokümantasyon](docs/README_TR.md)

## Hata bildirme veya özellik önerme

GitHub issue açıp ne denediğinizi, ne beklediğinizi ve ne olduğunu anlatın. Petrel revizyonunu, Pi/işletim sistemini, ekran modelini, ilgili Klipper/Happy Hare sürümlerini, tekrar üretme adımlarını ve kısa servis günlüğünü ekleyin. Görsel sorunlarda özgün boyutlu ekran görüntüsü ve gerektiğinde fiziksel ekran fotoğrafı paylaşın. Kimlik bilgilerini ve özel ağ bilgilerini kaldırın.

Özellik önerisi kullanıcı akışını ve gereken yazıcı özelliğini anlatmalıdır. Kod, dokümantasyon, çeviri, ikon veya donanım test sonucu ile katkı yapılabilir.

## Değişiklik hazırlama

Güncel `master` üzerinden dal açın; değişikliği odaklı tutun ve problemi, sonuçta oluşan davranışı ve doğrulamayı anlatan pull request açın. Moonraker Update Manager kurulu repoyu temiz tutabilsin diye ayrı geliştirme kopyası kullanın. Makine ayarlarını harici ortam dosyasında tutun.

Kullanıcının gördüğü değişikliklerde ilgili rehberi ve ekran görüntülerini güncelleyin. **İngilizce ve Türkçe belgeler aynı özellik ve adımları kapsamalı**, aynı görselleri/sırayı kullanmalı ve ekrandaki adları korumalıdır. Güncel kullanım rehberlere, geçmiş audit'ler referanslara aittir.

## Geliştirme araçları

| Araç | Ne işe yarar | Başlangıç |
|---|---|---|
| İsteğe bağlı framebuffer emülatörü | Görsel inceleme, dokümantasyon ve hata bildirimi için çalışan LCD arayüzünü yakalar | [Emülatör rehberi](docs/ui-emulator_TR.md) |
| Regresyon testleri | Yazıcıya bağlanmadan veya hareket ettirmeden değişikliği kontrol eder | [Test rehberi](tests/README_TR.md) |
| JPEG ikon paketleyici | İkon ekler ve yönetilen kütüphaneyi dışa aktarır | [İkon kaynak rehberi](assets/icons/README_TR.md) |
| Servis günlükleri | Açılış, bağlantı ve işlem hatalarını incelemeyi sağlar | [Sorun giderme](docs/installation_TR.md#sorun-giderme) |

## Çalıştırma ve doğrulama

Regresyon iş akışı her dal push'unda ve master hedefli pull requestlerde çalışır. Her mantıksal değişikliği gönderip imzalamayı bekleyin; devam etmeden son imzalı HEAD üzerindeki CI'ı doğrulayın. Yerini imzalı commit'e bırakan SHA üzerindeki kontroller son kalite kapısı değildir. Aşağıdaki komutlar isteğe bağlı yerel katkı araçlarını belgeler; CI öncelikli proje akışında zorunlu değildir.

Kurulu Pi'de mevcut uygulama ortamı çalışma bağımlılıklarını içerir. Testleri geliştirme kopyasından çalıştırın:

```bash
~/petrel-env/bin/python -m unittest discover -s tests -v
~/petrel-env/bin/python -m compileall -q .
```

Uygulamayı manuel denerken UART ve encoderi tek süreç kullansın diye önce kurulu servisi durdurun. Kendi bağlantı/pin değerlerinizi verin; `run.py` doğrudan çalıştırıldığında servisin ortam dosyasını okumaz ve yalın UART/düğme varsayılanları kurulumdan farklıdır:

```bash
sudo systemctl stop Petrel.service
if systemctl is-active --quiet Petrel-dwin.service; then
  export PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock
else
  unset PETREL_DWIN_SOCKET
fi
cd ~/Petrel
~/petrel-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 16 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

Manuel süreçten çıktıktan sonra `sudo systemctl start Petrel.service` ile kurulu servisi başlatın. Seçenekler için `run.py --help` kullanın; CLI değerleri ortam değerlerinden önceliklidir. Hareket, kalibrasyon ve MMU değişikliklerini otomatik testlere ek olarak uygun donanımda deneyin.

Yardımcı UART kuruluysa broker çalışır kalsın ve yukarıdaki gibi display socket açıkça seçilsin; SSH kabuğu servis drop-in ortamını devralmaz. Broker yoksa fiziksel UART doğrudan kullanılır. [Manuel bağlantı sahipliğine](assets/README_TR.md#manuel-bağlantı-sahipliği) bakın.

## Ekran görüntüleri ve dokümantasyon

Ekranı [emülatörle](docs/ui-emulator_TR.md) yakalayın. Açıklayıcı adlarla `docs/assets/screens/` içine kaydedin; aynı ekran/durumu temsil ediyorsa mevcut görseli değiştirin. Özgün **272×480 PNG** korunsun; büyütmeyin, kırpmayın veya JPEG'e çevirmeyin. Markdown'da tutarlı gösterim genişliği ve her dilde anlamlı alt metin kullanın.

PR açmadan önce yerel bağlantıları, bölüm bağlantılarını, görsel yollarını, çeviri çiftlerini ve kullanıcı komutlarını kontrol edin. Davranış değiştirmeyen dokümantasyon düzenlemelerinde yazıcı regresyon testleri gerekmez.

Tüm dokümantasyon ekranlarını yazıcı olmadan üretmek için `tools/render_docs_screenshots.py` kullanın; [çevrimdışı üretim rehberi](docs/ui-emulator_TR.md#dokümantasyon-ekranlarını-çevrimdışı-üretme) komutları ve örnek veri kullanımını anlatır. Forum bağlantılarının kırılmaması için var olan görsel dosyalarının adlarını değiştirmeyin.

### Üretim ve kontrol sözleşmeleri

[PNG ve GIF yenileme komutlarını](docs/ui-emulator_TR.md#png-çerçeve-ve-gif-yenileme) birlikte çalıştırın. Panel PNG'lerini 272×480 olarak koruyun; çerçeveli 528×900 kopyaları yalnız sunum içindir. Aynı checkout, örnek veriler, sahne sırası ve EN/TR açıklamaları kullanın. Galerideki özgün PNG bağlantıları repo içi bağıl yollarla aynı dalı izler; forum paylaşımı için açılan GitHub sayfasının tam adresini kopyalayın.

Print/Tune doğrulaması: After Job tıklaması yalnız `SET_PIN` yapmalı, cihazı anında kapatmamalı; eski yanıt yeni düzenlemeyi ezmemeli; reddedilen değer/switch/Pause iki kez kırmızı yanıp sönüp gerçek abonelik durumuna dönmeli; yarım basılı tutma taslağı korumalı. Kaynak ve donanım kontrolleri [test rehberindedir](tests/README_TR.md).

JPEG değişikliklerinde [fan/buton kurallarını](assets/icons/README_TR.md#print-butonları-switchler-ve-fan-görselleri), font ID 0'ı, baseline 4:2:0'ı ve kaynak/export denkliğini koruyun. Normal/seçili buton maskesi aynı kalmalı. Emülatör kontrolünden sonra ilgili durumları fiziksel panelde de deneyin.

## PN532 Type 4 target geçici çözümünün gerekçesi

### Sorun ve seçilen uygulama

PN532 ile salt okunur Type 4 NDEF URI emülasyonu sırasında Android bazen hedefi ISO14443A NDEF yerine **Unknown FeliCa / NfcF** olarak tanıyordu. Deneylerde target Mode `0x05` / `0x04`, ATQA `00 04` / `00 08` ve PN532 mod algılama register müdahalesi karşılaştırıldı.

`libnfc_api.py` içindeki üretim yolu dağıtımın orijinal `libnfc.so.6` kütüphanesini, upstream PN532 `TgInitAsTarget` Mode `0x05`, ATQA `00 04` ve SAK `0x20` değerlerini korur. PN532 target oturumu, **her** `nfc_target_init()` denemesinden hemen önce `ctypes` üzerinden şu maskeli yazmayı kuyruğa alır:

```python
pn53x_write_register(device, 0x6301, 0x04, 0x04)
```

`0x6301` adresi `CIU_Mode` register'ıdır; `0x04` maskesi AutoColl mod algılamasıyla ilişkili bit 2'yi, `ModeDetOff` alanını seçer. Bu, gözlenen yanlış tanıma için donanıma özgü bir çözümdür; **belgelenmiş genel bir “FeliCa kapat” API'si değildir**. Maskeli yazma diğer bitleri korur. libnfc yazmayı önbelleğe alıp sonraki native PN532 haberleşmesinde uygular; `0` dönüşü isteğin kabulünü gösterir, register geri okuması veya başarılı RF davranışı anlamına gelmez.

Fiziksel denemelerde gözlenen FeliCa yanlış tanıması giderildiği için sistem kütüphanesi ve bu register müdahalesi seçildi. Böylece özel libnfc derlemelerini sürdürmek, sistem kütüphanelerini değiştirmek veya deneysel A/B/C/D profillerini ve işaret dosyalarını ürün ayarına dönüştürmek gerekmez. Yalnız yapılandırılmış okuyucu modeli `PN532` olduğunda ve özel erişimli target oturumunda otomatik uygulanmalıdır. Bu yazmaları diğer okuyuculara göndermeyin ve normal initiator taramasına eklemeyin.

### Ayrı Android URL yönlendirme sorunu

NFC Tools içinde NDEF URI okunmasına rağmen Android başlangıçta URL açmayı önermiyor/açmıyordu. Bu ayrı bir oturum ömrü hatasıydı: ilk tam NDEF okumasının hemen ardından kapanmak, Android'in sonraki `SELECT`/`READ` APDU'larını engelliyordu. `NFCTargetSession.serve_uri()` artık aktarım sonrasında APDU yanıtlamayı sürdürür, aktarım sonrası alımda 2000 ms zaman aşımı kullanır ve `share.ndef_transferred` olayını yalnız bir kez üretir. **ModeDetOff teknoloji yanlış tanımasını; aktarım sonrası APDU oturum ömrü URL yönlendirmesini çözer.** İki mekanizmayı bağımsız koruyun.

### Kanıt ve bakım sınırları

- Denenen PN532/Pi/Android birleşiminde kullanıcı 20/20 NDEF okuma ve URL açılması, sıfır FeliCa tanıması ve ayrıca bir kırmızı aktivasyon hatası bildirdi. Bu sınırlı fiziksel kanıttır; bütün telefonlar veya libnfc paketleri için garanti değildir. Nadir `nfc_target_init(-1)` hatası henüz çözülmedi.
- `pn53x_write_register`, denenen upstream/dağıtım libnfc 1.8.x tarafından dışarı aktarılır ancak **özel bir semboldür; kararlı public API değildir**. `bind_pn532_register()` tam ABI imzasını bağlar ve sembol yoksa anlaşılır hata verir; sessiz fallback eklemeyin. CI dağıtım sembolünü ve PN532'ye özgü davranışı denetler. libnfc sürümü veya platform değiştiğinde sembol/ABI uyumluluğunu yeniden kontrol edin.
- PN532 target oturumu kapanırken bit 2'nin maskeli temizlenmesi **best effort** olarak kuyruğa alınır. Cihazın deaktive olması veya yazmanın önbellekte kalması nedeniyle bu, doğrulanmış donanım restorasyonu değildir.
- Dağıtım kütüphanesini koruyun. Özel `.so` seçimini, deney profillerini veya aktivasyon işaret dosyalarını geri getirmeyin. Gerçek NFC okuyucu yapılandırması ve özelliğin isteğe bağlı kurulumu ayrı ve geçerli konulardır.
- İlgili regresyonlar: `tests/test_nfc_system_modedet.py`, `tests/test_nfc_type4_dispatch.py` ve `tests/test_libnfc_api.py`. Otomatik testler RF uyumluluğunu kanıtlayamaz; bu yol değiştiğinde teknoloji tanımasını ve Android URL açılmasını fiziksel olarak doğrulayın.

## Ana menü sıralama sözleşmesi

Info her zaman son ana menü öğesidir. Yeni özellikleri Info'dan önce ekleyin; RFID, Info'nun hemen önündedir. Bu sıralama `tests/test_rfid_emergency.py` ile korunur.

## Commit başlıkları ve kablo uyumluluğu

`tür(kapsam): açıklama` biçimini kullanın: `feat(ui): ...`, `fix(nfc): ...`, `fix(dwin): ...` veya `docs(guides): ...`. İmza botu mesajı korur; biçimini düzeltmez. `docs(nfc):`, yalnız NFC yayınını açıkça etkinleştirir; genel doküman değişikliklerinde kullanmayın.

Yeni encoder kablolaması A/B GPIO21/16 ve buzzer GPIO19 kullanır. Eski A/B GPIO21/19 kurulumları, çakışmayan başka bir buzzer PWM piniyle desteklenir; mevcut kurulumun kablolamasını sessizce değiştirmeyin.

Tam denetim için master’daki `docs(audit):` başlığı, imza botu aynı commit’i imzalamadan önce tüm LCD PNG/GIF ve Kconfig görsellerinin üretilmesini açıkça seçer. Üretim, galeriler ve statik iki dil/bağlantı kontrolleri önce başarılı olmalıdır. Normal commit’lerin mevcut imza davranışı korunur. Son imzalı SHA’nın tam regresyon sonucunu bekleyin. Ayrı Documentation Render eylemi sonraki yenilemeler için kullanılabilir kalır.
