# Telegram Finance Bot (@AutoSum24bot)

ប្រព័ន្ធកត់ត្រាចំណូល-ចំណាយឆ្លាតវៃតាម Telegram Bot ជាមួយការស្កេនវិក្កយបត្រ (OCR) និងរបាយការណ៍បែងចែកពេលវេលា។

## ឯកសារក្នុងគម្រោង
- `bot.py` : កូដមេរបស់ Telegram Bot
- `database.py` : SQLite Database (តារាងអ្នកប្រើប្រាស់ និងប្រតិបត្តិការ)
- `Dockerfile` : កំណត់ Linux Environment រួមទាំង Tesseract OCR សម្រាប់ Deploy
- `docker-compose.yml` : ដំណើរការ Bot ក្នុង Docker Container
- `Procfile` : កំណត់ Worker process សម្រាប់ Cloud Hosting
- `requirements.txt` : កញ្ចប់បណ្ណាល័យ Python ដែលត្រូវការ

---

## របៀប Deploy ទៅកាន់ GitHub និង Cloud Hosting

### ជំហានទី ១: បង្កើត Repository លើ GitHub
1. ចូលទៅកាន់ [GitHub](https://github.com/new)
2. បង្កើត Repository ថ្មី (ឧទាហរណ៍ឈ្មោះ `telegram-finance-bot`)
3. បើក Terminal ក្នុងថតនេះ រួចវាយពាក្យបញ្ជា៖
   ```powershell
   git remote add origin https://github.com/<ឈ្មោះ_GitHub_របស់អ្នក>/telegram-finance-bot.git
   git branch -M main
   git push -u origin main
   ```

---

### ជំហានទី ២: ដាក់ឱ្យដំណើរការលើ Cloud (ជ្រើសរើស ១ ក្នុងចំណោម ២)

#### ជម្រើសទី ១: Railway.app (ងាយស្រួលបំផុត)
1. ចូលទៅ [railway.app](https://railway.app) ហើយ Sign in ជាមួយ GitHub
2. ចុច **New Project** -> **Deploy from GitHub repo**
3. ជ្រើសរើស Repository `telegram-finance-bot`
4. ចូលទៅផ្ទាំង **Variables** ហើយបន្ថែម៖
   - `BOT_TOKEN` = `8957791647:AAHE6P5dOmlZy7lkrZOwW6glxvFNA5zoJ7o`
5. Railway នឹង Build តាម `Dockerfile` ហើយដំណើរការ Bot 24/7 ដោយស្វ័យប្រវត្តិ។

#### ជម្រើសទី ២: Render.com (ឥតគិតថ្លៃ Free Tier)
1. ចូលទៅ [render.com](https://render.com) ហើយ Sign in ជាមួយ GitHub
2. ចុច **New +** -> ជ្រើសរើស **Background Worker**
3. ភ្ជាប់ជាមួយ Repository របស់អ្នក
4. ត្រង់ **Runtime/Environment**: ជ្រើសរើស **Docker**
5. ចូលទៅ **Environment Variables** ហើយបន្ថែម៖
   - `BOT_TOKEN` = `8957791647:AAHE6P5dOmlZy7lkrZOwW6glxvFNA5zoJ7o`
6. ចុច **Create Background Worker** ជាការស្រេច។
