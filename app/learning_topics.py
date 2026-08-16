TOPICS = [
    {
        "id": "rest_api",
        "title": "How REST API Works",
        "icon": "&#128268;",
        "content": """<h2>How REST API Works</h2>
<p>A REST API (Application Programming Interface) lets two applications talk to each other over HTTP.</p>

<h3>The Basic Idea</h3>
<p>Think of a restaurant. You (the client) look at a menu and tell the waiter (the API) what you want. The waiter goes to the kitchen (the server) and brings back your food (the data).</p>

<h3>HTTP Methods</h3>
<pre><code>GET    /api/jobs        -> Get all jobs
POST   /api/jobs        -> Create a new job
PUT    /api/jobs/1      -> Update job with id=1
DELETE /api/jobs/1      -> Delete job with id=1</code></pre>

<h3>A Real Example</h3>
<pre><code>import requests

# GET request - fetch all jobs
response = requests.get("https://api.example.com/api/jobs")
jobs = response.json()

# POST request - create a job
new_job = {"title": "Web Developer", "company": "Acme Corp"}
response = requests.post("https://api.example.com/api/jobs", json=new_job)</code></pre>

<h3>Status Codes</h3>
<ul>
  <li><code>200</code> - OK (success)</li>
  <li><code>201</code> - Created (something was added)</li>
  <li><code>400</code> - Bad Request (you sent wrong data)</li>
  <li><code>404</code> - Not Found (resource doesn't exist)</li>
  <li><code>500</code> - Server Error (something broke on the server)</li>
</ul>

<h3>REST Principles</h3>
<ol>
  <li><strong>Stateless</strong> - Each request contains all info needed (no session on server)</li>
  <li><strong>Resource-based</strong> - Everything is a resource (jobs, users, profiles)</li>
  <li><strong>Uniform interface</strong> - Same HTTP methods everywhere</li>
</ol>"""
    },
    {
        "id": "jwt_auth",
        "title": "How JWT Authentication Works",
        "icon": "&#128274;",
        "content": """<h2>How JWT Authentication Works</h2>
<p>JWT (JSON Web Token) is a secure way to authenticate users without storing sessions on the server.</p>

<h3>The Flow</h3>
<ol>
  <li>User logs in with email + password</li>
  <li>Server validates and creates a JWT token</li>
  <li>Token is sent back to the client</li>
  <li>Client stores the token (usually in localStorage)</li>
  <li>Every future request includes the token in the header</li>
</ol>

<h3>JWT Structure</h3>
<p>A JWT has 3 parts separated by dots: <code>Header.Payload.Signature</code></p>
<pre><code>eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxfQ.abc123signature</code></pre>

<h3>Implementation in Flask</h3>
<pre><code>import jwt
from datetime import datetime, timedelta

SECRET = "your-secret-key"

# Create token
def create_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

# Verify token
def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        return None  # Token expired
    except jwt.InvalidTokenError:
        return None  # Invalid token</code></pre>

<h3>Using JWT in Flask Routes</h3>
<pre><code>from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/api/jobs")
@login_required
def get_jobs():
    return jsonify({"jobs": [...]})</code></pre>

<h3>Why JWT over Session?</h3>
<ul>
  <li>Server doesn't need to store sessions (scalable!)</li>
  <li>Works across different domains</li>
  <li>Mobile app friendly</li>
</ul>"""
    },
    {
        "id": "migration",
        "title": "Database Migration Explained",
        "icon": "&#128194;",
        "content": """<h2>Database Migration Explained</h2>
<p>Migrations are like version control for your database schema. They let you change your database structure without losing data.</p>

<h3>Why Migrations?</h3>
<p>Imagine you have a <code>users</code> table and later need to add a <code>phone</code> column. Instead of manually running SQL, you write a migration file that can be applied or rolled back.</p>

<h3>Flask-Migrate (Alembic)</h3>
<pre><code># Install
pip install flask-migrate

# Initialize
flask db init

# Create a migration
flask db migrate -m "add phone column to users"

# Apply migration
flask db upgrade

# Rollback
flask db downgrade</code></pre>

<h3>Migration File Example</h3>
<pre><code>def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(100), default=''))

def downgrade():
    op.drop_column('users', 'phone')</code></pre>

<h3>Best Practices</h3>
<ol>
  <li>Always review auto-generated migrations before applying</li>
  <li>Test both upgrade AND downgrade</li>
  <li>Never edit a migration that's already been applied</li>
  <li>Commit migration files to git</li>
</ol>

<h3>SQLite Simple Migration (No Flask-Migrate)</h3>
<pre><code>import sqlite3

def add_column_if_missing(db_path, table, column, col_type):
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
    conn.close()

# Usage
add_column_if_missing("data.db", "users", "phone", "VARCHAR(100) DEFAULT ''")</code></pre>"""
    },
    {
        "id": "seeding",
        "title": "How to Seed Data",
        "icon": "&#127793;",
        "content": """<h2>How to Seed Data</h2>
<p>Seeding is the process of populating your database with initial data (like default roles, test users, etc.).</p>

<h3>Why Seed?</h3>
<ul>
  <li>Test data for development</li>
  <li>Default roles, categories, or settings</li>
  <li>Demo data for new users</li>
</ul>

<h3>Flask Seed Script</h3>
<pre><code>from app.db import SessionLocal, Job, User

def seed_jobs():
    session = SessionLocal()
    jobs = [
        {"title": "Web Developer", "company": "Acme", "role": "web developer"},
        {"title": "AI Engineer", "company": "TechCo", "role": "ai engineer"},
    ]
    for data in jobs:
        if not session.query(Job).filter_by(title=data["title"]).first():
            session.add(Job(**data))
    session.commit()
    session.close()

# Run: python -m app.seed</code></pre>

<h3>Using Faker for Realistic Data</h3>
<pre><code>from faker import Faker
fake = Faker()

def seed_fake_users(count=50):
    session = SessionLocal()
    for _ in range(count):
        user = User(
            username=fake.user_name(),
            password_hash=generate_password_hash("password123")
        )
        session.add(user)
    session.commit()
    session.close()</code></pre>

<h3>Command Line Seed</h3>
<pre><code># app/seed.py
import sys
from app.seed import seed_jobs, seed_fake_users

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("jobs", "all"):
        seed_jobs()
    if cmd in ("users", "all"):
        seed_fake_users()
    print("Seeding complete!")</code></pre>

<h3>Best Practice</h3>
<p>Use <code>get_or_create</code> pattern so seeding is idempotent (safe to run multiple times).</p>"""
    },
    {
        "id": "payment",
        "title": "How to Integrate Payment System",
        "icon": "&#128179;",
        "content": """<h2>How to Integrate Payment System</h2>
<p>Adding payments to your app involves connecting to a payment gateway like Stripe, SSLCommerz (for Bangladesh), or bKash.</p>

<h3>Payment Flow</h3>
<ol>
  <li>User clicks "Pay" on your app</li>
  <li>App sends payment request to gateway</li>
  <li>Gateway processes payment (card/mobile)</li>
  <li>Gateway sends confirmation back to your app</li>
  <li>You update the order status</li>
</ol>

<h3>Stripe Integration (Python)</h3>
<pre><code>import stripe
stripe.api_key = "sk_test_your_key"

# Create a payment intent
def create_payment(amount_bdt):
    intent = stripe.PaymentIntent.create(
        amount=amount_bdt * 100,  # Stripe uses cents/paisa
        currency="bdt",
        metadata={"order_id": 123}
    )
    return intent.client_secret

# Handle webhook (payment confirmation)
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    if event["type"] == "payment_intent.succeeded":
        order_id = event["data"]["object"]["metadata"]["order_id"]
        mark_order_paid(order_id)
    return "", 200</code></pre>

<h3>SSLCommerz (Bangladesh)</h3>
<pre><code>import requests

def init_sslcommerz(amount, order_id):
    data = {
        "store_id": "your_store_id",
        "store_passwd": "your_password",
        "total_amount": amount,
        "currency": "BDT",
        "tran_id": order_id,
        "success_url": "https://yoursite.com/payment/success",
        "fail_url": "https://yoursite.com/payment/fail",
    }
    resp = requests.post("https://sandbox.sslcommerz.com/gwprocess/v4/api.php", data=data)
    return resp.json()["GatewayPageURL"]</code></pre>

<h3>Key Considerations</h3>
<ul>
  <li>Always verify payments server-side (never trust client-side)</li>
  <li>Use webhooks for payment confirmation</li>
  <li>Handle failures gracefully</li>
  <li>Store transaction IDs for reference</li>
</ul>"""
    },
    {
        "id": "django_scaffold",
        "title": "How to Scaffold a Django Project",
        "icon": "&#128736;",
        "content": """<h2>How to Scaffold a Django Project</h2>
<p>Scaffolding means quickly setting up the basic structure of a Django project.</p>

<h3>Step 1: Create Project</h3>
<pre><code>pip install django
django-admin startproject jobpilot
cd jobpilot</code></pre>

<h3>Step 2: Create Apps</h3>
<pre><code>python manage.py startapp jobs
python manage.py startapp accounts
python manage.py startapp learning</code></pre>

<h3>Step 3: Project Structure</h3>
<pre><code>jobpilot/
  jobpilot/
    settings.py
    urls.py
    wsgi.py
  jobs/
    models.py
    views.py
    urls.py
    admin.py
  accounts/
    models.py
    views.py
    urls.py
  manage.py</code></pre>

<h3>Step 4: Settings.py</h3>
<pre><code>INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'jobs',
    'accounts',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}</code></pre>

<h3>Step 5: Models</h3>
<pre><code># jobs/models.py
from django.db import models

class Job(models.Model):
    title = models.CharField(max_length=300)
    company = models.CharField(max_length=300, blank=True)
    snippet = models.TextField(blank=True)
    role = models.CharField(max_length=100, blank=True)
    posted_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title</code></pre>

<h3>Step 6: Migrate</h3>
<pre><code>python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver</code></pre>"""
    },
    {
        "id": "django_developer",
        "title": "Steps to Be a Good Django Developer",
        "icon": "&#128640;",
        "content": """<h2>Steps to Be a Good Django Developer</h2>

<h3>1. Master Python First</h3>
<p>Before Django, be comfortable with: functions, classes, decorators, generators, list comprehensions, and virtual environments.</p>

<h3>2. Learn Django Basics</h3>
<ul>
  <li>Models & ORM (database queries)</li>
  <li>Views (function-based and class-based)</li>
  <li>Templates (Jinja2-like syntax)</li>
  <li>Forms & Validation</li>
  <li>URL routing</li>
</ul>

<h3>3. Understand Django's "Batteries Included"</h3>
<pre><code># Authentication
from django.contrib.auth.models import User

# Admin
admin.site.register(Job)

# Static files
{% load static %}
<link rel="stylesheet" href="{% static 'style.css' %}">

# Messages framework
from django.contrib import messages
messages.success(request, "Job saved!")</code></pre>

<h3>4. Learn Django REST Framework</h3>
<pre><code># api/views.py
from rest_framework import viewsets
from .models import Job
from .serializers import JobSerializer

class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer</code></pre>

<h3>5. Practice Projects</h3>
<ol>
  <li>Build a job board (like JobPilot!)</li>
  <li>Build a blog with comments</li>
  <li>Build an e-commerce site</li>
  <li>Build a REST API</li>
</ol>

<h3>6. Must-Know Topics</h3>
<ul>
  <li>Signals (post_save, pre_save)</li>
  <li>Custom middleware</li>
  <li>Database optimization (select_related, prefetch_related)</li>
  <li>Caching (Redis, Memcached)</li>
  <li>Deployment (Gunicorn + Nginx)</li>
</ul>"""
    },
    {
        "id": "django_mustknow",
        "title": "Must-Know Things for Django Developer",
        "icon": "&#128218;",
        "content": """<h2>Must-Know Things for Django Developer</h2>

<h3>1. ORM Queries</h3>
<pre><code># Get all jobs
Job.objects.all()

# Filter
Job.objects.filter(role="web developer")

# Exclude
Job.objects.exclude(company="")

# Chaining
Job.objects.filter(role="web developer").exclude(company="").order_by("-posted_date")

# Aggregations
from django.db.models import Count
Job.objects.values("role").annotate(count=Count("id"))

# Raw SQL (when needed)
Job.objects.raw("SELECT * FROM jobs WHERE role = %s", ["web developer"])</code></pre>

<h3>2. Class-Based Views</h3>
<pre><code>from django.views.generic import ListView, DetailView

class JobListView(ListView):
    model = Job
    template_name = "jobs/list.html"
    paginate_by = 20

class JobDetailView(DetailView):
    model = Job
    template_name = "jobs/detail.html"</code></pre>

<h3>3. Django Settings for Production</h3>
<pre><code># settings.py
DEBUG = False
ALLOWED_HOSTS = ["yourdomain.com"]
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "jobpilot",
        "HOST": "localhost",
    }
}</code></pre>

<h3>4. Testing</h3>
<pre><code># jobs/tests.py
from django.test import TestCase
from .models import Job

class JobModelTest(TestCase):
    def setUp(self):
        Job.objects.create(title="Web Developer", role="web developer")

    def test_job_creation(self):
        job = Job.objects.get(title="Web Developer")
        self.assertEqual(job.role, "web developer")</code></pre>

<h3>5. Common Gotchas</h3>
<ul>
  <li>N+1 queries (use <code>select_related</code> and <code>prefetch_related</code>)</li>
  <li>Forgetting <code>related_name</code> on ForeignKey</li>
  <li>Not using <code>get_or_create</code> for idempotent operations</li>
  <li>Storing secrets in settings.py (use environment variables!)</li>
</ul>"""
    },
    {
        "id": "django_rest_api",
        "title": "Building REST API with Django",
        "icon": "&#128241;",
        "content": """<h2>Building REST API with Django</h2>

<h3>Setup</h3>
<pre><code>pip install djangorestframework
# settings.py
INSTALLED_APPS += ['rest_framework']</code></pre>

<h3>Serializer (like a form for API)</h3>
<pre><code># jobs/serializers.py
from rest_framework import serializers
from .models import Job

class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["id", "title", "company", "snippet", "role", "posted_date"]</code></pre>

<h3>ViewSet (CRUD logic)</h3>
<pre><code># jobs/views.py
from rest_framework import viewsets
from .models import Job
from .serializers import JobSerializer

class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs</code></pre>

<h3>URL Configuration</h3>
<pre><code># jobs/urls.py
from rest_framework.routers import DefaultRouter
from .views import JobViewSet

router = DefaultRouter()
router.register(r"jobs", JobViewSet)
urlpatterns = router.urls

# jobpilot/urls.py
from django.urls import path, include
urlpatterns = [
    path("api/", include("jobs.urls")),
]</code></pre>

<h3>Testing Your API</h3>
<pre><code># Run server
python manage.py runserver

# Test with curl
curl http://localhost:8000/api/jobs/
curl http://localhost:8000/api/jobs/?role=web+developer

# Or use DRF's built-in browsable API (visit in browser!)</code></pre>

<h3>Authentication for API</h3>
<pre><code># settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}</code></pre>"""
    },
    {
        "id": "git_basics",
        "title": "Git Essentials for Developers",
        "icon": "&#128196;",
        "content": """<h2>Git Essentials for Developers</h2>

<h3>Basic Commands</h3>
<pre><code>git init                    # Start a new repo
git add .                   # Stage all changes
git commit -m "message"     # Save changes
git push origin main        # Upload to remote
git pull origin main        # Download changes
git status                  # See what changed
git log --oneline           # See history</code></pre>

<h3>Branching</h3>
<pre><code>git branch feature-x        # Create branch
git checkout feature-x      # Switch to it
git checkout -b feature-x   # Create + switch
git merge feature-x         # Merge into current
git branch -d feature-x     # Delete branch</code></pre>

<h3>The Git Workflow</h3>
<ol>
  <li>Create a branch for new feature</li>
  <li>Make changes, commit often</li>
  <li>Push branch to remote</li>
  <li>Create Pull Request</li>
  <li>Code review, then merge</li>
</ol>

<h3>Undo Mistakes</h3>
<pre><code>git reset HEAD file.txt     # Unstage a file
git checkout -- file.txt    # Discard changes
git revert HEAD             # Undo last commit (safe)
git reset --hard HEAD       # DANGER: lose all changes</code></pre>

<h3>.gitignore</h3>
<pre><code># .gitignore
*.pyc
__pycache__/
.env
data/
*.db
venv/</code></pre>"""
    },
    {
        "id": "linux_basics",
        "title": "Linux Commands Every Developer Should Know",
        "icon": "&#128421;",
        "content": """<h2>Linux Commands Every Developer Should Know</h2>

<h3>Navigation</h3>
<pre><code>pwd                     # Where am I?
ls -la                  # List all files (with details)
cd /path/to/dir         # Change directory
cd ~                    # Go to home
cd ..                   # Go up one level</code></pre>

<h3>File Operations</h3>
<pre><code>cp file.txt backup.txt  # Copy
mv old.txt new.txt      # Move/rename
rm file.txt             # Delete
mkdir new_dir           # Create directory
touch new_file.txt      # Create empty file
cat file.txt            # Show file contents
less file.txt           # View with pagination</code></pre>

<h3>Search & Find</h3>
<pre><code>find . -name "*.py"           # Find files by name
grep -r "TODO" .              # Search in files
grep -r "function" --include="*.js" .  # Search JS files only</code></pre>

<h3>Process Management</h3>
<pre><code>ps aux                 # List running processes
kill PID               # Kill a process
kill -9 PID            # Force kill
top                    # Live process monitor
htop                   # Better top (if installed)</code></pre>

<h3>Networking</h3>
<pre><code>curl https://api.example.com    # HTTP request
wget https://example.com/file   # Download file
ping google.com                 # Test connectivity
netstat -tlnp                   # List open ports</code></pre>

<h3>Permissions</h3>
<pre><code>chmod +x script.sh      # Make executable
chmod 755 file.txt      # rwxr-xr-x
chown user:group file   # Change owner</code></pre>"""
    },
    {
        "id": "docker_basics",
        "title": "Docker for Developers",
        "icon": "&#128051;",
        "content": """<h2>Docker for Developers</h2>
<p>Docker lets you package your app with everything it needs to run, anywhere.</p>

<h3>Core Concepts</h3>
<ul>
  <li><strong>Image</strong> - A blueprint (like a class)</li>
  <li><strong>Container</strong> - A running instance (like an object)</li>
  <li><strong>Dockerfile</strong> - Recipe to build an image</li>
  <li><strong>Docker Compose</strong> - Run multiple containers together</li>
</ul>

<h3>Dockerfile Example</h3>
<pre><code>FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "jobpilot.wsgi:app", "--bind", "0.0.0.0:8000"]</code></pre>

<h3>Basic Commands</h3>
<pre><code>docker build -t jobpilot .           # Build image
docker run -p 8000:8000 jobpilot      # Run container
docker ps                             # List running containers
docker stop CONTAINER_ID             # Stop a container
docker logs CONTAINER_ID             # See logs</code></pre>

<h3>Docker Compose</h3>
<pre><code># docker-compose.yml
version: "3.8"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///data/jobs.db
    volumes:
      - ./data:/app/data
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"</code></pre>

<pre><code>docker-compose up -d          # Start all services
docker-compose down           # Stop all
docker-compose logs -f        # Follow logs</code></pre>"""
    },
]
