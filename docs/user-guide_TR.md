# Günlük kullanım

[English](user-guide.md) · [Türkçe](user-guide_TR.md) · [Dokümantasyon](README_TR.md)

## Gezinme ve durum alanı

**Device** simgesi **Device settings** menüsünü açar; DWIN HMI parlaklık/karartma, buzzer, olay sesleri ve NFC okuyucu ayarları burada bulunur.

<p align="center">
  <img src="assets/screens/framed/home.png" width="360" alt="Ana ekran, birinci sayfa">
  <img src="assets/screens/framed/home-page-2.png" width="360" alt="Ana ekran, ikinci sayfa">
</p>

Seçimi taşımak için çevirin; seçmek için basın. Sayısal değere basın, düzenlemek için çevirin ve uygulamak için tekrar basın. Üst bardaki sabit **geri oku**, önceki ekrana döner. Menüler ve alt menüleri bu ok seçili açılır; tekrar basarak hemen geri dönebilirsiniz. Back hiçbir içerik satırını kaplamaz. İlk içerik işlemine ulaşmak için saat yönünde çevirin; kaydırmada yalnız içerik hareket eder. Cancel gibi onay işlemleri açık güvenlik seçenekleri olarak korunur. Ana ekran her sayfada dört ikon gösterir; sayfa değiştirmek için çevirmeye devam edin. Noktalar aktif sayfayı belirtir. İsteğe bağlı öğeler yazıcınızın yapılandırmasına bağlıdır.

Alt durum alanının üç satırı aşağıdadır. Hız/akış alanları iki saniyede bir çarpan ile anlık ölçüm arasında değişir. Tune, sayı düzenleyicisi, tam hata okuyucusu ve MMU sayfalarında bu alan görünmez.

| Satır | Sol | Orta | Sağ |
|---|---|---|---|
| 1 | Nozul gerçek/hedef (°C) | Hız çarpanı (%) / anlık hız (mm/s) | Fan (%0–100) |
| 2 | Tabla gerçek/hedef (°C) | Akış çarpanı (%) / hacimsel akış (mm³/s) | Oturum Z offset (mm) |
| 3 | X (mm) | Y (mm) | Z (mm) |

Diğer küçük göstergeler de yeni ikon gerektirmeden mevcut Klipper verilerini gösterir: nozul altındaki 12×3 ve tabla altındaki 14×3 piksellik çizgiler, **ısıtma kapalı** (soluk gri), **hedef sıcaklığa yaklaşıyor** (amber) veya **hedef toleransında** (turkuaz; titreşimi önleyen histerezisle) anlamına gelir. Nozul altındaki ayrı 4×3 piksellik nokta, Klipper `can_extrude` bilgisine göre **ekstrüzyona izin var** (turkuaz), **izin yok** (amber), **durum bilinmiyor** (gri) durumunu belirtir. Speed/Flow altındaki ince amber çizgi, ilgili çarpan %100 dışındayken görünür ve %100'de kaybolur; değer alanı anlık telemetriyi gösterirken de görünmeye devam eder. Z-offset altındaki küçük turkuaz nokta **aktif Bed Mesh**'i (isimsiz/adaptif mesh dahil) belirtir; aktif mesh matrisi yoksa kaybolur. Yalnız değişen göstergeler yeniden çizilir.

X/Y/Z simgelerinin altındaki 14×3 piksellik çizgi Klipper referans durumunu belirtir: **turkuaz** referanslanmış, **amber** referanslanmamış, **gri** ise (örneğin bağlantı kesildiğinde) durum bilgisinin alınamadığı anlamına gelir. Her çizgi yalnız ilgili eksenin durumu değiştiğinde güncellenir; konum değerleri ve ikon aralıkları etkilenmez.

Fan simgesi panelin kendi animasyonuyla döner; hız fan yüzdesinden hesaplanır ve 10 ms aralıklara yuvarlanır. Aynı interval için yeniden komut gönderilmez; %0’da durur.

Saatin **hemen sağındaki 8×8 piksellik simge**, **Klipper bağlantısını** gösterir. Mevcut ilerleme çubuğu uç ikonları kullanılır: Klipper hazır ve hatasızsa dolu, diğer durumlarda (bağlanıyor, bağlantı kesildi, shutdown, hata veya bilinmiyor) boş kanal simgesi. Mevcut Moonraker abonelik durumundan beslenir, Wi-Fi RSSI’dan bağımsızdır ve yalnız durum değişince yeniden çizilir.

Saatin yanındaki küçük Wi-Fi simgesi, Info ekranıyla aynı RSSI eşiklerini kullanır: **güçlü** (≥ −60 dBm, üç etkin yay), **orta** (−70 ile −60 dBm arası, iki yay) veya **zayıf** (−70 dBm altı, tek yay). Wi-Fi bağlantısı yoksa ya da RSSI bilinmiyorsa güç seviyesi simgesi gösterilmez. Ethernet bağlantısı bu göstergeden bağımsızdır. Yerel ikon yalnız seviye değiştiğinde yeniden çizilir.

![Fan 0, 1, 50 ve 100 yüzde iken panel-native animasyon örneği](assets/framed/fan-animation-demo.gif)

Örnek verilerle gerçek UI emülatörü çıktısıdır.

## Baskı seçme ve başlatma

<p align="center">
  <img src="assets/screens/framed/print-file.png" width="360" alt="Dosya tarayıcısı">
  <img src="assets/screens/framed/print-preview.png" width="360" alt="Model ve filament önizlemesi">
</p>

1. **Home → Print** açın. Klasör veya G-code dosyası seçin. Klasörler önce gelir; **Back** bir üst klasöre, kök klasörde ise ana ekrana döner.
2. Slicer sağlıyorsa model önizlemesini, tahmini süreyi, takım değişimlerini, toplam filament uzunluğu/ağırlığını ve kullanılan filament renklerini/malzemelerini/ağırlıklarını kontrol edin.
3. Başlatmak için **Print** seçip basın veya aynı dosyaya dönmek için **Cancel** seçin. Başlangıçta Cancel seçilidir.

Tarayıcı Mainsail'in ad/tarih/boyut sıralamasını ve yönünü izler. Geçerli tercih yoksa en yeni dosyalar önce gelir. Gizli klasörler ve G-code dışındaki dosyalar gösterilmez.

Eksik thumbnail veya metadata baskıyı engellemez. En fazla dört kullanılan takım gösterilir; T0 gibi takım ID'leri slicer takımlarıdır, fiziksel MMU kanal numarası değildir. Sık açılan önizlemeler gezinmeyi hızlandırmak için önceden hazırlanır.

## Baskı ve Tune

<p align="center">
  <img src="assets/screens/framed/printing.png" width="360" alt="Baskı ilerlemesi ve kontroller">
  <img src="assets/screens/framed/printing-paused.png" width="360" alt="Duraklatılmış baskı">
  <img src="assets/screens/framed/tune.png" width="360" alt="Tune">
</p>

Print önizlemeyi, ilerlemeyi, geçen/kalan süreyi, tahmini bitişi ve varsa katman bilgisini gösterir. **Pause / Resume** doğrudan çalışır; **Stop** başlangıçta **Back** seçili onay açar. Stop onayından sonra yazıcı durumu iptali doğrulayana kadar canlı Print ekranı, devre dışı **Stopping** düğmesiyle görünür kalır. Beklerken iptal komutunu tekrar göndermeyin. Baskı bitince veya iptal edilince **Close** ile Home'a dönün.

**Tune** ile Speed, **Flow**, sıcaklık/fan, Z offset, SCV, minimum cruise ratio, PA/yumuşatma ve firmware retraction ayarlarını değiştirin. Alanlar yapılandırma ve durum verisine bağlıdır. AFTER JOB switchleri yalnız politika pinlerini değiştirir; baskı sonu eylemini makrolarınız belirler. Z offset kalıcı probe kalibrasyonu değildir. [Alanlar, birimler ve hata davranışları](print-controls_TR.md).

