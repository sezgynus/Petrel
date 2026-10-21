# UI için C'ye taşıma adaylarının analizi

[English](ui-native-profiling.md)

Analiz dalı: `analysis/ui-native-profiling`; taban C broker commit'i `80a3641`.
Henüz UI algoritması C'ye taşınmadı. Araçlar yalnız tanılama içindir; profil
varsayılan olarak kapalıdır ve kurulum bağımlılığı değildir.

## Üç ayrı ölçüm

Aynı Pi, ekran, remote/emülatör ayarları ve dosyaları kullanın. Commit değişince
servisi yeniden başlatın; ölçüm sırasında checkout'u değiştirmeyin. SHA,
Python/OS/mimari ve önbelleğin soğuk/sıcak durumunu kaydedin. Baskı, ısıtma,
homing veya bakım testi başlatmayın; yalnız görüntüleme ekranlarını kullanın.
Her senaryoyu aynı süre ve yaklaşık aynı işlem sayısıyla üç kez tekrarlayın;
medyanları ve tekrarlar arasındaki değişkenliği karşılaştırın.

| Senaryo | 60 saniyelik işlem |
|---|---|
| idle | Dashboard'a dokunmayın |
| menus | Aynı gezinme rotasını tekrarlayın; dönüş/tıklama sayısını kaydedin |
| thumbnails | Aynı dosya önizlemelerini açın; ilk yükleme ve önbellekli ölçümü ayırın |
| mesh | Kayıtlı mesh'i görüntüleyin; kalibrasyon başlatmayın |
| maintenance | Mevcut kullanım/hatırlatma/değerlendirme sayfalarını gezin; test başlatmayın |

### 1. Normal süreç CPU ve belleği

```bash
cd ~/Petrel
git fetch origin
git switch analysis/ui-native-profiling
git pull --ff-only
sudo systemctl restart Petrel.service
sleep 30
git rev-parse HEAD
sudo ~/petrel-env/bin/python tools/profile_ui_resources.py baseline \
  --label idle-1 --seconds 60 --output-dir "$HOME/petrel-ui-profiles/baseline"
```

Diğer senaryolar için açıklayıcı etiketlerle tekrarlayın. Araç `/proc` verilerini
dışarıdan okur; Petrel içinde profil açmaz. CPU tek çekirdeğin yüzdesidir. JSON'da
ham RSS/PSS/USS/Swap/SwapPss, PSS+SwapPss, PID/başlangıç zamanı, platform ve araç
checkout SHA'sı bulunur. Yeniden başlama/PID yeniden kullanımı ölçümü geçersiz
kılar. Araç SHA'sı çalışan servisin yüklediği kodu kanıtlamaz; yukarıdaki yeniden
başlatma gereklidir. Rapor isimleri benzersiz, dosyalar özeldir. Tüm ölçümlerden
sonra `sudo chown -R "$(id -u):$(id -g)" "$HOME/petrel-ui-profiles"` ile sahipliği
geri alabilirsiniz.

İşlem sayısını ve görülen duraklamaları ayrıca kaydedin. Araçlar enkoder-panel
gecikmesini ölçmez; bunun için daha sonra hedefli zaman damgaları veya video gerekir.

### 2. Bütün thread'lerde etkin çağrı örneklemesi

Çalışma ortamına dokunmadan py-spy'ı ayrı ortama kurun:

```bash
python3 -m venv ~/petrel-profile-env
~/petrel-profile-env/bin/python -m pip install py-spy
~/petrel-profile-env/bin/py-spy --version
sudo ~/petrel-env/bin/python tools/profile_ui_resources.py cpu \
  --label menus-1 --seconds 60 \
  --py-spy "$HOME/petrel-profile-env/bin/py-spy" \
  --output-dir "$HOME/petrel-ui-profiles/cpu"
```

Aynı senaryoları tekrarlayın; py-spy sürümünü sonuçlarla saklayın. Pi mimarisi için
wheel bulunamazsa uygulama ortamını değiştirmeden hatayı bildirin. Araç 49 Hz,
thread kimlikleriyle yerel Speedscope JSON'u ve metadata JSON'u oluşturur.
Örnekleme süreci bir miktar etkiler; mutlak CPU/RAM için birinci ölçümü kullanın.
`--locals` eklemeyin.

