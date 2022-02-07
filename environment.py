import random


class Environment:
    def __init__(self, weather, air_quality):
        if weather is None:
            self.weather = random.random()
            print(f'Random weather: {self.weather}')
        else:
            self.weather = weather
        
        if air_quality is None:
            self.air_quality = random.random()
            print(f'Random air quality: {self.air_quality}')
        else:
            self.air_quality = air_quality
