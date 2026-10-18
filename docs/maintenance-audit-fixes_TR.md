# Maintenance kaynak denetimi çözümleri — 18 Ekim 2026

> Aşağıdaki tarihli kayıt/denetim notları kaydedildikleri sürümü açıklar; güncel çalıştırma talimatı veya kabul toplamı değildir. [Güncel kullanım rehberini](user-guide_TR.md#maintenance) ve [kabul çizelgesini](maintenance-reference-printer-acceptance_TR.md) kullanın. Daha sonraki değişiklikler eski test erişimi, güvenlik eşiği ve kabul bekleme ifadelerinin yerini alır.

Denetim tabanı: e324a6684c439e34ec745a614c1f508a5ff3cdbb. Çalışma feature/maintenance-ui-ux dalındadır. Lokal test veya emülatör çalıştırılmadı. Her değişiklik imzalandı ve sonraki geliştirmeden önce tam imzalı commit üzerinde Actions ile doğrulandı. Bir takvim regresyonunda saat enjeksiyonu ek test commit'iyle düzeltilip CI yeşile döndükten sonra devam edildi.

| Bulgu | Çözüm | İmzalı uygulama commit'i |
|---|---|---|
| A01 | Pozitif dryer güvenlik ihlali transport yeniden okuma toleransına girmez | 7e0c0998 |
| A02 | Workflow acil durdurma isteği ilk epoch ile korunur | b09987a6 |
| A03 | Filament işlem durumu sıfırlanır; meşgul başlatma sahipliği bozmaz | 3b957aa8 |
| A04 | Fan restore ölçeklenmiş PWM'i komut oranına geri dönüştürür | 282d288e |
| A05 | Kayıt proxy'si pulse JSON keyword çağrısını korur | 96590dfe |
| A06 | Son servis adımı gözlem ekranını güvenli üretir | f6a8a29b |
| A07 | Terminal F12 sonucu geçmiş ve Assessment'a bir kez aktarılır | bcadd89a |
| A08 | Reddedilen F12 devamı BLOCKED gösterilir | 498f8565 |
| A09 | Takvim vadesi güncellenir; discovery kayıt önbelleğini geçersiz kılar | 2ffcec33 |
| A10 | Sınırlı history Future'ları kuyruk ve disk hatalarını görünür kılar | b9df1411 |
| A11 | Bağımsız metrik politikaları bağımsız bulguları korur | d6897192 |
| A12 | Config-only kalibrasyonlar status nesnesi olmadan keşfedilir | bd5d1dac |
| A13 | Override edilmiş pulse ve DUMP_TMC komutları reddedilir | de213739 |
| K01 | Onaylı ısınma hızı referansı, uyumlu karşılaştırma, kaldırma ve güncel Findings | a90b6065, b7d967a0, 032eafe8 |
| K02 | Kalıcı örneklenmiş baskı/açık kalma sayaçları, kullanım hatırlatıcıları ve kapsam | 362b0c56, fa4b05f1, 032eafe8 |

Referans ölçülen ısınma cevabını karşılaştırır; parça aşınması veya garanti edilmiş ömür değildir. Kullanıcı sınırı seçip aynı donanım/soğutmayı onaylar; ölçülen kurulum koşulları uyuşmalıdır. Alt sınır kullanım vadenin geldiğini kanıtlayabilir, gelmediğini kanıtlayamaz. Kesin ömür, sıfırlanmayacağı kanıtlanmış Moonraker toplamları veya doğrulanmamış hareket sayacı sürekliliği uydurulmaz. Üretici bakım aralıkları varsayılan değil açık politikalardır. Yeni referans/kullanım akışı fiziksel ekran kabulü gerektirir; backend regresyon başarısı bunun yerine geçmez.
