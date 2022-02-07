from audioop import avg
from math import exp, sqrt
import math
from functools import reduce
import traci
from lxml import etree as ET
import os
import psycopg2


from constants import *


parkings_file = os.path.join(sumo_rel_path, gen_subdir, parkings_gen_filename)
weights_file = os.path.join(sumo_rel_path, config_subdir, weights_filename)
users_file = os.path.join(sumo_rel_path, config_subdir, users_conf_filename)


def gaussian(x, mean=0.0, sd=max(POS_TIME_DELTA_SEC, NEG_TIME_DELTA_SEC) / 3):
    var = float(sd)**2
    denom = (2*math.pi*var)**.5
    num = exp(-(float(x)-float(mean))**2/(2*var))
    return num/denom * 3000


def sigmoid(x):
    return 1 / (1 + exp(-x*4 + 4))


def sigmoid_star(x):
    return 2 / (1 + exp(x / (FREQ_N * WEEK_LEN_SECONDS)))


class ParkingAdvisor:
    def __init__(self, time_controller, environment):
        self._time_controller = time_controller
        self._environment = environment

        self._load_parking_lots()
        self._load_users()
        self._weight_config = self._load_weight_config()


    def suggest_targets(self, vehicle):
        self._invalidate_eta_cache()
        self.context = {}

        self._loc = self._get_user_localization(vehicle)
	
        target_sets = {
            'nearby_targets': self._get_nearby_targets(),
            'calendar_targets': self._get_calendar_targets(vehicle),
            'frequent_targets': self._get_frequent_targets(vehicle),
            'repeating_targets': self._get_repeating_targets(vehicle)
        }
        self._last_target_sets = target_sets

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
                conn = psycopg2.connect(conn_string)
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
            conn = psycopg2.connect(conn_string)
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
            conn = psycopg2.connect(conn_string)
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
            conn = psycopg2.connect(conn_string)
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


    def confidence_components(self, target):
        return {
            'nearby': self._confidence_nearby(target, self._last_target_sets['nearby_targets']),
            'calendar': self._confidence_calendar(target, self._last_target_sets['calendar_targets']),
            'frequent': self._confidence_frequent(target, self._last_target_sets['frequent_targets']),
            'repeating': self._confidence_repeating(target, self._last_target_sets['repeating_targets'])
        }


    def _confidence_nearby(self, target, target_set):
        return BASE_CONF_NEARBY * (1. - target_set[target] / MAX_DIST_NEARBY_METERS) if target in target_set else 0.0


    def _confidence_calendar_single(self, eta_time_of_week, time_of_week):
        return BASE_CONF_CALENDAR * gaussian(eta_time_of_week - time_of_week)


    def _confidence_calendar(self, target, target_set):
        eta_time_of_week = self._time_controller.time_of_week_from_sim(self._eta(target))
        return sum([self._confidence_calendar_single(eta_time_of_week, time_of_week) for tar, time_of_week in target_set if tar == target])


    def _confidence_frequent(self, target, target_set):
        return BASE_CONF_FREQUENT * sigmoid(sum([sigmoid_star(self._time_controller.curr_global_time() - absolute_time) for tar, absolute_time in target_set if tar == target]))


    def _confidence_repeating(self, target, target_set):
        eta = self._time_controller.time_of_week_from_sim(self._eta(target))
        return BASE_CONF_REPEATING * sigmoid(sum([sqrt(sigmoid_star(self._time_controller.curr_global_time() - absolute_time) * gaussian(eta - time_of_week)) for tar, time_of_week, absolute_time in target_set if tar == target]))


    def pick_parking_areas(self, vehicle, target):
        self.costs = {}

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
            conn = psycopg2.connect(conn_string)
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
            self._weights_by_weather(),
            self._weights_by_global_free_slots_ratio(),
            self._weights_by_time_to_event(target),
            self._weights_by_air_quality()
        ]

        applicable_weights = filter(lambda weights: weights is not None, weights_by_individual_factors)

        summed_weights = reduce(lambda acc, weights: [sum(w) for w in zip(acc, weights)], applicable_weights, [0, 0, 0])
        mean_weights = [w / len(weights_by_individual_factors[0]) for w in summed_weights]
        
        self.weight_time = mean_weights[0]
        self.weight_walking = mean_weights[1]
        self.weight_prob = mean_weights[2]


    def _weights_by_weather(self):
        return self._weights_by_factor('weather', self._environment.weather)


    def _weights_by_global_free_slots_ratio(self):
        total_occupied_spaces = sum([int(traci.parkingarea.getVehicleCount(parking)) for parking in self._all_parking_areas_ids])
        global_free_slots_ratio = (self._total_parking_capacity - total_occupied_spaces) / self._total_parking_capacity
        return self._weights_by_factor('globalFreeSlotsAvailability', global_free_slots_ratio)


    def _weights_by_time_to_event(self, target):
        event_confidence = 0.
        time_to_event = None

        for tar, time_of_week in self._last_target_sets['calendar_targets']:
            if tar == target:
                eta_time_of_week = self._time_controller.time_of_week_from_sim(self._eta(target))
                conf = self._confidence_calendar_single(eta_time_of_week, time_of_week)
                if conf > event_confidence and conf > BASE_CONF_CALENDAR / 2:
                    event_confidence = conf
                    time_to_event = eta_time_of_week - time_of_week

        if target in (t[0] for t in self._last_target_sets['repeating_targets']):
            conf = self._confidence_repeating(target, self._last_target_sets['repeating_targets'])
            if conf > event_confidence and conf > BASE_CONF_REPEATING / 2:
                mean_time_of_week = avg([time_of_week for tar, time_of_week, _ in self._last_target_sets['repeating_targets'] if tar == target])
                
                event_confidence = conf
                time_to_event = self._time_controller.curr_time_of_week() - mean_time_of_week

        return self._weights_by_factor('timeToEvent', time_to_event) if time_to_event is not None else None


    def _weights_by_air_quality(self):
        return self._weights_by_factor('airQuality', self._environment.air_quality)


    def _weights_by_factor(self, factor, value):
        self.context[factor] = value

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
        total = self.weight_time * min(time_total / MAX_TIME_TOTAL, 1.) + \
               self.weight_walking * min(time_walking / MAX_TIME_WALKING, 1.) + \
               self.weight_prob * (1 - prob_of_success)

        self.costs[parking_area] = (time_total, time_walking, prob_of_success, total)
        return total

    
    def _get_time_total(self, parking_area, target, vehicle):
        try:
            conn = psycopg2.connect(conn_string)
            cur = conn.cursor()

            sql = 'select estimated_total_time(%s, %s, %s, %s)'
            cur.execute(sql, (parking_area, target, *self._loc))
            time_total = cur.fetchall()[0][0]
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            time_total = MAX_TIME_TOTAL
        finally:
            if conn is not None:
                conn.close()

        return time_total

    
    def _get_time_walking(self, parking_area, target):
        try:
            conn = psycopg2.connect(conn_string)
            cur = conn.cursor()

            sql = 'select estimated_walking_time(%s, %s)'
            cur.execute(sql, (parking_area, target))
            time_walking = cur.fetchall()[0][0]
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            time_walking = MAX_TIME_WALKING
        finally:
            if conn is not None:
                conn.close()

        return time_walking


    def _get_time_driving(self, parking_area):
        try:
            conn = psycopg2.connect(conn_string)
            cur = conn.cursor()

            sql = 'select estimated_driving_time(%s, %s, %s)'
            cur.execute(sql, (parking_area, *self._loc))
            time_driving = cur.fetchall()[0][0]
            
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            time_driving = MAX_TIME_DRIVING
        finally:
            if conn is not None:
                conn.close()

        return time_driving


    def _get_prob_of_success(self, parking_area, vehicle):
        n_free_spots = self._get_free_spots_number(parking_area)
        # length_diff = ...
        # width_diff = ...
        # n_free_spots_nearby = ...
        time_driving = self._get_time_driving(parking_area)

        sigmoid_free_spots = lambda x, c: 1 - (c * (1 / (1 + exp(-x / 5)) - 0.5))
        sigmoid_time_driving = lambda x: 2 / (1 + exp(x / MAX_TIME_DRIVING / 4))

        factors = [
            sigmoid_free_spots(n_free_spots, COEF_FREE_SPACE),
            sigmoid_time_driving(time_driving)
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
            conn = psycopg2.connect(conn_string)
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
            conn = psycopg2.connect(conn_string)
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
