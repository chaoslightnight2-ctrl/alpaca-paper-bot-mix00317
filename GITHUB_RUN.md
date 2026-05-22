# GitHub'da Calistirma

Bu repo Alpaca paper bot icindir. Live trading etkin degildir.

## 1. Repo'ya Yukleme

Bu makinede `git` ve `gh` PATH'te yok. GitHub Desktop ile klasoru repo olarak ekleyebilir veya Git kurduktan sonra su komutlari kullanabilirsin:

```powershell
cd "$env:USERPROFILE\OneDrive\Masaüstü\alpaca_paper_bot_v22_aday7_91531"
git init
git add .
git commit -m "Add Alpaca paper bot mix_00317"
git branch -M main
git remote add origin https://github.com/KULLANICI/REPO.git
git push -u origin main
```

`.env`, `state/`, `logs/`, `__pycache__/` ve `app_profile/` repo'ya gitmemelidir.

## 2. GitHub Secrets

Repo Settings -> Secrets and variables -> Actions -> New repository secret:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

Paper key kullan. Live key kullanma.

## 3. Actions ile Calistirma

Actions -> Alpaca Paper Bot -> Run workflow.

- `mode=dry_run`: sinyal ve emirleri loglar, paper emir gondermez.
- `mode=execute`: Alpaca paper hesaba emir gonderir.
- `run_type=auto_window`: kisa loop boyunca broker/state cikislarini ve giris penceresini birlikte kontrol eder.
- `run_type=entry_window`: giris penceresinde yeni trade arar.
- `run_type=close_due`: Alpaca broker order history'den bugunku bot emirlerini bulur ve vadesi gelen cikislari kapatir.
- `max_minutes=35`: Manuel calistirmada loop suresi. Scheduled runlarda workflow kendi guard suresini secer.

Zamanlama ve Cron Gecikmesi:

- Stratejinin giris penceresi Turkiye saatiyle yaklasik `16:40-17:00`.
- GitHub cron bazen gec baslayabildigi veya yogunlukta drop olabildigi icin workflow tek saate guvenmez.
- GitHub dokumani, schedule yogunlukta gecikebilir/dusurulebilir; ozellikle saat baslari yogun oldugu icin farkli dakikalari onerir.
- Workflow artik `America/New_York` timezone kullanir; ABD yaz/kis saati degisiminde UTC cron elle duzeltilmez.
- Entry guard cronlari New York saatiyle `09:04-10:19` arasinda 5 dakikada bir kisa auto-window calistirir.
- Close guard cronlari New York saatiyle `14:04-16:19` arasinda 5 dakikada bir kisa auto-window calistirir.
- Cron dakikalari `:04, :09, :14, ... :54` seklindedir; `:00-:03` saat basi yogunlugu bilerek kullanilmaz.
- Her scheduled run varsayilan olarak 4 dakika yasar. Bu, tek uzun job'a baglanmak yerine cok sayida kisa yakalama denemesi yapar.
- Workflow run adi schedule stringini gosterir; Actions listesinden hangi cronun tetikledigini daha kolay gorursun.
- Opsiyonel heartbeat secretlari eklenirse cron'un baslayip baslamadigi ve basari/hata sonucu disaridan izlenebilir:
  - `PAPER_BOT_HEARTBEAT_START_URL`
  - `PAPER_BOT_HEARTBEAT_SUCCESS_URL`
  - `PAPER_BOT_HEARTBEAT_FAILURE_URL`
- Her kontrol once broker order history'den vadesi gelen bot pozisyonlarini kapatmayi dener, sonra giris penceresindeyse yeni trade arar.
- Bot Alpaca `client_order_id` gecmisini kontrol eder; ayni gun ayni sleeve/sembol icin duplicate open gondermeyi skip eder.
- Scheduled run'lar varsayilan olarak dry-run calisir. Otomatik paper emir istiyorsan repo variable ekle:
  - Settings -> Secrets and variables -> Actions -> Variables
  - `PAPER_BOT_SCHEDULE_EXECUTE=true`
- Kritik not: GitHub Actions yine yuzde yuz garanti vermez. Bu ayar, gecikme/drop riskini azaltan en agresif GitHub Actions guard katmanidir.

## 4. GitHub Actions Siniri

GitHub Actions kalici server degildir. Uzun sureli bot calistirmak icin VPS daha saglamdir.

Bu nedenle bu repoda Windows Task Scheduler local guard da vardir:

```powershell
.\install_windows_scheduled_tasks.ps1 -Mode execute
```

Kurulan gorevler:

- `AlpacaPaperBot-MainSessionGuard`: hafta ici 16:15 TR, 430 dakika.
- `AlpacaPaperBot-CloseBackupGuard`: hafta ici 21:10 TR, 135 dakika.

Bu local guard GitHub cron'a bagli kalmadan `paper_bot.py --execute --auto-window --loop` calistirir. GitHub schedule artik yedek katmandir.

Actions uygun kullanim:

- market acilis penceresinde 30-40 dakika paper bot calistirmak
- log ve state artifact almak
- dry-run smoke test yapmak

VPS uygun kullanim:

- her is gunu otomatik calisma
- dashboard'u surekli acik tutma
- state/log kaliciligi
