"""
setup.py — Run ONCE after extracting the project.
Deletes old DB, trains models, runs migrations, creates admin.
Usage: python setup.py
"""
import os, sys, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))

def run(cmd):
    print(f"\n>>> {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=BASE)
    if r.returncode != 0:
        print(f"ERROR: command failed"); sys.exit(1)

print("=" * 56)
print("  MediAI v2 — Multimodal Healthcare System Setup")
print("=" * 56)

# 1. Delete stale DB
db = os.path.join(BASE, 'db.sqlite3')
if os.path.exists(db):
    os.remove(db); print("\n✓ Deleted old db.sqlite3")
else:
    print("\n✓ No existing db.sqlite3")

# 2. Create media dirs
os.makedirs(os.path.join(BASE,'media','uploads'), exist_ok=True)
print("✓ media/uploads directory ready")

# 3. Train ML models
meta = os.path.join(BASE,'ml_models','metadata.json')
if not os.path.exists(meta):
    print("\n⚙  Training ML models (~30 seconds)…")
    run("python train_models.py")
else:
    print("✓ ML models already trained")

# 4. Migrations
print("\n⚙  Running migrations…")
run("python manage.py migrate --run-syncdb")

# 5. Create admin
print("\n⚙  Creating admin user…")
create_admin = """
import django, os, sys
sys.path.insert(0, r'""" + BASE.replace('\\','\\\\') + """')
os.environ['DJANGO_SETTINGS_MODULE'] = 'symptom_checker.settings'
django.setup()
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin','admin@mediAI.com','admin123')
    print('  Created: username=admin  password=admin123')
else:
    print('  Admin already exists')
"""
subprocess.run([sys.executable, "-c", create_admin], cwd=BASE)

print("\n" + "=" * 56)
print("  ✅  Setup complete!")
print("=" * 56)
print("\n  Start server:  python manage.py runserver")
print("  Open browser:  http://127.0.0.1:8000")
print("  Admin panel:   http://127.0.0.1:8000/admin")
print("  Admin login:   admin / admin123\n")
