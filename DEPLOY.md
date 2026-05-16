# სხვებისთვის გაზიარება — Railway-ზე განთავსება

Railway არის უფასო სერვისი, რომელიც შენს პროგრამას ინტერნეტით ხელმისაწვდომს ხდის.
რეგისტრაციაც უფასოა. ქვემოთ ნაბიჯ-ნაბიჯ ამოხსნა.

---

## ნაბიჯი 1: GitHub-ზე ატვირთვა

Railway-ს სჭირდება კოდი GitHub-ზე. GitHub უფასოა.

1. გახსენი https://github.com და გაიარე რეგისტრაცია
2. დააჭირე **New repository** (მწვანე ღილაკი)
3. სახელი: `price-finder` (ან რაც გინდა)
4. დააჭირე **Create repository**

შემდეგ გახსენი PowerShell `price-finder` საქაღალდეში:

```
cd C:\Users\user\price-finder
git init
git add .
git commit -m "Georgian price finder app"
git branch -M main
git remote add origin https://github.com/შენი-სახელი/price-finder.git
git push -u origin main
```

> `შენი-სახელი` შეცვალე GitHub-ზე შენი username-ით

---

## ნაბიჯი 2: Railway-ზე განთავსება

1. გახსენი https://railway.app
2. **Sign in with GitHub** (GitHub-ის ანგარიშით შესვლა)
3. დააჭირე **New Project**
4. აირჩიე **Deploy from GitHub repo**
5. სიიდან აარჩიე `price-finder`
6. Railway ავტომატურად აიღებს `Procfile`-ს და გაუშვებს სერვერს

---

## ნაბიჯი 3: API გასაღების დამატება

Railway-ს უნდა ეთქვა შენი Anthropic API გასაღები:

1. Railway-ს პროექტში გახსენი **Variables** ჩანართი
2. დააჭირე **New Variable**
3. ჩაწერე:
   - Name: `ANTHROPIC_API_KEY`
   - Value: `sk-ant-api03-...` (შენი გასაღები)
4. **Add** → Railway ავტომატურად გადაიტვირთება

---

## ნაბიჯი 4: ლინკის აღება

გადატვირთვის შემდეგ Railway გაჩვენებს ლინკს, მაგ.:
`https://price-finder-production.up.railway.app`

ეს ლინკი გაუზიარე სხვებს — სულ ეს არის!

---

## რამდენი ღირს?

Railway-ს **Hobby** გეგმა:
- პირველი $5 ყოველ თვე **უფასოა**
- ეს პროგრამა ძალიან მსუბუქია, $5-ზე ნაკლებ დახარჯავ
- 500 სეარჩი/თვე სავარაუდოდ $2-3 ღირს

---

## ლოკალური გაშვება (სხვა კომპიუტერზე)

თუ სხვა ადამიანს უნდა ლოკალურად გაუშვას:

1. გადმოწეროს კოდი: `git clone https://github.com/შენი-სახელი/price-finder`
2. `.env` ფაილში ჩაწეროს API გასაღები
3. გაუშვას `start.bat`

---

## ხშირი შეკითხვები

**Q: Railway-ს შეიძლება ნელა ეშვება პირველ ჯერ?**
A: დიახ, "cold start" ახლახანს გაჩერებული სერვისი 10-20 წამი ანელებს. Hobby გეგმაზე სერვისი გაჩერდება 30 წუთიანი idle-ის შემდეგ. შემდეგ request-ზე კვლავ გაიწყება.

**Q: ჩემი API key სხვებს ექნებათ წვდომა?**
A: არა — ის Railway-ს Variables-ში ინახება, კოდში არ ჩანს.

**Q: მეორე განახლება (კოდის ცვლილება) როგორ ავტვირთო?**
A: `git add . && git commit -m "update" && git push` — Railway ავტომატურად განაახლებს.