Çağrı örneği oranı kesin fonksiyon CPU süresi değildir. Boşta thread tespiti,
özellikle ARM32'de yaklaşıktır. Native çağrıdaki Python stack'i pahalı C rutinini
belirlemez; gerekirse ayrı native profil alınır. `--gil` ile sınırlamayın:
Pillow GIL dışında çalışabilir. UART/ağ beklemesi şüphesinde ayrıca boşta
thread'leri içeren iz ve taşıma kodu incelenmeden C kararı verilmez.
Kaynak: [py-spy dokümantasyonu](https://github.com/benfred/py-spy).

### 3. Python bellek tahsislerinin kaynağı

İlk iki ölçümden ayrı çalıştırın. İsteğe bağlı kanca UI importlarından önce
tracemalloc başlatır; 30 saniye bekleyip 60 saniyelik senaryonun öncesi/sonrası
snapshot'larını karşılaştırır. Başlangıç journal'a yazılır. Bu çalışmanın RAM,
CPU ve açılış süresi normal tüketimle karşılaştırılamaz. Beş çağrı çerçevesi ve
ilk 40 kayıt JSON'a yazılır; tam snapshot ve yerel değişken değerleri yazılmaz.
Hata olsa da izleme pencere sonunda kapanır. Daemon thread kapanışı geciktirmez;
servis erken kapanırsa rapor oluşmayabilir.

Mevcut servis kullanıcısı, ortamı, GPIO ve UART sahipliğini koruyan geçici drop-in
kullanın; dosya yeniden başlatmada silinir:

```bash
sudo mkdir -p /run/systemd/system/Petrel.service.d
sudo tee /run/systemd/system/Petrel.service.d/90-ui-memory-profile.conf >/dev/null <<'EOF'
[Service]
StateDirectory=Petrel-ui-profile
StateDirectoryMode=0700
Environment=PETREL_PROFILE_MEMORY_DIR=/var/lib/Petrel-ui-profile
Environment=PETREL_PROFILE_WARMUP_SECONDS=30
Environment=PETREL_PROFILE_SECONDS=60
EOF
sudo systemctl daemon-reload
sudo systemctl restart Petrel.service
journalctl -u Petrel.service -f --no-pager
```

`UI memory profile: workload window started` mesajında senaryoya başlayın.
Ctrl+C yalnız journal görüntülemeyi durdurur. `UI memory profile complete`
mesajını bekleyin. Her senaryo için servisi yeniden başlatın; etiket/PID'yi ayrıca
kaydedin. Eski raporlar korunur. Geçersiz seçenek veya profil hatası UI açılışını
engellemez, journal'a yazılır. Mevcut tracemalloc oturumu devralınmaz. İki süre
ayrı ayrı 1–600 saniye olabilir; izleyici ciddi RAM harcayabilir, Pi belleğini
değerlendirmeden süreleri artırmayın.

Yalnız bu drop-in'i kaldırıp yeniden başlatarak normal sürece dönün:

```bash
sudo rm /run/systemd/system/Petrel.service.d/90-ui-memory-profile.conf
sudo systemctl daemon-reload
sudo systemctl restart Petrel.service
sudo tar -czf "$HOME/petrel-ui-memory.tar.gz" -C /var/lib/Petrel-ui-profile .
```

Raporlarda kod yolu, satır ve bayt/adet toplamları vardır; yapılandırma içeriği
veya anahtarlar yoktur. Native tahsisler görünmeyebilir. Net büyüme bellekte tutulan
veridir, tek başına sızıntı kanıtı değildir; geçici tahsisler snapshot arasında
kaybolabilir. İzleyicinin kendi metadata maliyeti ayrıca raporlanır; snapshot'lar
da bellek kullanır. Tepe değerini kalıcı tahsislerle ve birinci ölçümle yorumlayın.

## Aday seçimi

İlk kod adayı `thumbnail_preview._protect_dark_foreground`: pikseller üzerinde
Python döngüsü ve tuple üretimi var; önemi henüz ölçülmedi. Pillow ölçekleme/JPEG
işlemleri zaten native'dir. Menü veya UART/ağ beklemelerini yalnız örnek oranıyla
C'ye taşımak gerekçelendirilemez.

Her adayda senaryo, mutlak süreç maliyeti, örnek payı, kalıcı/tepe tahsisler,
Python içinde iyileştirme imkânı, C sınırı/kopyalama maliyeti ve toplam kazanımın
üst sınırı raporlanır. Toplam CPU'nun %5'ini kullanan fonksiyon sonsuz hızlansa
bile toplam CPU'da en fazla o %5'i kazandırır. Tekrarlanabilir toplam kazanç veya
kullanıcıya yansıyan gecikme azalması bakım maliyetini karşılamalıdır; uygulamadan
önce sayısal hedef belirlenir.

Python referansı korunur; aynı paket/görsel çıktısı, sınır girdileri, hata ve iptal
davranışları karşılaştırılır. Native prototip ARM32/ARM64 derlemesi, sanitizer ve
CI regresyonları; ardından profilsiz Pi A/B ölçümü gerektirir. Proje kuralı:
yerel test/emülatör çalıştırmayın; her mantıksal commit sonrası imzalama ve son
imzalı SHA'nın bütün CI kontrollerini bekleyin.
