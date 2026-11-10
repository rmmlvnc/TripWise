# Switch to WeatherAPI.com

The weather code now uses WeatherAPI.com, not Open-Meteo. Keep the Render variable
WEATHERAPI_API_KEY set to your own valid key. No additional packages are required.
For local development, fill in WEATHERAPI_API_KEY in api_credentials.json and restart
Django. That private file is ignored by Git and must not be uploaded.

Upload the changed planner code, travel_planner settings, and example JSON file.
Render must finish deploying the new GitHub commit before the site changes.

The page should say WeatherAPI.com and 3 days. If it still says Open-Meteo and
16 days, Render is still serving an older deployment. Verify the latest deploy
commit and its build logs. Refresh the browser after deployment succeeds.

The existing ForecastCache table is reused with a new weatherapi namespace. Old
Open-Meteo cooldowns do not affect WeatherAPI.com. No new migration is needed for
this provider switch; existing migrations still run normally during Render builds.

Provider documentation: https://www.weatherapi.com/docs/forecast-api/
Free-plan coverage: https://www.weatherapi.com/pricing
