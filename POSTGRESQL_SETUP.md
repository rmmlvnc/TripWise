# TripWise PostgreSQL setup

Status: configuration prepared; no PostgreSQL server has been connected yet.
The default settings still use SQLite so the application continues to work.

1. Stop the Django development server.
2. Install PostgreSQL locally or obtain a hosted PostgreSQL database.
   Create an EMPTY database named tripwise and a login role that owns it.
   Use pgAdmin or your provider dashboard. Do not import into a database containing other records.
3. In PowerShell, from this project folder:

```powershell
..\Scripts\python.exe -m pip install -r requirements-postgresql.txt
New-Item -ItemType Directory -Force backups
..\Scripts\python.exe manage.py dumpdata --settings=travel_planner.settings --natural-foreign --natural-primary --exclude=contenttypes --exclude=auth.permission --exclude=sessions.session --output=backups/sqlite-data.json
```

This exports existing users (including password hashes), trips, and expenses.
Do not share the export or commit it to Git. Keep db.sqlite3 as your original backup.

4. Enter your connection details locally (the password input is hidden):

```powershell
. .\use-postgresql.ps1
..\Scripts\python.exe manage.py migrate
..\Scripts\python.exe manage.py loaddata backups/sqlite-data.json
..\Scripts\python.exe manage.py check --database default
..\Scripts\python.exe manage.py runserver
```

Stop if any command fails. Only import once into a newly migrated empty database.
On an existing populated PostgreSQL database, plan a separate merge instead.

5. Sign in with your existing account. Verify your trips and expenses, create a
   test trip, edit it, restart Django, and confirm the changes remain.

Each new terminal needs `. .\use-postgresql.ps1` before running Django.
SQLite remains unchanged; return to it by closing this terminal and opening a new
one without loading the PostgreSQL script. New PostgreSQL records do not sync to SQLite.

Saving, editing, and deleting records use the same Django views and models.
For FUTURE changes to model fields, run makemigrations followed by migrate with
PostgreSQL configured. Do not run migrations merely to edit a trip or expense.
