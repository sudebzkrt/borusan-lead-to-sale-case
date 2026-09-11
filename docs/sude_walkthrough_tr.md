# Sude için: bu repo ne, neden böyle, nasıl anlatılır

Bu doküman Türkçe; geri kalan her şey (kod, README, notebook açıklamaları) İngilizce, çünkü ilan "teknik dokümanları takip edebilecek İngilizce" istiyor ve repo İngilizce olunca daha ciddi durur. Sunumu Türkçe yapabilirsin.

## Büyük resim: tek cümle

"Üç farklı kaynak sistemden (CRM, web formu, bayi DMS'i) gelen kirli veriyi Fabric'te Bronze → Silver → Gold katmanlarından geçirip bir yıldız şemaya oturttum; Power BI bu Gold'u Direct Lake ile okuyor, lead skorlama modelim de aynı Gold'u okuyor. Rapor ve AI ürünü aynı sayılara bakıyor."

Bunu ezberle. Jürideki herkes 30 saniyede ne yaptığını anlar.

## Neden tek dataset?

İki soru da "gerçek bir iş problemi" istiyor. Lead-to-sale hunisi bir otomotiv ithalatçısının en somut problemi: web'den bin lead geliyor, 80'i satışa dönüyor, hangisini önce aramalı? Aynı veri hem Medallion'u hem AI ürününü doyuruyor. Dağınık iki demo yerine tek hikâye.

## Veri neden "kirli" üretildi?

