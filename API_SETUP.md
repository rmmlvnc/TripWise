# TripWise: five external APIs

Implemented in planner/services.py, planner/api_views.py, and each trip details page.

## Apply the database migration first

Stop the running Django server. In the SAME PowerShell window with your PostgreSQL
connection configured:

```powershell
..\Scripts\python.exe manage.py migrate
```

If using a new terminal, load `. .\use-postgresql.ps1` first (see POSTGRESQL_SETUP.md).
Do not re-import the SQLite backup. This migration only adds coordinates and photos.

Dependencies are requests and Pillow, already available in the current environment.
For a fresh environment:

```powershell
..\Scripts\python.exe -m pip install -r requirements-apis.txt
```

## Set up credentials locally

Open api_credentials.json in VS Code and fill in the four empty values.
This file is ignored by Git. Never paste these secrets in chat or put them in templates.
If the private file is missing, copy api_credentials.example.json to api_credentials.json.
Environment variables with the same names override this file when deploying.

### Geoapify

1. Create an account at https://myprojects.geoapify.com/.
2. Create a project and copy its API key.
3. Put it in GEOAPIFY_API_KEY in the private JSON file.
4. In a trip, search for a destination and select the matching result.
5. Coordinates and the selected address are saved in PostgreSQL.

Search requests originate on the Django server, not the browser. Configure any
provider key restrictions accordingly. Keep Geoapify and OpenStreetMap attribution.

### Cloudinary

1. Create a free account at https://cloudinary.com/users/register/free.
2. Open the product environment dashboard / API Keys page.
3. Enter the cloud name, API key, and API secret into CLOUDINARY_CLOUD_NAME,
   CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in the private JSON file.
4. Restart Django after changing credentials.
5. Open a trip and upload a JPEG, PNG, or WebP image no larger than 5 MB.

Django validates the image, uploads it to Cloudinary using backend authentication,
and stores only its HTTPS delivery URL and public ID in PostgreSQL. Removing a photo
also deletes it in Cloudinary. Deleting a trip removes its cloud photos first;
if the provider fails, the trip remains so you can retry.

### Open-Meteo

No API key for the public noncommercial service. Select a destination using Geoapify,
then click Check forecast. Only trip dates within the next 16 days are requested.
For trips beyond that horizon, the page explains when to check again. A trip partly
inside the window displays only the available dates, clearly labeled.

### Frankfurter

No API key. Select a target currency and click Convert. Uses the latest available
PHP reference rate from https://api.frankfurter.dev/v2/rate/php/usd (target varies).
The rate date is displayed; weekends and holidays may use an older rate.
Your stored budget and expenses stay in PHP. Estimates do not include bank fees.
The PHP to PHP option returns the unchanged amount locally, without an API request.

### Wikipedia / MediaWiki

No API key. Click Explore destination. The server searches English Wikipedia through
its MediaWiki API, retrieves the matching article introduction, and displays plain
text with a source link and attribution. Search matches may be ambiguous.

## Start and verify

```powershell
..\Scripts\python.exe manage.py runserver
```

Open a trip details page. Test each of the five numbered cards. Geoapify and Cloudinary
cannot be verified live until you add their credentials. Weather, currency, and
Wikipedia calls were checked against their live providers during development.
Never upload sensitive personal photos to a public image delivery service.

Local automated tests use a disposable SQLite test database and mocked external
requests, without changing the PostgreSQL database or spending API quotas:

```powershell
..\Scripts\python.exe manage.py test planner --settings=travel_planner.settings
```

External services have timeouts and helpful failure messages. Requests happen only
when a customer clicks a tool, so an API outage does not block the trip details page.
Searches and article introductions cache for a day, forecasts for 30 minutes, and
exchange rates for an hour. The default Django cache is per process.

## References

- https://apidocs.geoapify.com/docs/geocoding/
- https://open-meteo.com/en/docs
- https://frankfurter.dev/
- https://www.mediawiki.org/wiki/API:Query
- https://www.mediawiki.org/wiki/Extension:TextExtracts#API
- https://cloudinary.com/documentation/upload_images
