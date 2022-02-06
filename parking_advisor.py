from math import exp, sqrt
from functools import reduce
import math
import random
import traci
from traci.exceptions import FatalTraCIError, TraCIException
from lxml import etree as ET
import os
import psycopg2


from constants import *


parkings_file = os.path.join(sumo_rel_path, gen_subdir, parkings_gen_filename)
weights_file = os.path.join(sumo_rel_path, config_subdir, weights_filename)
users_file = os.path.join(sumo_rel_path, config_subdir, users_conf_filename)


def gaussian(x, mean=0.0, sd=(POS_TIME_DELTA_SEC - NEG_TIME_DELTA_SEC) / 3):
    var = float(sd)**2
    denom = (2*math.pi*var)**.5
    num = math.exp(-(float(x)-float(mean))**2/(2*var))
    return num/denom


def sigmoid(x):
    return 1 / (1 + exp(-x + 4))


def sigmoid_star(x):
    return 2 / (1 + exp(x / (FREQ_N * WEEK_LEN_SECONDS)))


class ParkingAdvisor:
    def __init__(self, time_controller):
        self._time_controller = time_controller

        self._load_parking_lots()
        self._load_users()
        self._weight_config = self._load_weight_config()


    def suggest_targets(self, vehicle):
        self._invalidate_eta_cache()
        self._loc = self._get_user_localization(vehicle)
	
        target_sets = {
            'nearby_targets': self._get_nearby_targets(),
            'calendar_targets': self._get_calendar_targets(vehicle),
            'frequent_targets': self._get_frequent_targets(vehicle),
            'repeating_targets': self._get_repeating_targets(vehicle)
        }

        targets = {target for target_set in target_sets.values() for target in (target_set.keys() if type(target_set) == dict else [t[0] for t in target_set])}
        
        ordered_targets = sorted(targets, key=lambda target: self._confidence(target, target_sets))[::-1]
        return ordered_targets


    def _get_user_id(self, vehicle):
        return int(vehicle.split('_')[0][3:])


    def _get_user_localization(self, vehicle):
        pos_geom = traci.vehicle.getPosition(vehicle)
        pos_geogr = traci.simulation.convertGeo(*pos_geom)
        return pos_geogr


    def _eta(self, building):
        if building not in self._eta_cache:            
            try:
                conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
                cur = conn.cursor()

                sql = 'select estimated_travel_time from estimated_travel_time(%s, %s, %s);'

                cur.execute(sql, (building, self._loc[0], self._loc[1]))
                travel_time = float(cur.fetchall()[0][0])
                
                conn.commit()
                cur.close()

                self._eta_cache[building] = self._time_controller.curr_sim_time() + travel_time + T_CONST_SEC
            except (Exception, psycopg2.DatabaseError) as error:
                print(error)
                travel_time = 0
                return self._time_controller.curr_sim_time() + T_CONST_SEC + T_ERR
            finally:
                if conn is not None:
                    conn.close()

        return self._eta_cache[building]


    def _invalidate_eta_cache(self):
        self._eta_cache = {}


    def _get_nearby_targets(self):
        try:
            conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
            cur = conn.cursor()

            sql = 'select building, distance from get_nearby_buildings(%s, %s, %s);'

            cur.execute(sql, (self._loc[0], self._loc[1], float(MAX_DIST_NEARBY_METERS)))
            frequent_targets = {res[0]: float(res[1]) for res in cur.fetchall()}
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            frequent_targets = {}
        finally:
            if conn is not None:
                conn.close()

        return frequent_targets


    def _get_calendar_targets(self, vehicle):
        user_id = self._get_user_id(vehicle)
        user_calendar_events = self._calendars[user_id].items()

        event_not_too_early = lambda event_time_of_week, place: self._time_controller.time_of_week_from_sim(self._eta(place)) - event_time_of_week < NEG_TIME_DELTA_SEC
        event_not_too_late = lambda event_time_of_week, place: event_time_of_week - self._time_controller.time_of_week_from_sim(self._eta(place)) < POS_TIME_DELTA_SEC
        event_within_timeframe = lambda event_time_of_week, place: event_not_too_early(event_time_of_week, place) and event_not_too_late(event_time_of_week, place)

        return [(place, time_of_week) for time_of_week, place in user_calendar_events if event_within_timeframe(time_of_week, place)]


    def _get_frequent_targets(self, vehicle):    
        try:
            conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
            cur = conn.cursor()

            sql = 'select building, absolute_time from user_history where user_id = %s;'
            user_id = self._get_user_id(vehicle)

            cur.execute(sql, (str(user_id),))
            frequent_targets = [(res[0], int(res[1])) for res in cur.fetchall()]
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            frequent_targets = {}
        finally:
            if conn is not None:
                conn.close()

        return frequent_targets


    def _get_repeating_targets(self, vehicle):
        try:
            conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
            cur = conn.cursor()

            sql = 'select building, time_of_week, absolute_time from get_events_within_timeframe(%s, %s, %s, %s, %s, %s, %s);'
            user_id = str(self._get_user_id(vehicle))

            cur.execute(sql, (user_id, int(self._time_controller.curr_time_of_week()), self._loc[0], self._loc[1], int(T_CONST_SEC), int(NEG_TIME_DELTA_SEC), int(POS_TIME_DELTA_SEC)))
            repeating_targets = [(res[0], int(res[1]), int(res[2])) for res in cur.fetchall()]
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            repeating_targets = {}
        finally:
            if conn is not None:
                conn.close()

        return repeating_targets


    def _confidence(self, target, target_sets):
        # print (f'\n==== target: {target} ====')
        conf = self._confidence_nearby(target, target_sets['nearby_targets']) \
            + self._confidence_calendar(target, target_sets['calendar_targets']) \
            + self._confidence_frequent(target, target_sets['frequent_targets']) \
            + self._confidence_repeating(target, target_sets['repeating_targets'])
        # print(f'\nOverall confidence: {conf}')
        return conf


    def _confidence_nearby(self, target, target_set):
        conf = BASE_CONF_NEARBY * target_set[target] if target in target_set else 0.0
        # print(f'conf_n: {conf}')
        return conf


    def _confidence_calendar(self, target, target_set):
        eta_time_of_week = self._time_controller.time_of_week_from_sim(self._eta(target))
        conf = sum([BASE_CONF_CALENDAR * gaussian(eta_time_of_week - time_of_week) for tar, time_of_week in target_set if tar == target])
        # print(f'conf_c: {conf}')
        return conf


    def _confidence_frequent(self, target, target_set):
        conf = BASE_CONF_FREQUENT * sigmoid(sum([sigmoid_star(self._time_controller.curr_global_time() - t[1]) for t in target_set if t == target]))
        # print(f'conf_f: {conf}')
        return conf


    def _confidence_repeating(self, target, target_set):
        eta = self._time_controller.time_of_week_from_sim(self._eta(target))
        conf = BASE_CONF_REPEATING * sigmoid(sum([sqrt(sigmoid_star(self._time_controller.curr_global_time() - t[2]) * gaussian(eta - t[1])) for t in target_set if t == target]))
        # print(f'conf_r: {conf}')
        return conf


    def pick_parking_areas(self, vehicle, target):
        self._save_user_target(vehicle, target)
        parking_areas_nearby = self._find_nearest_parking_areas(target)
        self._update_contextual_weights(vehicle, target)
        reccomended_parking_areas = sorted(parking_areas_nearby, key=lambda parking_area: self._cost(parking_area, vehicle, target))
        return reccomended_parking_areas[:N_PROPOSITIONS]


    def _load_parking_lots(self):
        parking_tree = ET.parse(parkings_file)
        self._parking_lots = parking_tree.xpath('/additional')[0]
        self._all_parking_areas_ids = [parking.attrib['id'] for parking in self._parking_lots.xpath('./parkingArea')]
        self._total_parking_capacity = sum([int(parking.attrib['roadsideCapacity']) for parking in self._parking_lots.xpath('./parkingArea')])

    
    def _load_users(self):
        users_tree = ET.parse(users_file)
        user_elements_list = users_tree.xpath('/users/user')

        user_id = lambda user_el: int(user_el.attrib['id'])
        event_element_list = lambda user_el: user_el.xpath('./calendar/event')

        time_of_week = lambda day, time_of_day: DAYS.index(day) * DAY_LEN_SECONDS + int(time_of_day)
        time_of_event = lambda event_el: time_of_week(event_el.attrib['day'], event_el.attrib['time'])
        place_of_event = lambda event_el: event_el.attrib['place']

        self._calendars = {
            user_id(user_el): {
                time_of_event(event_el): place_of_event(event_el) for event_el in event_element_list(user_el)
            } for user_el in user_elements_list
        }


    def _load_weight_config(self):
        return ET.parse(weights_file)

    
    def _find_nearest_parking_areas(self, target):
        n_parking_lots = 10

        try:
            conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
            cur = conn.cursor()

            sql = 'select id from get_parkings_around_building(%s, %s)'
            cur.execute(sql, (target, n_parking_lots))
            nearby_parkings = [p[0] for p in cur.fetchall()]
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            nearby_parkings = []
        finally:
            if conn is not None:
                conn.close()

        return nearby_parkings


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
        return self._weight_time * min(time_total / MAX_TIME_TOTAL, 1.) + \
               self._weight_walking * min(time_walking / MAX_TIME_WALKING, 1.) + \
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
            sigmoid(n_free_spots, COEF_FREE_SPACE)
        ]
        return sum(factors) / len(factors)


    def _get_free_spots_number(self, parking_area):
        n_parked_cars = traci.parkingarea.getVehicleCount(parking_area)
        capacity = self._get_parking_area_capacity(parking_area)
        return capacity - n_parked_cars


    def _get_parking_area_capacity(self, parking_area_name):
        parking_area_elem = self._parking_lots.xpath(f'./parkingArea[@id="{parking_area_name}"]')[0]
        return int(parking_area_elem.attrib['roadsideCapacity'])


    def _save_user_target(self, vehicle, target):
        try:
            conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
            cur = conn.cursor()

            sql = 'INSERT INTO user_history VALUES(%s, %s, %s, %s)'

            user_id = self._get_user_id(vehicle)
            time_of_week = self._time_controller.time_of_week_from_sim(self._eta(target))

            values = (user_id, target, time_of_week, self._time_controller.curr_global_time())

            cur.execute(sql, values)
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
        finally:
            if conn is not None:
                conn.close()


    def clear_user_history(self):
        try:
            conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
            cur = conn.cursor()

            sql = 'DELETE FROM user_history'
            cur.execute(sql)
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
        finally:
            if conn is not None:
                conn.close()
