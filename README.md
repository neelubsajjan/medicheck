# 🩺 MediAI — AI-Driven Symptom Checker

Built with Python Django + Scikit-learn for Enhanced Telemedicine Services.

---

## ⚡ Quick Setup (3 steps)

### Step 1 — Install dependencies
```
pip install -r requirements.txt
```

### Step 2 — Run the one-click setup script
```
python setup.py
```
This automatically:
- Deletes any stale database
- Trains all 6 ML models
- Runs Django migrations
- Creates admin user (username: admin / password: admin123)

### Step 3 — Start the server
```
python manage.py runserver
```

Open → **http://127.0.0.1:8000**

---

## 📁 Project Structure

```
symptom_checker/
├── setup.py              ← Run this first!
├── train_models.py       ← ML training script
├── manage.py             ← Django management
├── requirements.txt
├── ml_models/            ← Trained .pkl files (auto-created)
├── symptom_checker/      ← Django config (settings, urls)
└── checker/              ← Main app
    ├── models.py
    ├── views.py
    ├── ml_service.py
    ├── urls.py
    └── templates/checker/
```

---

## 🤖 ML Models Covered

| Model               | Accuracy |
|---------------------|----------|
| Logistic Regression | ~100%    |
| SVC                 | ~100%    |
| KNN                 | ~100%    |
| Random Forest       | ~99.9%   |
| Decision Tree       | ~86.9%   |
| Naive Bayes         | ~69.9%   |

Covers **41 diseases** and **130+ symptoms**.

---

## 🔑 Default Admin Login
- URL: http://127.0.0.1:8000/admin
- Username: `admin`
- Password: `admin123`

---

## ⚠️ Disclaimer
For educational and research purposes only. Not a certified medical device.
