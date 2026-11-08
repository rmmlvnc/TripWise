# Deploy TripWise on Render

Prepared files: requirements.txt, build.sh, .python-version,
travel_planner/settings_production.py, and .gitattributes.
Local SQLite and PostgreSQL configuration is unchanged.

1. Push this project to your GitHub repository. manage.py should be at the root.
   Do not upload api_credentials.json, .env files, backups, database exports, or
   generated staticfiles. They are ignored by Git. Do not copy your entire
   django-env folder or virtual environment into the repository.
2. Create a Render PostgreSQL database in the same region as your web service.
3. Create a Render Web Service connected to your repository:

| Setting | Value |
| --- | --- |
| Language | Python 3 |
| Root directory | Leave blank if manage.py is at the repository root |
| Build command | bash build.sh |
| Start command | gunicorn travel_planner.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60 --access-logfile - |

4. Add these environment variables BEFORE deploying:

| Variable | Value |
| --- | --- |
| DJANGO_SETTINGS_MODULE | travel_planner.settings_production |
| SECRET_KEY | A NEW random secret, at least 50 characters; use Render Generate |
| DATABASE_URL | Render PostgreSQL Internal Database URL (same region) |
| GEOAPIFY_API_KEY | Your actual Geoapify key |
| CLOUDINARY_CLOUD_NAME | Your actual cloud name |
| CLOUDINARY_API_KEY | Your actual API key |
| CLOUDINARY_API_SECRET | The matching secret from the same Cloudinary key row |

RENDER_EXTERNAL_HOSTNAME is supplied automatically by Render. For a custom domain,
also set ALLOWED_HOSTS to its hostname (comma-separated if multiple), without https://.
The default onrender.com hostname remains allowed automatically.

5. Deploy. The build script installs dependencies, checks configuration, collects
   static files, and applies migrations to the HOSTED PostgreSQL database.
6. Open your Render URL. Verify registration, login, trip edits, search, weather,
   conversion, destination information, and photo uploads. Confirm styling loads
   with DEBUG=False. Your Cloudinary images remain in Cloudinary.

The hosted database starts empty. Existing local accounts and trips do NOT move
automatically. You can register a new account online or plan a one-time data
transfer separately. Do not import a local backup repeatedly during deployment.

The build script never creates an admin account or loads personal data. If you
need an administrator, use a secure management session connected to the hosted DB.

The application is not deployed by creating these files. You still need to create
the Render services and supply their environment values. Review Render's current
free PostgreSQL expiration and web-service limits before selecting plans.

References:
https://render.com/docs/deploy-django
https://render.com/docs/python-version
https://render.com/docs/free

## Verification notes

Production settings were checked with temporary placeholder environment values,
without connecting to a real hosted database. Static collection succeeded; the
production login page and all four hashed CSS/JS assets returned HTTP 200 with
DEBUG=False through WhiteNoise. Real migrations and hosted connectivity are
verified during your Render deployment.

The deployment security check reports two optional HSTS policy warnings:
include-subdomains and preload. These remain disabled deliberately until you
control the final domain and its HTTPS policy. HTTPS redirect, secure cookies,
and a one-hour HSTS policy are enabled for the current hostname.

Run build.sh on Render, not in Windows PowerShell. Gunicorn is the Linux production
server; continue using manage.py runserver for local Windows development.
