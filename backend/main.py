'''
Project: SustainableSpot
Authors: Michelle Domagala-Tang, Justin Domagala-Tang
Description: Collects information about a location, returns recommendations for renewable energy sources
'''

from flask import Flask, request, render_template
# import requests
import openmeteo_requests
import json
import pandas as pd
import requests as req
import statistics
import numpy as np
import country_converter as coco

app = Flask(__name__)

@app.route('/', methods =["GET", "POST"])
def index():
    if request.method == "POST":
        city_name = request.form.get("city")
        country_name = request.form.get("country")

        # Call functions
        longitude, latitude, population_density, gdp_per_capita, gdp = get_city_data({'city_name' : city_name, 'country_name' : country_name})
        global json_dict
        json_dict = load_json_values()
        get_data(longitude, latitude)
        norm_eff_values, wind_params, solar_params, nuclear_params = final_calc(gdp, population_density)
        print(norm_eff_values, wind_params, solar_params, nuclear_params)

        return render_template('index.html', percentages=norm_eff_values, wind_params=wind_params, 
                               solar_params=solar_params, nuclear_params=nuclear_params, latitude=latitude, longitude=longitude)
    else:
        return render_template('index.html', percentages=None, wind_params=None, 
                               solar_params=None, nuclear_params=None, latitude=None, longitude=None)

def load_json_values():
    return {"avg-wind-speed": None, "avg-cloud-coverage": None, "population-density": None, "avg-DSR": None, "avg-surface-pressure": None}

### Call APIs to retrieve data
def get_city_data(location):
    print(location)
    country_ISO = coco.convert(names=location['country_name'], to='ISO2')
    api_url = 'https://api.api-ninjas.com/v1/city?name={}&country={}'.format(location['city_name'], country_ISO)
    response = req.get(api_url, headers={'X-Api-Key': ninja_api_key})
    rCity = response.json()
    api_url = 'https://api.api-ninjas.com/v1/country?name={}'.format(country_ISO)
    response = req.get(api_url, headers={'X-Api-Key': ninja_api_key})
    rCountry = response.json()


    longitude, latitude = rCity[0]['longitude'], rCity[0]['latitude']
    gdp_per_capita = rCountry[0]['gdp'] / rCountry[0]['population']

    population_density = (rCity[0]['population'] / 20**2)

    gdp = gdp_per_capita * population_density * 20
    
    return longitude, latitude, population_density, gdp_per_capita, gdp


def get_data(longitude, latitude): 
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "surface_pressure,cloud_cover,wind_speed_80m,direct_radiation,temperature_2m",
        "start_date": "2023-06-15",
        "end_date": "2024-01-01"
    }
    openmeteo = openmeteo_requests.Client()
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]

    # Process hourly data. The order of variables needs to be the same as requested.
    hourly = response.Hourly()
    # get_surface_pressure(hourly)

    # hourly_data = {"date": pd.date_range(
    #     start = pd.to_datetime(hourly.Time(), unit = "s"),
    #     end = pd.to_datetime(hourly.TimeEnd(), unit = "s"),
    #     freq = pd.Timedelta(seconds = hourly.Interval()),
    #     inclusive = "left"
    # )}
    
    hourly_surface_pressure = hourly.Variables(0).ValuesAsNumpy()
    hourly_cloud_cover = hourly.Variables(1).ValuesAsNumpy()
    hourly_wind_speed = hourly.Variables(2).ValuesAsNumpy()
    hourly_radiation = hourly.Variables(3).ValuesAsNumpy()
    hourly_temperature = hourly.Variables(4).ValuesAsNumpy()

    # hourly_data["surface_pressure"] = hourly_surface_pressure

    # hourly_dataframe = pd.DataFrame(data = hourly_data)
    # print(hourly_dataframe)
    json_dict["avg-wind-speed"] = statistics.mean(hourly_wind_speed)
    json_dict["avg-cloud-coverage"] = statistics.mean(hourly_cloud_cover)
    json_dict["avg-surface-pressure"] = statistics.mean(hourly_surface_pressure)
    json_dict["avg-DSR"] = statistics.mean(hourly_radiation)
    json_dict["avg-temperature"] = statistics.mean(hourly_temperature)

    return 'done'

### Rate each factor based on data



def final_calc(gdp, pop_dense):
    if pop_dense > 1200:
        scale = 2
    elif pop_dense < 150:
        scale = 0
    else:
        scale = 1
    wind_cost = {
        'maintain' : 45000,
        'startup' : 3000000
    }
    solar_cost = {
        'maintain' : 150,
        'startup' : 500
    }
    nuclear_cost = {
        'maintain' : 100000000,
        'startup' : 2500000000
    }
    wind_scale = [0.4, 0.6, 0.7]
    solar_scale = [1, 0.4, 0.15]
    nuclear_scale = [0,0.01,1]

    # cost-eff coeff
    solar_cost_eff = ((json_dict["avg-DSR"]**2 * (json_dict["avg-cloud-coverage"]/100) * 0.4) / solar_cost['maintain']) ** solar_scale[scale]
    wind_cost_eff = ((0.5 * 0.4 * np.pi * 45**2 * (json_dict["avg-wind-speed"]*(1000/60**2))**3) / wind_cost['maintain']) ** wind_scale[scale]
    nuclear_cost_eff = ((1) ** nuclear_scale[scale] *( gdp / (0.1*(nuclear_cost['startup']))))
    eff_sum = nuclear_cost_eff + wind_cost_eff + solar_cost_eff
    norm_eff_values = {'wind' : np.round(100*wind_cost_eff/eff_sum, 2), 'solar' : np.round(100*solar_cost_eff/eff_sum, 2), 'nuclear' : np.round(100*nuclear_cost_eff/eff_sum, 2) }
    wind_params = {'Average_Wind_Speed (km/h)' : json_dict["avg-wind-speed"], 'Average_Atmospheric_Pressure (hPa)' : json_dict["avg-surface-pressure"]}
    solar_params = {'Average_Daily_Solar_Radiance (W/m2)' : json_dict["avg-DSR"], 'Average_Cloud_Coverage (%)' : json_dict["avg-wind-speed"]}
    nuclear_params = {'Startup_Cost_vs_City_GDP (USD)' : nuclear_cost['startup']/gdp, 'Population_Density (people/km2)' : pop_dense}
    return norm_eff_values, wind_params, solar_params, nuclear_params

### Return recommendations 


### Run Flask Web App
if __name__ == "__main__":
    # json_file_paths = [['dynamic-location-data' , 'backend/Data/Dynamic Location Data.json'], ['static-power-data' , 'backend/Data/Static Power Data.json']]
    # longitude, latitude, population_density, gdp_per_capita, gdp = get_city_data(location)
    # json_dict = load_json_values()
    # get_data(longitude, latitude, json_dict)
    # norm_eff_values, wind_params, solar_params, nuclear_params = final_calc(json_dict, gdp, population_density)
    # print(norm_eff_values, wind_params, solar_params, nuclear_params)
    app.run(host="127.0.0.1", port=8080, debug=True)