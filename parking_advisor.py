from functools import reduce
import math
import random
import traci
from traci.exceptions import FatalTraCIError, TraCIException
from lxml import etree as ET


parkings_file = 'parkings.add.xml'
weights_file = 'weights.xml'

n_propositions = 5

max_time_total = 1200
max_time_walking = 600

coef_free_space = 2


WEEK_LEN_SECONDS = 7 * 24 * 3600
DAY_LEN_SECONDS = 24 * 3600


class ParkingAdvisor:
    def __init__(self):
        self._load_parking_lots()
        self._weight_config = self._load_weight_config()


    def suggest_targets(self, vehicle):
        return []


    def pick_parking_areas(self, vehicle, target):
        parking_areas_nearby = self._find_nearest_parking_areas(target)
        self._update_contextual_weights(vehicle, target)
        reccomended_parking_areas = sorted(parking_areas_nearby, key=lambda parking_area: self._cost(parking_area, vehicle, target))
        return reccomended_parking_areas[:n_propositions]


    def _load_parking_lots(self):
        parking_tree = ET.parse(parkings_file)
        self._parking_lots = parking_tree.xpath('/additional')[0]
        self._all_parking_areas_ids = [parking.attrib['id'] for parking in self._parking_lots.xpath('./parkingArea')]
        self._total_parking_capacity = sum([int(parking.attrib['roadsideCapacity']) for parking in self._parking_lots.xpath('./parkingArea')])

    
    def _load_weight_config(self):
        return ET.parse(weights_file)

    
    def _find_nearest_parking_areas(self, target):
        # TODO: return all parking areas within specified radius
        return random.choices(self._parking_lots.xpath('./parkingArea'), k=10)


    def _update_contextual_weights(self, vehicle, target):
        """ Sets weights tailored to a specific query based on context. """
        weights_by_individual_factors = [
            self._weights_by_global_free_slots_ratio()
        ]
        summed_weights = reduce(lambda acc, weights: [sum(w) for w in zip(acc, weights)], weights_by_individual_factors, [0, 0, 0])
        mean_weights = [w / len(weights_by_individual_factors[0]) for w in summed_weights]
        
        self._weight_time = mean_weights[0]
        self._weight_walking = mean_weights[1]
        self._weight_prob = mean_weights[2]


    def _weights_by_global_free_slots_ratio(self):
        total_occupied_spaces = sum([int(traci.parkingarea.getVehicleCount(parking)) for parking in self._all_parking_areas_ids])
        global_free_slots_ratio = (self._total_parking_capacity - total_occupied_spaces) / self._total_parking_capacity
        return self._weights_by_factor('globalFreeSlotsAvailability', global_free_slots_ratio)


    def _weights_by_factor(self, factor, value):
        levels = self._weight_config.xpath(f'/weights/factor[@id="{factor}"]/level')
        ordered_lvls = sorted(levels, key=lambda lvl: float(lvl.attrib['upperThreshold']))
        applicable_level = [lvl for lvl in ordered_lvls if float(lvl.attrib['upperThreshold']) >= value][0]
        
        weight_value = lambda weight_name: float(applicable_level.xpath(f'./weight[@id="{weight_name}"]')[0].attrib['value'])
        weight_total_time = weight_value('totalTime')
        weight_walking_time = weight_value('walkingTime')
        weight_prob_of_success = weight_value('probOfSuccess')
        return weight_total_time, weight_walking_time, weight_prob_of_success        

    
    def _cost(self, parking_area, vehicle, target):
        time_total = self._get_time_total(parking_area, target, vehicle)
        time_walking = self._get_time_walking(parking_area, target)
        prob_of_success = self._get_prob_of_success(parking_area, vehicle)
        return self._weight_time * time_total / max_time_total + \
               self._weight_walking * time_walking / max_time_walking + \
               self._weight_prob * prob_of_success

    
    def _get_time_total(self, parking_area, target, vehicle):
        return 0

    
    def _get_time_walking(self, parking_area, target):
        return 0


    def _get_prob_of_success(self, parking_area, vehicle):
        n_free_spots = self._get_free_spots_number(parking_area)
        # length_diff = ...
        # width_diff = ...
        # n_free_spots_nearby = ...

        sigmoid = lambda x, c: c * (1 / (1 + math.exp(-x / 5)) - 0.5)

        factors = [
            sigmoid(n_free_spots, coef_free_space)
        ]
        return sum(factors) / len(factors)


    def _get_free_spots_number(self, parking_area):
        n_parked_cars = traci.parkingarea.getVehicleCount(parking_area.attrib['id'])
        capacity = int(parking_area.attrib['roadsideCapacity'])
        return capacity - n_parked_cars
