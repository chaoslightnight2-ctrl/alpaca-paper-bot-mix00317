# Render 7/24 Worker

Bu kurulum cron degil, 7/24 acik kalan Render Background Worker kullanir.

## Ne calisir?

Render worker start command:

```bash
python paper_bot.py --execute --auto-window --loop --sleep-seconds 10
```

Bot surekli ayakta kalir, her 10 saniyede:

- Alpaca paper broker history uzerinden vadesi gelen bot cikislarini kontrol eder.
- Stratejinin giris penceresindeyse yeni sinyal arar.
- Gunun giris penceresi degilse yeni pozisyon acmaz.
- Paper endpoint disinda calismaz.

## Render kurulumu

1. Render Dashboard -> New -> Blueprint.
2. Bu GitHub reposunu sec:
   `https://github.com/chaoslightnight2-ctrl/alpaca-paper-bot-mix00317`
3. Render `render.yaml` dosyasini okuyup worker servisini olusturur.
4. Environment variables alanina secret olarak gir:
   - `ALPACA_API_KEY`
   - `ALPACA_API_SECRET`
5. `ALPACA_DATA_FEED=iex` blueprint icinde hazir gelir.

## Maliyet

Render Background Worker ucretsiz degildir. `starter` plan 7/24 acik kalacagi icin aylik sabit compute ucreti dogurur. Render fiyatini dashboard'da onaylamadan deploy etme.

## Guvenlik

- `strategy_config.json` icinde `paper_only=true`.
- `live_trading_enabled=false`.
- `paper_base_url=https://paper-api.alpaca.markets`.
- Live key kullanma.
- API keyleri dosyaya yazma, sadece Render secret/env var olarak gir.

## Neden cron'dan daha iyi?

GitHub Actions schedule exact-time garanti etmez. Render worker zaten acik oldugu icin cron'un runner baslatmasini beklemez; zaman hassasiyeti botun ic loop suresine iner. Bu repoda loop 10 saniyedir.

## Operasyon notlari

- Render logs ekraninda strateji adi, dry_run/execute durumu, broker close kontrolleri ve giris penceresi mesajlari gorunur.
- Render worker restart olursa lokal `state/` kalici olmayabilir. Bot bu yuzden broker order history'den vadesi gelen cikislari kontrol eder.
- Ayni gun duplicate order riskini azaltmak icin Alpaca `client_order_id` gecmisi kontrol edilir.
