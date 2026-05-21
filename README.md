# Alpaca Paper Bot - mix_00317

Bu bot sadece Alpaca paper endpointine emir yollar. Canli Alpaca URL'si kilitlidir.

## Kurulum

PowerShell:

```powershell
cd "$env:USERPROFILE\OneDrive\Masaüstü\alpaca_paper_bot_v22_aday7_91531"
$env:ALPACA_API_KEY="paper_key"
$env:ALPACA_API_SECRET="paper_secret"
python .\paper_bot.py --dry-run --loop
```

Paper emir gondermek icin:

```powershell
python .\paper_bot.py --execute --loop
```

## Test

Piyasa kapaliyken sadece sinyal mantigini denemek icin:

```powershell
python .\paper_bot.py --dry-run --allow-late-entry
```

## Strateji Ozeti

- Kaynak: `mix_00317` no-lookahead 5m Alpaca feature-combo aramasi.
- 10,000 TL uzerinden 1 yillik paper-config Monte Carlo p50: 87,132 TL.
- Cift yonlu: long ve short alt sinyaller birlikte calisir.
- Agirlikli brut kaldirac 1.8246, ust limit 2.0.
- Ucretsiz Alpaca uyumu icin sadece `iex` market data feed kullanir.
- Historical bars endpointinde `next_page_token` sayfalamasi yapar.
- Son bar cikislari 16:00 sonrasi kuyruga dusmesin diye 15:59 ET'de kapatilir.
- Emirlerde tekrar acmayi azaltmak icin `client_order_id` kullanir.
- Entry bar 1, 2, 3 ve exit bar 60, 77 kullanan 4 alt-sinyal var.
- Yeni giris penceresi Turkiye saatiyle yaklasik 16:40-17:00 arasidir.
- Dry-run state dosyasi: `state/dry_run_state.json`
- Paper execute state dosyasi: `state/paper_state.json`
- Log dosyasi: `logs/paper_bot.log`

Not: Bu bir backtestten turetilmis paper test botudur; kar garantisi degildir. Live trading etkin degildir.