Elapsed hazırlık/duraklamalar dahil toplam iş süresidir. İlerleme, Remaining ve Finish [Mainsail-varsayılan hesaplarını](print-controls_TR.md#baskı-süresi-ve-ilerleme) kullanır; Remaining dosya/filament tahminlerini ortalar, Finish dilimleyici süresini de katar. Finish yanındaki `+1` yarın demektir (genelde takvim günü farkı); tahmin yoksa `--:--` gösterilir. Mainsail tarayıcısına özel seçenekler aktarılmaz.

## Yazıcı bağlantısı ve kurtarma

İlk açılışta veya yazıcı/ekran röle güç çevriminde bağlantı beklenirken boot ekranında 30 saniyeye kadar **Connecting to printer...** veya **Starting Klipper...** kalır. Açık Klipper error/shutdown kurtarmayı hemen açar. Bağlantı uzarsa **Printer connection** gecikmeyi açıklar; otomatik restart yapılmadan yeniden bağlantı denenir. Normal açılıştan sonraki kopma kurtarmayı hemen açar.

Kurtarma sayfasında kaydırılabilir hata metni ve sabit eylemler vardır. **Refresh connection** yalnız durum okur. **Restart Klipper** ve **Firmware Restart** error/shutdown için görünür; Klipper bağlantısı kopuksa **Restart Klipper service** yalnız Moonraker o örneğin tam servisini belirlerse sunulur. Moonraker erişilemiyorsa yalnız yenileme vardır. İlk seçim Refresh'tir; restart taze durum kontrolünden sonra tek açık basışla çalışır. İlk eylemin soluna dönerek hata metnini kaydırın; basınca eylemlere dönersiniz. Bağlantı toparlanınca yarıda kalan test/komut sürdürülmeden Home açılır. [Kurtarma ayrıntılarına](klipper-recovery_TR.md) bakın.

## Prepare ve Live jog

<p align="center">
  <img src="assets/screens/framed/prepare.png" width="360" alt="Prepare menüsü">
  <img src="assets/screens/framed/move.png" width="360" alt="Move, Live jog kapalı">
  <img src="assets/screens/framed/move-live-jog.png" width="360" alt="Move, Live jog açık">
</p>

**Prepare → Home** yazıcıyı home eder. **Disable steppers** motorları bırakır. **Runtime Z offset** mevcut oturumun offset'ini değiştirir.

**Prepare → Move** içinde X, Y, Z veya Extruder seçin, değeri düzenleyin ve uygulamak için basın. **Live jog** kutusu işaretliyken encoder ile düzenleme anında hareket ettirir; kutu boşken hareket onaylandığında uygulanır.

Önce gerekli eksenleri home edin. Baskı ve duraklama sırasında hareket kullanılamaz; hareket sınırları uygulanır. Ekstrüzyondan önce nozulu ısıtın. Başarısız jog sonrası hareket kilitli kalırsa yazıcıyı kontrol edin ve sunulduğunda **Control → Restore jog state** kullanın.

## Sıcaklık ve ön ısıtma presetleri

<p align="center">
  <img src="assets/screens/framed/temperature.png" width="360" alt="Sıcaklık kontrolleri">
  <img src="assets/screens/framed/preheat-settings.png" width="360" alt="Preset düzenleme ve kaydetme">
  <img src="assets/screens/framed/prepare-preheat.png" width="360" alt="Prepare içinde adlandırılmış ön ısıtma presetleri">
</p>

- **Prepare → Preheat [ad]** preset'i uygular. **Cooldown** ısıtıcıları kapatır.
- **Control → Temperature** mevcut hotend, tabla ve fan hedeflerini değiştirir.
- Preset'in **[ad] settings** bölümünü açın, ısıtıcı hedeflerini düzenleyin ve **Save settings** seçin. Preset kaydetmek ısıtmayı başlatmaz. **Back** kaydedilmemiş düzenlemeleri korur; **Discard changes** o presetin kayıtlı değerlerini geri getirir. Düzenlemeleri iptal etmeden önce süren kaydın tamamlanmasını bekleyin.

Mevcutsa preset adları ve ısıtıcı hedefleri Mainsail ile paylaşılır; LCD düzenlemeleri oraya kaydedilir. Mainsail presetleri yoksa yerel presetler kullanılır. Fan ayarları sıcaklık presetleriyle eşitlenmez.

## Çalışma zamanı hareket sınırları

<p align="center">
  <img src="assets/screens/framed/control.png" width="360" alt="Control menüsü">
  <img src="assets/screens/framed/motion-runtime.png" width="360" alt="Çalışma zamanı hareket sınırları">
</p>

Maksimum hız, maksimum ivme, square-corner velocity ve destekleniyorsa minimum cruise ratio için **Control → Motion** açın. Alana basın, çevirin ve uygulamak için basın. Değişiklikler çalışma zamanı ayarlarıdır; kalıcı varsayılan istiyorsanız Klipper yapılandırmasını ayrıca düzenleyin.

## Vida ayarı

Klipper'ın `[screws_tilt_adjust]` yapılandırmasında probe ve dört ayrı köşe vidası gerektirir.

<p align="center">
  <img src="assets/screens/framed/screws-tilt.png" width="360" alt="Vida ayarını hesaplama">
  <img src="assets/screens/framed/screws-tilt-probing.png" width="360" alt="Köşeler ölçülüyor">
  <img src="assets/screens/framed/screws-tilt-reading-results.png" width="360" alt="Sonuçlar okunuyor">
  <img src="assets/screens/framed/screws-tilt-adjust.png" width="360" alt="Vida yönleri ve dönüş miktarları">
  <img src="assets/screens/framed/screws-tilt-success.png" width="360" alt="Köşeler düzeltildi">
</p>

1. **Leveling → Screws Tilt Adjust → Calculate** açın. Eksik eksenler ölçümden önce home edilir.
2. **Probing corners…** ve **Reading results…** aşamalarını bekleyin.
3. **Base** vidasını değiştirmeyin. Diğer vidaları **CW** (saat yönü) veya **CCW** (saat yönünün tersi) ve gösterilen miktara göre çevirin. `01:20` bir tam tur ve turun 20/60'ı demektir.
4. **Continue** seçin, gerektiğinde ayarlayın ve tekrar hesaplatın. Yeşil **Corners leveled / Tolerance achieved!**, ölçülen en yüksek/en düşük farkın **0,05 mm** altında olduğunu belirtir.

Vidaları siz ayarlarsınız; ekran ölçüm ve yönlendirme yapar. Bu işlem yapılandırma kaydetmez.

## Bed mesh ve kayıtlı profiller

<p align="center">
  <img src="assets/screens/framed/leveling.png" width="360" alt="Leveling menüsü">
  <img src="assets/screens/framed/mesh-calibrating.png" width="360" alt="Nokta nokta canlı ölçüm">
  <img src="assets/screens/framed/mesh-results.png" width="360" alt="Ölçüm sonucu, Save ve Continue">
</p>

**Home → Leveling → Bed Mesh** açın. Probe yapılandırılmışsa **Calibrate** eksik eksenleri home edip tablayı ölçer. Ölçüm sonrası renkli yükseklik haritasını ve minimum/maksimum Z değerlerini inceleyin.

Ölçüm sırasında her prob sonucu ilgili noktaya anında eklenir. Ölçüm bitince ve kayıtlı mesh açılınca renk aralığı o mesh’in minimum/maksimum değerlerine göre yeniden ayarlanır: en alçak nokta mavi, en yüksek nokta kırmızı; aradaki değerler camgöbeği, yeşil ve sarı tonlarıdır.

- **Continue** menüye döner ve ölçülen mesh'i mevcut oturum için korur.
- **Save** profil ve yeniden başlatma onayı ister. Ölçülen mesh oluşturulan `lcd_mesh_N` profiline kaydedilir; Klipper yeniden başlar. İlgisiz bekleyen yapılandırma değişiklikleri kaydı engelleyebilir.
- **Mesh Viewer**, Current Mesh veya kayıtlı profilleri incelemenizi sağlar. Görüntülemek profil yüklemez, yazıcıyı hareket ettirmez ve aktif mesh'i değiştirmez. Düşük Y haritanın altındadır.

<p align="center">
  <img src="assets/screens/framed/bed-mesh.png" width="360" alt="Bed Mesh menüsü">
  <img src="assets/screens/framed/mesh-profiles.png" width="360" alt="Kayıtlı mesh profilleri">
  <img src="assets/screens/framed/mesh-viewer.png" width="360" alt="Default mesh yükseklik haritası">
  <img src="assets/screens/framed/mesh-pei.png" width="360" alt="Mesh yükseklik haritası">
</p>

**Ölçüm sırasında Cancel → Stop acil durdurmadır:** Klipper shutdown durumuna girer. Kurtarmak için web konsolundan `FIRMWARE_RESTART` kullanın. Ölçümün sürmesini istiyorsanız onayı iptal edin.

## Probe offset kalibrasyonu

<p align="center">
  <img src="assets/screens/framed/probe-calibration.png" width="360" alt="Kalibrasyonu başlatma">
  <img src="assets/screens/framed/probe-calibration-active.png" width="360" alt="Dört hareket düğmesi ve canlı Z">
  <img src="assets/screens/framed/probe-calibration-accepted.png" width="360" alt="Kabul edilen ofseti kaydetme">
</p>

1. Kalibrasyon için tablayı boşaltın. Ekran gerektiğinde XYZ eksenlerini home eder, güvenli geçiş için Z’yi yükseltir ve probu yapılandırılmış tabla merkezine götürür.
2. **Leveling → Probe Calibration → Start** açın.
3. Alt ve üst denenmiş konumların arasında canlı Z yüksekliğini izleyin. Düğmeyi çevirerek dört **-- / - / + / ++** butonundan birini seçin ve basarak Klipper'ın arama adımlarıyla hareket edin.
4. Uygunsa **Accept**, oturumu iptal etmek için **Cancel** seçin.
5. Accept sonrası kalıcı kayıt ve Klipper'ı yeniden başlatmak için **Save**, kaydetmeden çıkmak için **Continue** seçin.

Baskı durmuş olmalıdır. Bekleyen yapılandırma değişiklikleri kalibrasyonu engellemez. Kayıt yalnızca bekleyen değişiklik kabul edilen prob ofsetinden oluşuyorsa yapılabilir. Kayıt Klipper'ı yeniden başlatır; geçici çalışma Z ofsetinden ayrıdır.

<a id="ekran-ayarları"></a>
## Cihaz ayarları

Üst bar, Raspberry Pi'nin yerel sistem saatini **SS:DD** biçiminde gösterir.

<p align="center"><img src="assets/screens/framed/display.png" width="360" alt="Parlaklık ve boşta kısma"></p>

**Home → Device** açın:

| Ayar | Kullanım |
|---|---|
| Brightness | Normal parlaklık, %0–100; değişiklik düzenleme sırasında görünür |
| Idle dim | Off veya encoder girdisi olmadan 1–60 dakika sonra kısma |
| Dim brightness | Kısılmış parlaklık, %0–100; normal parlaklıkla sınırlanır |

Düzenlemek için basın, çevirin ve kaydetmek için tekrar basın. Ayarlar ekranın güç döngüsünde korunur. Varsayılanlar **%100**, **Off** ve **%10**'dur. Kayıt başarısızsa düzenleme açık kalır; yeniden denemek için basın.

Boşta kısma sonrası ilk encoder hareketi veya tıklama, menü işlemi yapmadan ekranı uyandırır. **%0 arka ışığı kapatır**; Brightness düzenlerken saat yönünde çevirerek tekrar artırın.

### Buzzer ve tuş sesleri

**Device → Buzzer** artık ayrı çıkış seçme ekranı yerine sesi doğrudan **Enabled/Disabled** olarak ayarlar. **Volume**, **Click tone**, **Encoder tone** satırları buzzer kapalıyken de düzenlenir. Basıp enkoderle değiştirin, yeniden basarak kaydedin. Volume %0–100 aralığında %10 adımlarla ayarlanır; %100 için fiziksel PWM duty %50'dir. Tonlar Off, Tick, Short beep, Low, High, Double. Ayarlar DWIN Flash'ta kalıcıdır.

Buzzer artık Raspberry Pi **donanımsal PWM** ile, Klipper `pwm_cycle_time`, `output_pin` veya Moonraker G-code kullanmadan çalışır. Fiziksel buzzer pini yalnızca `./configure.sh` → **Buzzer hardware PWM** üzerinden GPIO12/13/18/19 arasından seçilir. Kurucu device-tree overlay ve PWM servis erişimini hazırlar; boot ayarı değişmişse Pi'yi yeniden başlatın. NFC kart sesi asenkron Spoolman sorgusunu bekler: eşleşmede yalnız NFC_SPOOL_MATCH, eşleşme yoksa veya sorgu hatasında yalnız NFC_TAG_READ seçilir. Atama NFC_TAG_READ kullanır. Genel Buzzer Enabled/Disabled, Volume ve seçilen olay anahtarı geçerlidir; kapalı ses yerine başka ses çalmaz. Hızlı encoder hareketlerinde bekleyen ses kuyruğu birikmez.

### İsimli buzzer melodileri

Bütün nota dizileri `buzzer_melodies.py` içinde tutulur. Kütüphanede
`PRINT_DONE`, `HEATING_DONE`, `COOLING_DONE`, `ERROR`, `FILAMENT_OUT`, `BOOT`,
`SHUTDOWN`, `PAUSE`, `RESUME`, `LAYER_CHANGE`, `HOMING`, `PROBE_SUCCESS`,
`PROBE_FAIL`, `WARNING` ve `CUSTOM_EVENT` bulunur. Kısa, olaya özgü motifler ve açık sessiz beklemeler kullanılır. Mevcut UI tonları ve emergency
alarmı da aynı kütüphaneyi kullanır.

UI kodu `self._play_buzzer_melody('PRINT_DONE')`, mevcut oynatıcıya erişen diğer
kod `player.play_melody('PRINT_DONE', settings)` çağırabilir. Yeni PWM sahibi
başlatmak yerine tek oynatıcı yeniden kullanılır. Çalma asenkrondur; genel ses
anahtarına ve volume ayarına uyar, click/encoder tonu seçimine bağlı değildir.
Oynatıcı meşgulken normal istek reddedilir; `priority=True` normal sesi kesip
kuyruk biriktirmeden değiştirir. Emergency alarmının özel tam sesli öncelik yolu
korunur ve normal melodiler alarmı kesemez. Bilinmeyen isimler kuyruğa alınmadan
`ValueError` üretir.

On altı melodi uygulama ve abone olunan yazıcı olaylarına bağlanmıştır:

| Melodi | Tetikleyici |
|---|---|
| `PRINT_DONE` | Aktif baskının `complete` durumuna geçmesi; iptal sessizdir. |
| `PAUSE` | Aktif baskının `paused` durumuna geçmesi. |
| `RESUME` | `paused → printing`; ilk baskı başlangıcı sessizdir. |
| `ERROR` | Canlı baskının `error` olması veya Klipper shutdown bildirimi. |
| `BOOT` | Açılış tamamlanıp buzzer ayarları okunduğunda; işlem başına bir kez. |
| `SHUTDOWN` | Petrel kapatmasının onaylanması; güç isteği gönderilmeden hemen önce. |
| `HEATING_DONE` | Her ısıtıcının pozitif hedefine ulaşması; dashboard ile ortak 2 °C giriş / 3 °C çıkış histerezisi. |
| `COOLING_DONE` | Hedef tam sıfırken daha önce sıcak görülen ısıtıcının 50 °C, bed’in 40 °C altına inişi. |
| `HOMING` | Kalibrasyon hazırlığı dahil Petrel G28 komutunun korumalı yerel gönderime ulaşması. |
| `PROBE_SUCCESS` | Doğrulanmış mesh/vida ölçümü, kabul edilmiş manuel prob ofseti veya başarılı prob tanılaması. |
| `PROBE_FAIL` | Prob komutunun sunucu tarafından hata ile sonuçlanması veya başarısız prob tanılaması. |
| `LAYER_CHANGE` | Aynı aktif baskıda bildirilen `print_stats.info.current_layer` değerinin artması. |
| `FILAMENT_OUT` | Etkin Happy Hare’de ortak boolean `mmu.runout` alanının canlı `false → true` geçişi. |
| `NFC_TAG_READ` | Spoolman eşleşmesi olmayan kart (sorgu hatası dahil) veya emergency/spool ataması. |
| `NFC_SPOOL_MATCH` | Mevcut asenkron Spoolman sorgusunun eşleşen makarayı bulması. |
| `NFC_SHARE_DONE` | Etkin paylaşım popup’ını kapatan `share.ndef_transferred`; iptal veya hata değil. |

NFC ailesi ortak Do6/Mi6 başlangıcını kullanır: NFC_TAG_READ 135 ms’lik iki
notalı kısa imza, NFC_SPOOL_MATCH Sol6 ekleyen 290 ms’lik onay, NFC_SHARE_DONE
ise Sol6 üzerinden Do7’ye çözülen 430 ms’lik tamamlanma sesidir. Mevcut asenkron sorgu sonucu beklenir: eşleşen kartta yalnız NFC_SPOOL_MATCH,
eşleşme yoksa veya sorgu başarısızsa yalnız NFC_TAG_READ çalar. Atama sırasında
genel okutma sesi korunur. Seçilen ses kapalıysa diğer sese geçilmez.
Yeni sorgu, polling veya okuyucu işçisi eklenmez. Üçü de genel ses anahtarı ve
Volume ayarını kullanır; emergency davranışı değişmez. WARNING ve CUSTOM_EVENT
kütüphanede kalır, otomatik olaya bağlanmaz.

Mevcut WebSocket durum/lifecycle bildirimleri ve UI callback’leri kullanılır;
yeni polling, sorgu veya G-code makrosu eklenmez. İlk bağlantı, yeniden bağlantı
snapshot’ları ve tekrarlanan durumlar ses üretmez. Baskı hatası ve Klipper
shutdown aynı hata için tek ses üretir; sıradan bağlantı kaybı hata melodisi
değildir. Yeni bağlantı kurulduktan sonra eski oturumdan gecikmiş bildirimler
elenir. Ses mevcut sınırlı PWM işçisinde asenkron çalar; Buzzer Enabled/Disabled
ve Volume ayarlarına uyar. Emergency alarmının önceliği korunur.

Isıtıcılar çevrimlerini bağımsız izler; dashboard ile aynı `heater_ready()`
hesabı kullanılır. Hedef başına bir kez ses üretilir; dalgalanma tekrar kurmaz.
Soğuma takibi sıcak/kapalı durum gözlenince veya sıcak ısıtıcı kapatılınca kurulur;
ilk/yeniden bağlantıdaki soğuk snapshot eski bir soğumayı duyurmaz. Yeni hedef
önceki takibi değiştirir. Genel ısıtıcıların sıcaklık/hedef alanları mevcut
aboneliğe eklenir; güç telemetrisi termal test/kullanım izniyle sınırlı kalır.
Aynı anda gelen aynı bildirimler ses kuyruğu biriktirmek yerine birleşebilir.

Homing sesi yerel G28 gönderimini belirtir; motor hareketini kanıtlamaz, içeriği
bilinmeyen homing makrolarını veya başka istemcilerden başlatılanları kapsamaz.
Prob bildirimleri mevcut işlem sonuçlarından üretilir; yeni sorgu veya zamanlayıcı
eklenmez. Her temas yerine tüm işlem duyurulur. Vida ölçümünün başarılı olması
yatağın düz olduğu anlamına gelmez. Kullanıcı iptali, zaman aşımı, bağlantı kaybı
ve doğrulanamayan/bozuk sonuçlar prob hatası sayılmaz. Klipper shutdown genel
ERROR alarmını kullanır; özel emergency alarmının önceliği daha yüksektir.
Katman sesi, yalnız dilimleyici/makro katman bilgisini Klipper’a bildiriyorsa
çalışır. Z hareketinden tahmin edilmez; ilk geçerli değer başlangıç kabul edilir.
Tekrar, geriye sayım, iş değişimi, pause/resume ve yeniden bağlantı snapshot’ları
ses üretmez. Katman atlaması tek bildirim üretir; kaçırılmış katmanlar için ses
tekrarı yapılmaz. Layer changed kutusu bu sesi açıp kapatır; genel buzzer ve volume
ayarları da geçerlidir. Filament bitişi HH v3.0.1/v3.4.2 ve v4.0/v4.1’de ortak `mmu.runout`
sözleşmesini kullanır. Sürüm metninden tahmin yapılmaz; mevcut `mmu` aboneliği
yeterlidir. Alan eksik, boolean değil veya MMU devre dışıysa ses üretilmez.
İlk bağlantıdaki `true` başlangıç kabul edilir; yeniden bağlantıda çalınmaz.
Ham sensörler, gate doluluğu, pause nedeni metni ve `operation=runout` tetikleyici
değildir; sonuncusu clog/tangle durumunu da kapsayabilir. EndlessSpool sırasında
gerçek runout ses üretir, normal yükleme/boşaltma/değişim tek başına üretmez.
Runout bayrağı açıkken gelen PAUSE sesi bastırılır; aynı bildirimdeki genel ERROR
önceliklidir, emergency alarmının önceliği de korunur. Kapsam HH’nin bu bayrakla
bildirdiği runout işlemleridir; bütün sensör hata yolları değildir. Deprecated
alan ileride kaldırılırsa sensörlerden tahmin üretilmez. Ek polling, Klipper
extra’sı veya makro kurulmaz.

Kapanış melodisi güç isteğinden önce başlar; ses için kapatma geciktirilmez.
Pi’nin gücü de kesiliyorsa melodi yarıda kalabilir. Ani elektrik kesilmesinde
kapanış sesi garanti edilemez. Diğer melodiler otomatik olay bağlantısı
olmadan isimle çağrılabilir.

### Olay seslerini açma ve kapatma

**Device → Event sounds** altında 18 bağımsız checkbox bulunur: yukarıdaki on altı olay, **Emergency card alarm** ve **Power button hold**. Enkoderle olayı seçip basarak açıp kapatın. İlk kurulumda ve geçerli kayıt bulunmayan güncellemelerde hepsi varsayılan açıktır. WARNING ve CUSTOM_EVENT yalnız melodi kütüphanesinde kalır.

Her değişiklik DWIN Flash'a otomatik kaydedilir ve geri okunarak doğrulanır. Kayıt sürerken son doğrulanan seçimler geçerlidir. **Not saved** durumunda önceki seçimler korunur; tekrar basarak kaydı deneyin. **Retry read** ayarları yeniden okur. `0x0480` adresindeki ayrı, CRC korumalı 16 baytlık kayıt mevcut ekran ve buzzer ayarlarını korur.

Ana Buzzer anahtarı bütün sesleri susturmaya devam eder. Normal olay melodileri Volume ayarını kullanır. Acil durum alarmı açıkken tam sesle çalar; kendi kutusunu kapatmak yalnız alarmı susturur, **acil durdurma işlemini devre dışı bırakmaz**. Tuş ve enkoder tonları mevcut ayarlarını kullanmaya devam eder.

**Power button hold**, dört kısa sesi birlikte kontrol eder: basılı tutma çubuğu açılınca başlangıç, çizilen her ilerleme adımında 7 ms tık, dolunca farklı bir hazır tonu ve erken bırakınca alçalan iptal sesi. Normal kısa basış bu sesleri üretmez. Gecikmiş adımlar için ses birikmez; çubuk dolunca yine bırakmak ve mevcut ayrı kapatma onayını vermek gerekir. Dört ses de genel ses anahtarı/seviyesine uyar, acil alarmı kesemez. Yeni bit mevcut Flash kaydına sona eklenir; önceki seçimler korunur ve bu seçenek varsayılan açıktır.

![Olay sesi seçimleri](assets/screens/event-sounds.png)
![RFID, NFC ve acil durum sesi seçimleri](assets/screens/event-sounds-nfc.png)

### Klipper sanal buzzer (isteğe bağlı extra)

Kconfig'teki **Klipper virtual buzzer → Virtual SET_PIN Buzzer Klipper extra** seçeneği ilk yapılandırmada **varsayılan açıktır**. Apply edildiğinde Petrel, Klipper extras klasörüne kaynak dosyasının sembolik bağlantısını kurar, yönetilen `petrel-buzzer.cfg` parçasını oluşturur ve `printer.cfg` dosyasına include ekler. Klipper **otomatik yeniden başlatılmaz**; yazıcı boşta iken elle restart uygulayın. Kconfig seçeneği kapatılırsa yalnız Petrel tarafından yönetilen dosyalar temizlenir.

**Klipper'ı yeniden başlatmadan önce eski `[pwm_cycle_time Buzzer]` bölümünü kendiniz silin.** Petrel bu bölümü silmez; aksi halde iki modül `PIN=Buzzer` adına kaydolmaya çalışır. Yeni bölüm:

```ini
[petrel_buzzer Buzzer]
socket_path: /home/YOUR_USER/.config/Petrel/klipper-buzzer.sock
value: 0
shutdown_value: 0
cycle_time: 0.001
```

Bu bölüm installer tarafından gerçek mutlak kullanıcı yolu ile otomatik yazılır; elle ikinci kopya eklemeyin. Mevcut G-code makroları **değişmeden çalışır**:

```gcode
SET_PIN PIN=Buzzer VALUE=0.5 CYCLE_TIME=0.001
G4 P200
SET_PIN PIN=Buzzer VALUE=0
```

`VALUE`, doğrudan **fiziksel PWM duty oranıdır** (0–1); `scale` ayarlanmışsa değere ölçek uygulanır. `CYCLE_TIME` saniye cinsinden periyottur (0.00005–1 s); verilmezse yapılandırmadaki varsayılan kullanılır. UI'daki volume ayarının aksine `VALUE=0.5` tam %50 PWM duty üretir. Eski Jinja durum nesnesi isimleri için uyumluluk sağlamıyoruz.

Klipper extra'sı komutları Petrel'in tek PWM işçisine, **özel yerel Unix datagram socket** üzerinden gönderir. **Device → Buzzer Disabled** Klipper tonlarını da susturur; UI Volume ve ton ayarları Klipper'ın açıkça belirttiği VALUE değerini yeniden ölçeklemez. Petrel çalışmıyorsa G-code akışını bloke etmez. LCD bildirimleri Klipper tonuna kısa süreli öncelik alabilir; acil durum NFC melodisi tüm tonları keserek özel öncelik kazanır. Klipper shutdown anında `shutdown_value` gönderilir; aktarım kaybolursa harici PWM için 30 saniyelik güvenlik zaman aşımı vardır. Özel socket erişimi için Petrel ve Klipper'ın aynı Linux kullanıcısı ile çalışması önerilir. Klipper shutdown durumundayken LCD bildirimleri bağımsızdır.

### NFC okuyucu ayarları

**Device → NFC settings** menüsü `configure.sh` sırasında NFC'nin etkin olup
olmadığını gösterir. Kurulumda açılmadıysa NFC satırları görünür ama odaklanıp
değiştirilemez. `configure.sh` ile NFC'yi açıp Petrel'i yeniden başlattığınızda
ayarlar kullanılabilir. Libnfc okuyucu ailesini, o ailenin arayüzünü, sistemde
mevcut port/aygıtı ve haberleşme hızını seçip **Save**'e basın. Her ayara
basıldığında ayrı bir kaydırılabilir seçenek listesi açılır; enkoderle
seçeneğin üzerine gelip basınca seçim NFC ayar ekranına aktarılır.
**Back** seçimi değiştirmeden döner. Ana ekranda seçili değerler
satırların sağında gösterilir; uzun aygıt adları özet satırında
kısaltılır, seçim listesinde ayırt edilebilir biçimde görünür.
**NFC feature** bilgisi, Info ekranındaki gibi salt okunur durum
göstergesidir (yeşil **Enabled**, kurulumda kapalıysa soluk **Disabled**).
Etiket standart menü sütununda, değer sağa hizalıdır; menü ikonu,
işlem satırı ayracı veya enkoder odağı bulunmaz. Pasif NFC
ayarlarında da enkoder her çevrildiğinde liste bir satır kayar; böylece
**Save** ve **Test connection** satırlarına kadar ulaşılır. Pasif satırlar
odaklanamaz ve çalıştırılamaz; sıradaki etkin satıra gelince odak geri gelir.
Okuyucu veya arayüz değişince alt seçimler sıfırlanır. UART listesi Moonraker'ın
`/machine/peripherals/serial` API'sinden gelir: her cihazın yalnızca ana
`device_path` yolu görünür; `/dev/serial/by-id`, `/dev/serial/by-path`
ve `/dev/serial0` takma adları ayrı seçenekler olmaz. Liste yalnızca
**Port / device** alt menüsüne girilince arka planda yenilenir ve gerekirse
kısa süreli **Loading...** durumu gösterilir. Moonraker hatasında veya boş
yanıtında eski /dev taramasına geri dönülmez. I2C/SPI mevcut Linux aygıt
düğümlerinden; USB, PC/SC ve NCI kurulu libnfc'nin gerçekten bulduğu
aygıtlardan alınır. Bu arayüzlerde hız ayarı yoktur. Seçimler Petrel
kullanıcısının özel yapılandırma dizininde saklanır ve seçilen bağlantı kaydedince
arka plan okuyucusuna uygulanır. Hız ayarı yalnızca UART için değiştirilebilir.
Libnfc I2C, SPI, USB, PC/SC ve NCI için bu ayarı uygulamadığından hız satırı
pasiftir ve odaklanamaz.

**Test connection**, **Save** altındaki son seçenektir ve model, arayüz,
aygıt seçildikten sonra etkinleşir. Dosyaya kaydetmeden *ekranda seçili*
değerleri sınar. Ekranda önce **Wait**, ardından yeşil **OK** veya
kırmızı **Fail** görülür. Ortak libnfc API'si, karta ihtiyaç duymadan seçilen
okuyucuyu açar ve initiator modunda başlatır; kart okuma kalitesini veya
RF menzilini doğrulamaz. Test, Petrel'in mevcut RFID iş parçacığında
seri olarak yürütülür; aktif taramayla aynı anda ikinci libnfc oturumu
açılmaz ve ekran/enkoder bloke edilmez. Test sürerken kaydetme ertelenir.
Test tamamlandığında kayıtlı ayarlar değişmez; hatalar günlüklenir.

Liste libnfc sürücü ailelerini gösterir; tüm üreticilerin kart adlarını ayrı ayrı
listelemez. Upstream libnfc'de PN532 UART, I2C ve SPI arayüzlerini destekler;
kurulu derlemenin etkin sürücüleri kullanılabilir seçenekleri belirler.

Ses ayarına basın, çevirmeyle değiştirin ve tekrar basarak kaydedin. Ses seviyesi %0–100 arasında 10’ar adımla değişir. Tonlar Off, Tick, Short beep, Low, High ve Double seçeneklerini içerir. Çıkış ve ses tercihleri yeniden başlatmada korunur. Sesler arka planda çalar; hızlı çevirmelerde birikmez. Seçili section Klipper yapılandırmasından kaldırılırsa kullanılabilir bir çıkış seçilene kadar ses kontrolleri gizlenir.

## Maintenance

Yazıcı boştayken **Home → Maintenance** açın. Görünen kontroller ve cihazlar keşfedilen yazıcı yapılandırmasına göre belirlenir. Ekran etiketleri İngilizce kalır.

<p align="center"><img src="assets/screens/framed/maintenance.png" width="360" alt="Bakım ilerlemesi ve dört sabit bölümle Maintenance özeti"></p>

Giriş ekranı en yakın veya zamanı gelmiş iki bakım planını gösterir. Plan ve öneri sayısı artsa da dört bölüm aynı yerde kalır:

| Bölüm | Kullanım amacı |
|---|---|
| **Care schedule** | Tüm kayıtlı hatırlatıcılar, ilerlemeleri ve tamamlanan bakımı kaydetme |
| **Check printer** | Amaç/cihaz bazında kılavuzlu kontroller ve desteklenen kalibrasyonlar |
| **Diagnostics** | İstek üzerine okumalar, kullanım/geçmiş ve destek araçları |
| **Recommendations** | Cihaz bazında güncel kayıtlı sorunlar ve kullanılabilir sonraki kontroller |

Görseller güncel arayüzü örnek controller kayıtları ve ölçümlerle gösterir; yeni fiziksel test sonucu değildir. Yazıcınızdaki seçenekler ve değerler farklı olabilir.

### Care schedule: periyodik bakım

<p align="center">
  <img src="assets/screens/framed/maintenance-care.png" width="360" alt="Birden fazla kayıtlı planla bakım takibi">
  <img src="assets/screens/framed/maintenance-care-scrolled.png" width="360" alt="Kaydırılabilir alandaki diğer bakım planları">
</p>

Çubuk, belirlediğiniz aralıkta geçen süreyi gösterir; parça aşınmasını veya kalan ömrü ölçmez. **Due**, bu aralığın dolduğunu belirtir. Kayıtlı başlangıçtan beri örneklenen kullanım çubuğu doldurur; eksik/sıfırlanmış okumada ilerleme uydurulmadan takip duraklatılır. Tüm planlara enkoderi çevirerek ulaşabilirsiniz; **Back** üstte kalır.

1. **Care schedule → Add reminder** açın. Desteklenen cihazı, bakım işini ve sunulan hatırlatma esasını seçin.
2. Üreticinin bakım rehberine göre aralığı belirleyin, inceleyin ve açıkça kaydedin. Editörün başlangıç değeri değiştirilebilir kontrol önerisidir; kurulmuş bir bakım planı veya üreticinin onaylı parça ömrü değildir.
3. Bakımı gerçekten yaptıktan sonra planı açıp **I completed this service → Yes, record completion** seçin. Bu işlem bakım tarihini kaydeder; donanım testine başarılı sonucu vermez.
4. Kayıtlı planları yeniden yüklemek için **Refresh records** kullanın. Yükleme/kayıt hatası başarı gibi gösterilmez.

Örneklenmiş baskı/açık kalma saatleri yalnız kaydedilen dönemi kapsar ve alt sınırdır. Değerin aralığın altında olması bakımın henüz gerekmediğini kanıtlamaz.


<p align="center">
  <img src="assets/screens/framed/maintenance-care-device.png" width="176" alt="Bakım cihazı seçimi">
  <img src="assets/screens/framed/maintenance-care-class.png" width="176" alt="Hotend bakım sınıfları">
  <img src="assets/screens/framed/maintenance-care-basis.png" width="176" alt="Takvim, saat ve filament uzunluğu ölçütleri">
  <img src="assets/screens/framed/maintenance-care-interval.png" width="176" alt="Filament uzunluğu bakım aralığı düzenleme">
</p>
<p align="center">
  <img src="assets/screens/framed/maintenance-care-review.png" width="176" alt="Hatırlatıcı gözden geçirme">
  <img src="assets/screens/framed/maintenance-care-detail.png" width="176" alt="Kayıtlı bakım hatırlatıcısı">
  <img src="assets/screens/framed/maintenance-care-complete.png" width="176" alt="Tamamlanan gerçek bakımı onaylama">
  <img src="assets/screens/framed/maintenance-care-remove.png" width="176" alt="Hatırlatıcı kaldırmayı onaylama">
</p>

### Kontrol çalıştırma ve sonucunu okuma

<p align="center">
  <img src="assets/screens/framed/maintenance-checks.png" width="360" alt="Amaca göre gruplandırılmış kontroller">
  <img src="assets/screens/framed/maintenance-prepare.png" width="360" alt="Fan kontrolünden önce hazırlık">
  <img src="assets/screens/framed/maintenance-result.png" width="360" alt="Ayrı Details işlemiyle kaydedilen fan gözlemi">
</p>

1. **Check printer** açın; grubu ve gereken kontrolü/cihazı seçin.
2. Hazırlığı okuyup **Prepare check** seçin. Bu adım donanımı çalıştırmaz.
3. Ayrı onay ekranını inceleyip **Start check**, homing gerekiyorsa **Home axes and continue** seçin.
4. Sensör, fiziksel gözlem veya ölçüm talimatlarını izleyin. Komut verilen mesafe yerine gerçekten ölçtüğünüz mesafeyi girin. Kullanıcı yanıtında zaman aşımı yoktur.
5. Sonuç başlığını ve **What this means** açıklamasını okuyun. İsteğe bağlı ölçümler için **Details**, başladığınız cihaza dönmek için **Back to checks** seçin.

Kayıtlı kullanıcı gözlemi, ölçüm ölçütü ve tamamlanamayan kontrol farklı anlam taşır. Tamamlanan bir kontrol tüm işlevleri veya parçanın kalan ömrünü belgelemez. Fan başlangıç turlarında fanın fiziksel olarak tamamen durduğunu açıkça onaylamanız gerekir.

**Etkin ısıtmayı durdurmak Klipper güvenlik shutdown isteği gönderir.** Basmadan önce durdurma eylemini okuyun. Kalibrasyon değişiklikleri otomatik kaydedilmez. Günlük prob offset, vida ayarı ve bed mesh araçları **Leveling** altında kalır.

### Ölçümler ve diagnostik

<p align="center">
  <img src="assets/screens/framed/maintenance-diagnostics.png" width="360" alt="Sistem okumaları, kullanım/geçmiş ve destek araçları">
  <img src="assets/screens/framed/maintenance-host.png" width="360" alt="Etiket ve değer gruplarıyla host ölçümleri">
  <img src="assets/screens/framed/maintenance-host-page-2.png" width="360" alt="Enkoderle kaydırılmış diagnostik rapor">
</p>

**Diagnostics** açın; bir grup ve okumayı seçin. Bilgi arka planda alınır ve doğrudan rapor olarak açılır. Başlık okumayı tanımlar; ölçümler etiket, değer ve birimi birlikte gösterir. Bilgi alanları seçilebilir menü öğesi değildir.

Tüm Maintenance raporlarında enkoderi çevirerek dikey kaydırın; Next/Previous düğmesi gerekmez. Son konumdan başa, baştan ters yönde çevirince sona dönülür. **Back** ve rapor başlığı sabit kalır. Bilgiyi okurken basmak Back üzerinden döner; gerçek rapor işlemleri içerikten sonra odak alır ve basılarak çalışır. Sağdaki çubuk konumu gösterir; ortak dashboard korunur.


<p align="center">
  <img src="assets/screens/framed/maintenance-usage-menu.png" width="176" alt="Kullanım ve geçmiş menüsü">
  <img src="assets/screens/framed/maintenance-usage-component.png" width="176" alt="Kayıtlı komponent kullanım miktarları">
  <img src="assets/screens/framed/maintenance-sensor-list.png" width="176" alt="Sensör diagnostik listesi">
  <img src="assets/screens/framed/maintenance-sensor-report.png" width="176" alt="Filament sensörü diagnostik ayrıntısı">
</p>

Kayıtlı hatırlatıcıyı silmek için **Care schedule** içinde açıp **Remove reminder** seçin ve ayrı ekranda onaylayın. Varsayılan seçim **Keep reminder** olur. Kullanım sayaçları ve tamamlanan bakım geçmişi korunur.

Desteklenen fan, ısıtıcı, çıkış ve LED nesneleri kendi kullanımlarına göre **Sampled powered hours** seçeneğini otomatik sunar. Örnekleme menünün açık olmasına bağlı değildir. S12 ekranında saklanan kullanım miktarları görünür; takip/kapasite verileri ek satır olarak gösterilmez; bkz. [Komponent kullanım takibi](maintenance-usage_TR.md).

**Diagnostics → Usage and history** altında kayıtlı baskı kullanımı, örneklenmiş bileşen kullanımı ve son kontrol geçmişi bulunur. Geçmiş kanıtlar **HISTORY** olarak işaretlenir; güncel donanım sağlığını anlatmaz. **Support tools** isteğe bağlı kayıt ve diagnostik rapor aktarımını içerir; kaydı açmak kontrol başlatmaz.

### İnceleme gerektiren sonuçlar ve öneriler

<p align="center">
  <img src="assets/screens/framed/maintenance-thermal-result.png" width="360" alt="Belirgin inceleme mesajıyla ısıtma sonucu">
  <img src="assets/screens/framed/maintenance-evidence.png" width="360" alt="İsteğe bağlı etiketli ısıtma ölçümleri">
  <img src="assets/screens/framed/maintenance-recommendation.png" width="360" alt="Sonraki işlemlerden ayrı öneri açıklaması">
</p>

Dikkat gerektiren sonuç, sonraki işlemleri sunmadan önce neyin ölçüldüğünü açıklar. Örneğin yüksek sıcaklık aşımı, sıcaklık kontrolünü incelemenizi ister; otomatik olarak ısıtıcı eskimesi tanısı koymaz. Desteklenen PID kalibrasyonu yalnız aynı ısıtıcı için kayıtlıysa sunulur.

**Recommendations** güncel kayıtlı bulguları cihaz bazında toplar. **What to review** açıklamasını okuyup gerekiyorsa sunulan kontrolü seçin. Ek metne rapor sayfalarından ulaşılır. Öneri bulunmaması güncel kayıtlı uyarı olmadığı anlamına gelir; tüm parçaların sağlıklı olduğunu göstermez.

Tam bir ısıtma sonucunda **Heating speed reference** sunulabilir. Yalnız sağlam çalıştığı bilinen yanıtı açık onayla kaydedin. Karşılaştırma aynı donanım/soğutma koşullarını ve sizin seçtiğiniz inceleme sınırını gerektirir; bu sınır üreticinin aşınma eşiği değildir. Donanım değişince referansı kaldırın.

[Güncel ekran galerisini](screenshots_TR.md#maintenance-testleri-bakım-ve-diagnostik), [LCD etkileşim ayrıntılarını](maintenance-ui_TR.md), [çıkış profillerini](maintenance-profiles_TR.md) ve [fiziksel kabul çizelgesini](maintenance-reference-printer-acceptance_TR.md) inceleyin. Backend kabulü ve CI görselleri bu arayüzün fiziksel kabulünün yerine geçmez.

## Info ve güncellemeler

<p align="center">
  <img src="assets/screens/framed/info-overview.png" width="360" alt="Makine, Wi-Fi ve host">
  <img src="assets/screens/framed/info-mcu-details.png" width="360" alt="MCU durumu">
  <img src="assets/screens/framed/info-mcu-overview.png" width="360" alt="MCU ve yazılım bölümleri">
  <img src="assets/screens/framed/info-software.png" width="360" alt="Yazılım sürümleri">
</p>

**Home → Info** veya **Control → Info** açın; Machine, Host, MCUs ve Software bölümlerini kaydırmak için çevirin. Yazıcı boyutlarını, ağ/IP'yi, Wi-Fi adını/sinyalini, CPU/RAM/sıcaklığı, MCU bağlantısını/yükünü/sıcaklığını ve kurulu yazılım sürümlerini kontrol edin. Bulunamayan değerlerde `N/A` veya kullanılamıyor durumu gösterilir. MCU sıcaklığı yapılandırılmış `temperature_mcu` kaynağı, Wi-Fi ayrıntıları Linux `iw` gerektirir.

<p align="center">
  <img src="assets/screens/framed/info-project.png" width="360" alt="Proje QR ve güncelleme kontrolü">
  <img src="assets/screens/framed/info-update-checking.png" width="360" alt="Güncelleme kontrol ediliyor">
  <img src="assets/screens/framed/info-update-current.png" width="360" alt="Güncel">
</p>

Repoyu açmak için proje QR kodunu tarayın. Bağlı NFC okuyucu Type 4 NDEF
URI etiket taklit desteğini doğrulamışsa Software bölümündeki Petrel sürüm
numarasının hemen önünde küçük NFC paylaşım ikonu otomatik görünür. Turkuaz
odak çerçevesi görünene kadar kaydırıp basınca bekleme popup'ı açılır;
telefonu okuyucuya yaklaştırınca aynı Petrel repo bağlantısı
(`https://github.com/sezgynus/Petrel`) NDEF URI olarak sunulur.
NDEF verisinin tamamı başarıyla iletildiğinde popup kendiliğinden kapanır;
bu, telefonun tarayıcıyı açtığı anlamına gelmez. Enkodere basmak işlemi iptal
eder. Desteklenmeyen, bağlantısı kopmuş veya yeteneği henüz keşfedilmemiş
okuyucuda düğme tamamen gizlenir. Hata popup'ta gösterilir; basarak kapatılır.
Bu görünürlük ve paylaşım denetimi bütün ekranlarda tekrar kullanılabilecek,
yalnız NFC Core'a bağlı ortak UI bileşenindedir.
LCD'den güncellemek için:

1. Yazıcıyı boşta bırakın ve **Check for updates** düğmesine kaydırın. Encodere basın.
2. **Checking…** aşamasını bekleyin. Yeşil **Up to date** güncelleme gerekmediğini gösterir; güncelleme varsa düğme **Update** olur.
3. Petrel'i yüklemek için **Update** seçin. Moonraker ardından servisi yeniden başlatır. Bu işlem tüm yazıcı bileşenlerini güncellemez.

Repo kirli veya geçersizse **Soft recovery**, ikinci bir **Confirm recovery** adımı sunar. Kurtarma yerel repo değişikliklerini siler; gerekenleri önceden yedekleyin. Çevirmek onayı iptal eder. Kurtarma otomatik güncelleme yüklemez. Sonuç doğrulanmamışsa tekrar denemeden önce Mainsail Update Manager'dan kontrol edin.

Info sağda sabit konum çubuğu kullanır. Kaydırmada yalnız açılan içerik, değişen değer ve dar çubuk kenarı yenilenir; olmayan alanlar uydurulmaz.

## Kabin ışığı

<p align="center"><img src="assets/screens/framed/case-light.png" width="360" alt="Case Light"></p>

**Control → Case Light**, yapılandırılmış `output_pin case_light` için görünür. On/Off kullanın ve PWM parlaklığı %0–100 ayarlayın. On son pozitif parlaklığı, bilinmiyorsa %100'ü geri getirir. Makro gerekmez.

PWM destekli çıkış aşağıdaki gibi ayarlanabilir; `PA3` yerine gerçek ışık kontrol pininizi yazın:

```ini
[output_pin case_light]
pin: PA3
pwm: True
value: 1.0
shutdown_value: 0
cycle_time: 0.01
```

## Yazıcı gücü

<p align="center">
  <img src="assets/screens/framed/power-confirm.png" width="360" alt="Güç kapatma onayı">
</p>

Moonraker güç aygıtı adını `./configure.sh` ile ayarlayın. Açmak için encoder düğmesini basılı tutun; varsayılan süre **2 saniye**. Pi/servis ve Moonraker erişilebilir kaldığı sürece Klipper veya ekran çevrimdışıyken de çalışır.

Her ekrandan kapatma onayına ulaşmak için encoder düğmesini **1,2 saniye basılı tutup bırakın**. İlk 450 ms boyunca gösterge çıkmaz; ardından küçük **Hold for power** penceresi açılır ve içindeki çubuk dolar. **Cancel başlangıçta seçilidir**; saat yönünde çevirerek **Power off** seçin ve ayrı bir kısa basışla onaylayın. Cancel aynı ekrana ve kaydedilmemiş düzenleme değerine döner. Baskı, duraklatılmış baskı veya süren işlem sırasında kapatma engellenir. Kısa basış bırakıldığı anda çalışır; ek bekleme yoktur. 450 ms–1,2 saniye arasında bırakılan yarım uzun basış menüyü tetiklemez.

Pi çalışmaya devam ederken röle yazıcı ve ekranı birlikte besliyorsa, yeniden güç açıldığında ilk ana ekran sayfasına dönülür. Menüleri kullanmadan önce açılışın bitmesini bekleyin.

Yapılandırılmış Moonraker güç cihazı açıldığında Petrel, LCD için 150 ms aralıklarla bloklamayan handshake denemelerini başlatır. Bu cihaz yoksa aynı hızlı bağlantı penceresini Klipper’ın hazır duruma geçmesi tetikler. 10 saniye yanıt alınamazsa handshake istekleri 5 saniye aralığa döner. Bağlantısı doğrulanan panel, sabit 750 ms uyanma beklemesi olmadan kullanılır.

### Güç akış örneği

![Güç için basılı tutma, bırakma, yarım basışın iptali ve aktif baskı engeli](assets/framed/power-shortcut-demo.gif)

Örnek verilerle gerçek UI emülatörü çıktısıdır. [Özgün panel PNG'leri](screenshots_TR.md) ve [yeniden üretim](ui-emulator_TR.md#png-çerçeve-ve-gif-yenileme).

<a id="nfc-ve-rfid-deneysel"></a>
### NFC ve RFID

**Info içindeki NFC durum bölümü** ve **Home → NFC**, ctypes üzerinden doğrudan libnfc C API'sini
kullanan tek bir arka plan yöneticisini paylaşır. `nfc-poll`, `nfc-scan-device`,
shell veya konsol çıktısı ayrıştırıcısı kullanılmaz. Diğer NFC araçları kapalı
olmalıdır. Sistem libnfc paylaşımlı kütüphanesi gerekir; Pi'de derleyici veya
geliştirme başlıkları gerekmez. Okuyucu **Device → NFC settings** içinden
seçilir. libnfc sembol bağlamaları Petrel sürecinde yalnız bir kez oluşturulup
tekrar kullanılır; okuyucu context ve handle'ları ise oturum bazında açılıp
kapatılır. Ayar modülü USB/PCSC/NCI için doğrudan libnfc keşfi başlatmaz;
keşif yalnız NFC Backend worker üzerinden sıraya alınır. NFC Backend yalnızca kayıtlı ve doğrulanmış
`nfc-settings.json` ayarlarını kullanır; `PETREL_NFC_DEVICE` değişkeni veya
sabit bir UART adresine geri dönüş yoktur. NFC devre dışıysa ya da geçerli
okuyucu kaydı yoksa libnfc aygıtı açılmaz. Backend mevcut Petrel sürecinde tek
worker ve tek donanım sahibi olarak iki ekran tarafından paylaşılır.
**Save** seçimi UI thread'ini bloke etmeden yeniden yapılandırma bildirimi
gönderir. Save, bağlantı testi, aygıt keşfi ve paylaşım istekleri devam eden libnfc
taramasını keser; backend worker eski oturumu kapatmadan başka bir işlem için
okuyucuyu kullanmaz. Donanım bağlantısı kopunca mevcut kart ve bekleyen algılama
bildirimi temizlenir, kaldırılma olayı yayımlanır; aynı kart yeniden bağlanınca
yeni bir algılama olayı üretilebilir. Kimlik bağlantı başına bir kez okunur,
yeniden bağlantıda yenilenir.
Info model, firmware, libnfc sürümü ve desteklenen A/B/FeliCa protokollerini gösterir.
PN532 modül kartının revizyonunu bildirmez; Hardware alanı **Not reported** olur.
Info ve RFID ekranlarının NFC verileri yalnız Core önbelleğinden gelir.
Info'daki NFC alanları UI zamanlayıcısıyla değil `reader.changed` ve
`capabilities.changed` olaylarıyla yenilenir. Aygıt keşfi, bağlantı testi ve
kayıtlı ayarları uygulama da Core üzerinden geçer. libnfc handle'larını yalnız
backend yönetir; UART port seçenekleri yine Moonraker seri API'sinden gelir.

RFID, okuyucunun libnfc üzerinden bildirdiği tüm initiator teknolojilerini tarar:
ISO14443A/B, B', ST SRx, ASK CTx, iki hızda FeliCa, Jewel/Topaz, NFC Barcode,
iClass/PicoPass ve destekleniyorsa pasif NFC-DEP. Type A seçimi 106 kbps ile başlar;
yüksek haberleşme hızları seçimden sonra görüşülür. Her sırada tek aktivasyon
denemesi yapılır; ek sleep, AutoPoll periyodu veya kartın kaldırılmasını bekleme
yoktur. Başlangıçta diğer teknolojilerin arasına Type A taraması konur; kart
bulununca bu ek sıralar son okunan kartın teknolojisine verilir. Diğer tüm
bildirilmiş modlar sırayla ilerlemeye devam eder. RFID ekranı yalnız NFC Core
olaylarıyla yenilenir; normal yazıcı/durum işleri 500 ms aralıkta kalır.
Aynı aygıt bağlantısı açık kalır. Tüm protokollerin turu gerçek RF/aktarım
süresi gerektirir; mutlak algılama gecikmesi veya eşzamanlı tarama vaat edilmez.
Firmware'in reddettiği bildirilmiş modlar loglanır; durum kısmi desteği belirtir.
Bağlantı hatasında iki saniye beklenip yeniden bağlanılır.

NFC Backend bağlı libnfc aygıtının ISO14443A Target Mode ve desteklenen
target bit hızlarını sorgular; `ndef_uri_emulation` özelliğini Core üzerinden
evet/hayır/bilinmiyor olarak sunar. Info bölümünde **NFC Sharing** görünür.
Desteklenmeyen, durumu bilinmeyen veya bağlantısı olmayan donanımda URI
paylaşım eylemi gösterilmemelidir. USB/PCSC/NCI cihaz keşfi NFC Backend'in
tek donanım worker'ında sıralanır; NFC Settings arayüzü yalnız asenkron keşif
sonucunu kullanır. `share_ndef_uri(url)` başlatılınca normal
kart taraması geçici durur, salt okunur NFC Forum Type 4 NDEF URL etiketi
taklit edilir; ancak **NDEF dosyasının tüm baytları başarıyla gönderildiğinde**
`share.ndef_transferred` olayı oluşur. Bu, telefonda tarayıcının açıldığı
anlamına gelmez. İptal, hata veya başarılı aktarım sonunda normal taramaya
dönülür. Paylaşım sırasında global RFID kart işlevleri duraklar.

### PN532 Type 4 NDEF emülasyonu

Petrel, dağıtımın değiştirilmemiş `libnfc.so.6` paketini kullanır.
PN532 Type 4 hedef emülasyonu, upstream `TgInitAsTarget` Mode `0x05`
ve sabit ATQA `00 04` ile çalışır; bunlar kullanıcı tarafından
seçilen profiller değildir.

Petrel, her PN532 target aktivasyonundan önce libnfc'nin dışarı aktardığı
`pn53x_write_register` fonksiyonuyla `CIU_Mode (0x6301)` register'ının
`ModeDetOff` bit 2'sine maskeli yazma isteği ekler. libnfc, sonraki
PN532 komutunu gönderirken write-back cache'ini uygular. Sistem
libnfc'de ilgili sembol yoksa PN532 target oturumu açıkça hata verir;
sessizce farklı RF davranışına geçmez. Diğer NFC okuyucularına
bu PN532'ye özel register komutu uygulanmaz. Özel `.so`, kaynak kod
yaması, derleyici, profil seçimi veya `.enabled` dosyası gerekmez.
Kurulumda NFC desteğinin etkin olup olmadığına dair mevcut seçenek korunur.

NDEF tamamlandıktan sonra telefonun ek Type 4 SELECT/READ işlemleri
için bağlantı, son APDU'dan itibaren en fazla 2 saniyelik sessizlik
süresine kadar açık tutulur. Başarı olayı yalnızca bir kez üretilir;
Android sisteminin URL açma akışı tamamlanabilir. Sistem libnfc ile
gerçek PN532 + Android testinde yirmi okutmanın hiçbirinde yanlış
FeliCa algılaması görülmedi; bir kez aralıklı target aktivasyon `-1`
hatası oluştu. Bunun kök nedeni henüz belirlenmedi.

Eski deneysel derlemeleri ve işaretleri *Petrel güncellendikten sonra*
Petrel servis kullanıcısıyla temizlemek için (komutlara sudo eklemeyin):

```bash
cd ~/Petrel
python3 tools/cleanup_nfc_experiments.py
python3 tools/cleanup_nfc_experiments.py --apply
sudo systemctl restart Petrel.service
```

Temizlik, yalnızca mevcut kullanıcının XDG config/data dizinlerindeki
bilinen PN532 deney kütüphanelerini, geçici derleme dizinlerini ve
profil/etkinleştirme işaretlerini siler. Sistem `libnfc6` paketi, NFC
cihaz ayarları ve diğer Petrel verileri korunur. İlk komut önizlemedir;
her iki komut da üretim sistem-libnfc yapılandırması yoksa durur.

NFC Core, NFC Backend olaylarını tek noktadan alır; bağlama özel, öncelikli,
tüketilebilir `card.detected`/`card.removed` olaylarını dağıtır. Global
emergency-stop eşleşmeleri normal bağlamlardan önceliklidir ve Moonraker'ın
öncelikli `printer.emergency_stop` isteğini kullanır. Kullanıcının atayabileceği
eşleşmeler `~/.config/Petrel/nfc-actions.json` dosyasına yazılır; özel G-code
çalıştırılamaz ve **fiziksel acil durdurmanın yerine geçmez**.
RFID ekranı artık 50 ms aralıklarla kart sorgulamaz ve periyodik çizilmez:
Core mevcut LCD olay kuyruğuna bildirim gönderir, yalnız LCD iş parçacığı
değişen kart verisini çizer. libnfc'nin alttaki RF taraması hâlen sürmektedir;
PN532'den kendiliğinden UART olayı yöntemi henüz uygulanmadı.


Son kartın protokolü, tam UID/ID'si (32 bayta kadar), ATQA ve SAK canlı güncellenir;
kart uzaklaşınca kimlik kalır. Her kart sunumunda asenkron sorgudan sonra tek ses seçilir: makara eşleşmesinde NFC_SPOOL_MATCH, diğer durumlarda NFC_TAG_READ (sorgu hatası dahil). Atama NFC_TAG_READ kullanır. Genel buzzer anahtarı, Volume ve seçilen olay anahtarı geçerlidir; click/encoder tonu bağımsızdır ve kapalı ses yerine başka ses çalmaz.
Tutulan kart bir kez öter; kendi
teknolojisindeki iki başarısız tarama aynı kart için yeniden bipi etkinleştirir. Kimlikler UUID değildir; ATQA/SAK kesin MIFARE çipini
kanıtlamaz. Yalnız değişen alanlar çizilir; kart belleğine veya diske yazılmaz.
Sayfadan çıkılınca tarama sürer; kapanışta bekleyen libnfc I/O'su iptal edilip port
kapatılır. Üst bardaki Back okunu seçip basarak Home’a dönün. NFC kutucuğu kendi normal/seçili ikonlarını (112/113) kullanır. Güncel örnekler [NFC galerisindedir](screenshots_TR.md#nfc-kartları-ve-makara-atama).

### Acil durdurma kartı

Ana menü daima **NFC → Info** ile biter; gelecekteki yeni ana menü öğeleri
Info'dan önce eklenir. **NFC** içinde encoderi çevirip **Emergency stop tag**
seçeneğini, ardından **Assign tag** (veya **Replace tag**) seçeneğini açın.
Okuyucuda tutulan kartı uzaklaştırıp yeni kartı okutun. Görünen UID'yi kontrol
edip **Save tag** ile onaylayın; **Cancel** önceki atamayı korur.
**Remove tag** kayıtlı atamayı siler.

Tek kayıtlı UID, NFC ayarlarının yanındaki `nfc-actions.json` dosyasına atomik
kaydedilir ve Petrel yeniden başlatıldığında korunur. Bu kart okutulunca NFC
Core, açık menüden ve baskı durumundan bağımsız olarak Moonraker'ın
`printer.emergency_stop` API isteğini gönderir. Mevcut öncelikli yol normal
G-code komutlarının arkasında beklemez. Açık emergency kart ataması sırasında kayıtlı acil durdurma kartı shutdown göndermeden onay için yakalanır. Bu akışın dışında, spool kart ataması dahil, emergency önceliği sürer. Atama iptal edilince normal davranış geri gelir. Backend her kart sunumu
için bir olay üretir; yeniden tetiklemek için kartı uzaklaştırıp tekrar okutun.
Acil durdurma işleminde onay penceresi beklenmez. Kayıtlı EMG kartı okutulduğunda Raspberry Pi'nin donanım PWM buzzer'ı yaklaşık 1,5 saniye boyunca tam sesli, iki tonlu yükselip alçalan bir uyarı ve sonunda iki keskin yüksek ton çalar. Bu alarm, normal enkoder/NFC sesini keser; Klipper shutdown durumuna girse veya Moonraker isteği başarısız olsa bile çalışmaya devam edebilir. Device → Buzzer ana anahtarı Disabled ise veya Emergency card alarm kutusu kapalıysa ses çalmaz; Volume ve normal ton seçimleri alarmı etkilemez.

Okuyucu etkin, yapılandırılmış ve dinliyor olmalıdır. Yukarıda açıklandığı gibi
NFC target modunda URL paylaşımı kart algılamasını geçici olarak duraklatır.
UID eşleştirmesi kimlik doğrulama veya donanımsal güvenlik devresi değildir;
çalışan Pi'ye, okuyucuya ve Moonraker bağlantısına bağlıdır.

### NFC kartıyla MMU gate atama

Spoolman **Tags** üzerinden eşlenmiş bir kart normal bir Petrel ekranında
okutulunca **Spool #ID: choose gate** penceresi açılır. Altta dört soluk gate
makarası, üstte kartın bağlı olduğu makaranın gerçek rengindeki hareketli
makara vardır. Bu makaralar Home ve MMU menüsündeki aynı ortak
**SpoolView** simgeleridir; yeni bir ikon kopyası kullanılmaz. Üretici,
filament adı, malzeme ve makara ID'si, solda filament renginde şerit bulunan
yuvarlatılmış bilgi kartında görünür. Makara, Happy Hare'de mevcut bir gate'e
eşliyse popup açılırken kalan yüzde bir kez alınır; makaranın üzerindeki yüzde
ve dolgu yüksekliği Home/MMU ekranlarıyla aynı SpoolView mantığını kullanır.
Bu yüzde, popup boyunca sabit kalır; eşleşmeyen veya bilinmeyen makaraya başka
bir gate'in yüzdesi atanmaz, `--` gösterilir. Gate altındaki yazılar mevcut
makara atamasını gösterir. Gereksiz enkoder kullanım açıklamaları gösterilmez.
Bilgi kartından hareketli makaraya ve makaradan seçili gate'e ince bağlantı
çizgileri uzanır; gate'e inişte alt çizgi kısalıp kaybolur. Animasyon
karelerinde ikonlar yeniden çizilmez; DWIN'in bölge taşıma komutu kullanılır.
Enkoderle gate seçilir (dörtten fazla gate için sayfalama); basıldığında
önce kartın Spoolman eşleşmesi doğrulanır. Happy Hare ataması başarılı bir geri okumayla doğrulandıktan sonra makara
GIF'teki gibi yaklaşık 600 ms süren tek bir yumuşak inişle gate'e oturur. Başlıktaki Back seçeneği atamadan vazgeçirir.
Bu işlem filament yüklemez ve motor hareketi başlatmaz.

Yazdırma, duraklatma/kurtarma, meşgul veya uygun olmayan MMU durumunda
atama engellenir. Onaydan hemen önce NFC kart eşleşmesi yeniden okunur;
MMU işlemi mevcut korumalı MMUSession mekanizmasıyla yürütülür.
Başarı, gerçek gate map geri okumasından sonra gösterilir.

### Spoolman makarasına NFC kartı atama

**Home → NFC → Spoolman tag** yoluyla Spoolman envanterini açın. Liste 20'şer
makara olarak ihtiyaç üzerine yüklenir; Previous/Next page ile diğer sayfalara
geçilir. Liste üretici/ID, filament adı, malzeme ve renk kutucuğunu gösterir.
Makarayı seçince ID, üretici, ad, malzeme ve gerçek HEX renk değeriyle büyük
renk kutusu görünür; çok renkli filamentte kutu şeritlere bölünür.
Eksik renk tahmin edilmez.

**Assign tag** seçin, kartı uzaklaştırıp tekrar okutun ve UID'yi kontrol ederek
**Save tag** ile onaylayın. NFC Core yalnız yeni kart olayını yakalar; EMG
kartının global önceliği korunur. Cancel hiçbir kart ataması kaydetmez.

Atama Moonraker'ın Spoolman proxy API'si üzerinden makaranın gerçek **Tags**
kayıtlarına yazılır: `POST /v1/spool/{id}/tag`. Başarı göstermeden önce makara
yeniden okunur ve UID'nin `tags` listesinde bulunduğu doğrulanır. Özel
`extra.nfc_id` alanına yazma veya sessiz fallback yoktur; native Tags API'si
olmayan sunucuda açık hata gösterilir.

Kart başka makaraya bağlıysa kaynak ve hedef ID'leriyle **Move and assign**
onayı istenir. Cancel bağlantıları değiştirmez. Onay güncel sunucu durumuyla
yeniden karşılaştırılır; eski makaradaki yalnız ilgili tag silinir ve hedefe
eklenir. Hedefin diğer tag'leri korunur. API'nin boş 204 silme yanıtı Moonraker
tarafında hata olarak raporlansa bile tekrar silme gönderilmez: kaynaktaki
gerçek tag listesi yeniden okunarak sonuç doğrulanır. Kısmi taşıma hatasında
“Move incomplete” gösterilir; bağlantıları Spoolman'dan kontrol edin.
Başarısız yazmalar otomatik tekrarlanmaz.

Önceki hatalı sürümün oluşturduğu `extra.nfc_id` değerleri otomatik taşınmaz
ve silinmez. Aynı makara ve kartı bu akışla yeniden atayın; gerçek **Tags**
bölümünde görünmesi bu kez sunucudan doğrulanır.

Bu akış aktif makarayı değiştirmez, MMU yükleme başlatmaz ve fiziksel kart
üzerine veri yazmaz. Arşivlenmiş makaralar seçimde gösterilmez, ancak kartın
mevcut sahibi aranırken dahil edilir. Spoolman native tag benzersizliğini
sunar; iki sunucu isteğinden oluşan taşıma yine tek bir atomik işlem değildir.

### Spool kartını okutarak MMU gate atama

Petrel'in herhangi bir normal ekranında Spoolman **Tags** kaydı olan kartı
okutunca **Spool #ID: choose gate** penceresi açılır. **Cancel** veya hedef gate'i
seçin. Gate satırı mevcut makara ID'sini gösterir. Gate seçimi, okutulan kartın
bağlı olduğu makara ID'sini Happy Hare'a atar; filament yükleme veya motor
hareketi başlatmaz. Aynı makara ID'sinin diğer gate'lerden kaldırılması mevcut
Happy Hare gate atama davranışını izler.

Kartın güncel Spoolman eşleşmesi seçimden sonra yeniden doğrulanır. Gate sayısı,
MMU durumu ve komutun gönderilme anındaki kontroller mevcut MMUSession üzerinden
uygulanır. Baskı, pause/recovery, meşgul MMU veya desteklemeyen Spoolman modu
atamayı engeller; gerekçe pencerede gösterilir. Başarı, MMU'nun yeni gate
haritasının mevcut sorgu/doğrulama yoluyla onaylanmasından sonra gösterilir.
Cancel önceki ekrana ve düzenleme durumuna döner. Başlamış atamayı kapatmak
gönderilmiş komutu geri almaz.

Bu işlev NFC Core'un kart olayını kullanır; yeni libnfc/PN532 erişimi veya
periyodik Spoolman sorgusu yoktur. Bekleyen sorgu sayısı bir çalışan ve en son
kart ile sınırlıdır; eski sorgu sonuçları kullanılmaz. Kart tanımlama mevcut
önceliğini korur; EMG kartı eşleştirme sorgusundan önce işlenir ve açık gate
penceresini iptal eder. Tanımsız veya arşivlenmiş makara kartı pencere açmaz.
Aktif güç/telefon paylaşım penceresi bölünmez. URL paylaşımı target modunda
olduğu sürece kart taraması zaten duraklar.

### NFC pencereleri ve tamamlanma bildirimleri

Geçici güç ve gate pencereleri, etkin kart tanımlamayı ve yakalanan UID'yi korur.
Spoolman liste, kayıt, hata ve taşıma onayı sonuçları başka pencere açıkken de
saklanır; geri dönünce yazma tekrarlanmadan tamamlanan durum gösterilir.
Tanımlamadan farklı bir ekrana gerçekten ayrılmak işlemi iptal eder ve durumunu
detay sayfasına döndürür.

NFC tamamlanma bildirimleri mevcut LCD sahibindeki, en fazla 32 olay türü tutan
ayrı bir birleştirme kutusunu kullanır. Dolu enkoder kuyruğu bu bildirimleri
kaybettirmez; aynı türün tekrarlı bildirimlerinde en son bekleyen durum korunur.
Yeni NFC/Spoolman polling'i, donanım handle'ı veya worker eklenmez. Aynı anda tek
kart yazısı kabul edilir. Normal kapanış kuyruktaki işleri iptal eder ve başlamış
kart yazısını en fazla 60 saniye bekler; HTTP istemcisi read worker durana kadar
korunur. Süre dolarsa günlük Spoolman Tags bağlantılarını kontrol etmenizi ister.
Bu, uzaktaki DELETE/POST taşımasını atomik yapmaz; sürecin zorla öldürülmesi
sonrasında tamamlanma garantisi vermez.

NFC örnekleri CI'da üretilip [ekran galerisine](screenshots_TR.md) yayımlanır.
Mevcut tam doküman üretimi manuel kalır. Master'daki `docs(nfc):` commiti,
yalnız o sürümün regresyon CI'ı geçtikten sonra NFC yayınını başlatır;
daha yeni bir master'ın üzerine yazılmaz.

### v7 NFC hotfix davranışları

Gate seçim penceresinde okutulan makaranın doluluğu Spoolman kaydındaki kalan ağırlık ve başlangıç ağırlığından (yoksa filament ağırlığından) hesaplanır; yüzde yazısı ve ortak makara çizimi aynı değeri kullanır. Bu veri yoksa yalnız aynı makara ID’sine bağlı Happy Hare gate yüzdesi kullanılır; başka gate’in doluluğu alınmaz. Geçerli miktar yoksa `--` gösterilir. Değer pencere açılırken bir kez alınır.

Emergency kartı atama akışında kayıtlı emergency kartı tekrar okutulursa acil durdurma gönderilmeden onay için yakalanır. Bu açık atama akışının dışında, spool kartı atama sırasında da emergency önceliği korunur. Atamayı iptal etmek normal emergency davranışını geri getirir. Remove tag yalnız kayıtlı emergency kartı varken görünür. Her iki atama akışında NFC_TAG_READ, genel Buzzer anahtarı ve Volume ayarına bağlı olarak çalar.
