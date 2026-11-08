#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
export DJANGO_SETTINGS_MODULE=travel_planner.settings_production
python -m pip install -r requirements.txt
python manage.py check --settings=travel_planner.settings_production
python manage.py collectstatic --noinput --settings=travel_planner.settings_production
python manage.py migrate --noinput --settings=travel_planner.settings_production
