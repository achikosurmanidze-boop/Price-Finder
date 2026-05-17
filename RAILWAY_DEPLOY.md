# Railway Deploy

## რა არის მზად

- Flask production-ზე ეშვება `gunicorn main:app --bind 0.0.0.0:$PORT` start command-ით.
- `nixpacks.toml` აყენებს `backend/requirements.txt`-ს.
- frontend ემსახურება backend-ის `/` route-იდან.
- `.env` და SQLite cache არ უნდა აიტვირთოს GitHub-ზე.

## Railway-ზე ატვირთვა

1. შექმენი GitHub repo და ატვირთე `C:\Users\user\price-finder`.
2. Railway-ში შექმენი New Project -> Deploy from GitHub repo.
3. Service Variables-ში დაამატე:

```text
ANTHROPIC_API_KEY=შენი_გასაღები
CACHE_DURATION_SECONDS=7200
```

4. Deploy-ის შემდეგ Settings -> Networking -> Public Networking -> Generate Domain.
5. მიიღებ საჯარო HTTPS მისამართს, მაგალითად `https://your-app.up.railway.app`.

## შენიშვნა SQLite-ზე

Railway-ის ჩვეულებრივ deploy-ზე `price_cache.db` დროებითია და redeploy-ზე შეიძლება გასუფთავდეს. ეს cache-ისთვის მისაღებია. თუ გინდა shopping lists/alerts მუდმივად შეინახოს, დაამატე Railway Volume ან PostgreSQL.