İlan iki yerde veri kalitesini vurguluyor. Temiz bir CSV'yi üç katmandan geçirmek gösteriş olurdu. O yüzden generator kasıtlı 22 tip hata gömüyor: aynı müşteri iki kayıt, telefon beş formatta, "İstanbul/Istanbul/ISTANBUL", %150 iskonto, bayi kodu D099 (yok), satış tarihi lead'den önce, karışık tarih formatları. `docs/dq_injections.md` bunların sayısını tutuyor. Silver notebook'un son hücresi kendi bulduklarını bu sayılarla karşılaştırıyor: 18 kontrolün 12'si birebir, kalanı ±1-8 (aynı satıra iki hata denk geldiğinde olur, notebook'ta açıklaması var).

Mülakatta şunu söyle: "Gerçek projede ground truth olmaz; o yüzden `dq_results` tablosu ve DQ Monitor sayfası var. Burada sentetik veri sayesinde kontrolleri doğrulayabildim."

## Katmanlar, tek tek

**Bronze (`01_bronze_ingest`)**: Dosyalar olduğu gibi Delta tablosuna. Her şey string. Üç lineage kolonu (`_source_system`, `_source_file`, `_ingest_ts`). DMS'in ondalık virgülü bile burada düzeltilmiyor. Soru gelirse: "Bronze denetim izi. Silver'da bir sayı yanlış çıkarsa kaynağın ne gönderdiğine bakabilmeliyim."

**Silver (`02_silver_clean`)**: Asıl iş burada.
- `try_to_timestamp` ile yedi tarih formatı sırayla deneniyor, tutmayan null kalıp sayılıyor.
- Telefon → `+905XXXXXXXXX`; şehir → Türkçe-duyarlı katlama (`fold_tr`) ile kanonik yazım.
- Müşteri tekilleştirme: aynı normalize telefon = aynı kişi; en eski kayıt "golden record", diğerleri `customer_xref` ile ona bağlanıyor; lead ve satışlardaki `customer_id` golden'a yönlendiriliyor. Bu, ilandaki "ana veri yönetimi" (master data) maddesi.
- CRM lead'leri + web JSON lead'leri tek `silver.leads` tablosunda birleşiyor.
- Kural: satır silinmez (tam duplicate hariç), değer sessizce null'lanmaz. Her sorun `dq_flags` dizisine yazılır, her kontrol `dq_results`'a satır olarak düşer.
- Eksik net fiyat liste × (1 − iskonto) ile **impute** ediliyor ve flagleniyor. Neden? Ciro KPI'ında sessiz boşluk, belgelenmiş tahminden kötüdür.

**Gold (`03_gold_star_schema`)**: Yıldız şema. `fact_leads` lead başına tek satır, bütün huni pre-joined (test sürüşü var mı, teklif var mı, satış var mı, kaç etkileşim). `dim_dealer`, `dim_vehicle`, `dim_customer`, `dim_advisor`, `dim_lead_source`, `dim_date`. Bozuk FK'ler için her dimension'da `UNK` satırı var: bayi kodu bozuk lead huniden kaybolmuyor, "Unknown dealer" altında görünüyor. `lead_notes` AI ürünü için notların birleştirilmiş hali.

Soru: "Neden surrogate key yok, SCD2 yok?" Cevap: "İki günde doğal anahtarla gittim; bayi adı değişince tarihçe tutmak için SCD2 bir sonraki adım, `dim_dealer`'a `valid_from/valid_to` eklenir."

**Semantic model**: Direct Lake (import yok, refresh yok). İlişkiler tek yönlü, fact → dim. `dim_date` date table olarak işaretli. Ölçüler `_Measures` tablosunda, `semantic_model/measures.dax` içinde her birinin yorumu var. "Conversion" iki tane: açık lead'ler paydada olan ("bugün itibarıyla") ve sadece kapananlar. Bu farkı sen gündeme getir, olgun görünür.

**Rapor**: 4 sayfa. Huni, bayi/danışman, model karması, DQ monitor. `report/report_spec.md` görsel görsel yazıyor.

## AI ürünü: Lead Intelligence Assistant

Problem: danışmanın önünde 60 açık lead var, CRM sırasıyla arıyor. Ürün: her açık lead'e satışa dönüşme olasılığı + "neden" + önerilen sonraki adım.

Teknik olarak dikkat çekecek kısım **point-in-time correctness**. Kapanmış bir lead'in son hâli eğitim örneği olamaz; "teklif var = kazandı" sınavın cevabını okumaktır. O yüzden her kapanmış lead'den yaşam süresi içinde rastgele iki *snapshot* alınıyor ve her özellik o an bilinebilen olaylardan hesaplanıyor. Sonucu yazan son not ("Sözleşme imzalandı") tamamen atılıyor. Doğrulama zamansal: Mart 2026 öncesi eğitim, sonrası test. AUC 0.82; teklif öncesi lead'lerde 0.84 ve en üst %10'da 3.7× lift. "Teklif öncesi" sayısını vurgula: model asıl orada işe yarıyor.

Notlar → sinyal: `signals.py` kural tabanlı (fiyat itirazı, sessizleşti, erteleme, alım sinyali, finansman, stok…). LLM neden her lead için çağrılmıyor? 15 bin lead × günlük çağrı = para ve gecikme; modelin kaba sinyal yetiyor. LLM "son mil"de: seçilen lead için özet + sonraki adım + müşteriye taslak WhatsApp mesajı. Anahtar yoksa şablon modunda çalışıyor; demo asla bozulmaz.

Açıklama yöntemi: SHAP değil, tek-özellik ablasyonu (özelliği popülasyon medyanıyla değiştir, skor kaç puan değişti). Sorarlarsa "SHAP bir sonraki adım" de.

`ai_product/app.py` Streamlit; arayüz Türkçe çünkü kullanıcı bayi personeli. Model kartı sayfası sınırları da yazıyor (sentetik veri, bayi etkisinin adil olmaması, aylık yeniden eğitim). Sınırları kendin söylemek puan kazandırır.

## Vibe coding sorusuna cevap

Soru metni "AI-assisted / vibe coding yaklaşımından yararlanabilirsiniz" diyor; sormaları muhtemel. Dürüst cevap: "Evet, Claude ile çalıştım. Mimariyi ve veri modelini ben belirledim, kodu birlikte yazdık, her hücreyi çalıştırıp çıktıyı doğruladım, DQ sayılarını ground truth ile karşılaştırdım. Repo'da `CLAUDE.md` ve `AGENTS.md` var; ekipte biri devam etmek istese asistan bağlamı hazır." Bu, ilandaki "AI dönüşüm vizyonu"na birebir oturuyor.

## Öncelik sırası (2 gün)

1. Fabric'te üç notebook'u çalıştır, ekran görüntüsü al. (Gün 1 sabah)
2. Pipeline'ı kur, bir kez koştur, Monitor ekranını çek. (Gün 1 öğle)
3. Semantic model + rapor. En çok zaman bu. (Gün 1 öğleden sonra + Gün 2 sabah)
4. `run_local.sh` ile lokalde her şeyi çalıştır, Streamlit'i aç, prova yap. (Gün 2 öğle)
5. Slaytlar (`docs/presentation_outline.md`). (Gün 2 öğleden sonra)
6. Bir şey ters giderse: rapor yerine ekran görüntüleri, Fabric yerine lokal çalıştırma. Hikâye aynı kalır.

## Muhtemel sorular

- *Neden Lakehouse, neden Warehouse değil?* Spark ile dönüşüm ve Direct Lake için Lakehouse yeterli; Warehouse T-SQL ağırlıklı ekipler için. Gold'u Warehouse'a taşımak bir gün.
- *Artımlı yükleme?* Şu an full overwrite. Sonraki adım: Bronze `append` + `_ingest_ts`, Silver'da Delta `MERGE` ile upsert, pipeline parametresi `run_date`.
- *Veri güvenliği / yetkilendirme?* Semantic model'de RLS (bayi müdürü sadece kendi bayisini görür), OneLake'te workspace rolleri, KVKK için `kvkk_consent` kolonu Silver'da; Gold'da telefon/e-posta yok.
- *Performans izleme?* Pipeline Monitor + `dq_results` trendi; error-severity kontrol eşiği aşarsa pipeline fail.
- *Model ne kadar sık eğitilir?* Aylık; Gold'dan sonra pipeline adımı. Drift için aylık AUC'yi `model_metrics` tablosuna yazmak sonraki adım.
- *Bu sentetik veri; gerçekte ne değişir?* Not kalitesi düşer → LLM çıkarımı gerekebilir; kaynak sistem sayısı artar; şema değişimleri için Bronze'da schema evolution.
