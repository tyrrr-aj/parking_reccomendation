import sys, os
from lxml import etree as ET
import xml.dom.minidom
import random
import psycopg2

from parking_generator import save_output
from constants import *


n_weeks = 1
n_users = 100


output_trips_file = os.path.join(sumo_rel_path, gen_subdir, users_trips_filename)
output_users_file = os.path.join(sumo_rel_path, config_subdir, users_conf_filename)

net_file = os.path.join(sumo_rel_path, gen_subdir, net_gen_filename)
parkings_file = os.path.join(sumo_rel_path, gen_subdir, parkings_gen_filename)
trips_file = os.path.join(sumo_rel_path, gen_subdir, all_trips_gen_filename)
buildings_file = os.path.join(sumo_rel_path, config_subdir, buildings_filename)

encoding = 'UTF-8'

min_time_between_trips = 3600   # in seconds
max_time_between_trips = 24 * 3600  # in seconds

max_n_calendar_entries = 30
min_time_between_events = 3600
min_event_hour = 6
max_event_hour = 22

n_user_trips = 20
calendar_acc_ratio = 0.7
time_delta = 900

min_stop_time = 500
max_stop_time = 2000


def get_parkings():
    parking_tree = ET.parse(parkings_file)
    return [p.attrib['id'] for p in parking_tree.xpath('/additional/parkingArea')]

def get_roads():
    osm = ET.parse(net_file)
    return [e.attrib['id'].split(':')[-1] for e in osm.xpath('/net/edge') if not str.startswith(e.attrib['id'], ':cluster') and 'function' not in e.attrib]

def get_buildings():
    osm = ET.parse(buildings_file)
    return [e.text for e in osm.xpath('building/name')]

days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
buildings = get_buildings()
parkings = get_parkings()
roads = get_roads()

sources = ['277117089', '277117080', '-21094558#7', '558612810#0', '-277424358', '370453642']
sinks = ['431516755#1', '114324803#3', '21094558#4', '277424367#1', '277424358', '-370453642']


def xml_root(root_element_name):
    root = ET.Element(root_element_name)
    return root


def save_output(output_tree, output):
    dom = xml.dom.minidom.parseString(ET.tostring(output_tree))
    xml_string = dom.toprettyxml()
    part1, part2 = xml_string.split('?>')

    with open(output, 'w', encoding=encoding) as out:
        out.write(part1 + 'encoding=\"{}\"?>\n'.format(encoding) + part2)


def fill_random_calendar(calendar):
    n_entries = random.randint(0, max_n_calendar_entries)
    i = 0
    time = 3600 * (min_event_hour - 1)
    time += random.randint(min_time_between_events, 3600 * (max_event_hour - min_event_hour))
    day_ix = 0

    while i < n_entries:
        if time > 3600 * max_event_hour:
            if day_ix < 6:
                day_ix += 1
                time = 3600 * (min_event_hour - 1)
                time += random.randint(min_time_between_events, 3600 * (max_event_hour - min_event_hour))
            else:
                break

        event = ET.SubElement(calendar, 'event')
        event.set('day', days[day_ix])
        event.set('time', str(time))
        event.set('place', random.choice(buildings))

        time += random.randint(min_time_between_events, 3600 * (max_event_hour - min_event_hour))


def find_parking_area(target):
    try:
        conn = psycopg2.connect(conn_string)
        cur = conn.cursor()

        sql = 'select id from get_parkings_around_building(%s, %s)'

        cur.execute(sql, (target, 5))
        nearby_parkings = [p[0] for p in cur.fetchall()]
        
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        nearby_parkings = random.choices(parkings, k=5)
    finally:
        if conn is not None:
            conn.close()

    return random.choice(nearby_parkings)


def event_absolute_time(event, week):
    random_delta = int((random.random() - 0.5) * time_delta)
    return week * WEEK_LEN_SECONDS + days.index(event.attrib['day']) * DAY_LEN_SECONDS + int(event.attrib['time']) + random_delta


def random_time():
    week = random.randint(0, n_weeks - 1)
    day = random.randint(0, len(days) - 1)
    time = random.randint(0, DAY_LEN_SECONDS)
    return week * WEEK_LEN_SECONDS + day * DAY_LEN_SECONDS + time


def occupied(absolute_time, trips):
    return any('time' in trips.attrib and abs(float(trip.attrib['time']) - absolute_time) < min_time_between_trips for trip in trips)


def random_trip_time(trips):
    absolute_time = random_time()
    while occupied(absolute_time, trips):
        absolute_time = random_time()
    return absolute_time


def fill_random_trips(user_id, trips, calendar):
    events = calendar.xpath('./event')
    trip_id = 0
    
    for week in range(n_weeks):
        for event in events:
            if random.random() < calendar_acc_ratio:
                trip = ET.SubElement(trips, 'trip')
                trip.set('id', f'usr{user_id}_{trip_id}')
                trip.set('time', str(event_absolute_time(event, week)))
                trip.set('target', event.attrib['place'])
                trip_id += 1

        while trip_id < n_user_trips * (week + 1):
            trip = ET.SubElement(trips, 'trip')
            trip.set('id', f'usr{user_id}_{trip_id}')
            
            time = random_trip_time(trips)
            trip.set('time', str(time))

            trip.set('target', random.choice(buildings))
            trip_id += 1

    trips[:] = sorted(trips, key=lambda trip: float(trip.attrib['time']))


def fill_random_user(id, user):
    user.set('id', str(id))
    calendar = ET.SubElement(user, 'calendar')
    trips = ET.SubElement(user, 'trips')

    fill_random_calendar(calendar)
    fill_random_trips(id, trips, calendar)


def generate_users(users_tree):
    for i in range(n_users):
        user = ET.SubElement(users_tree, 'user')
        fill_random_user(i, user)


def add_guided_v_type(trips_tree):
    v_type = ET.SubElement(trips_tree, 'vType')
    v_type.set('id', 'veh_guided')
    v_type.set('vClass', 'passenger')
    v_type.set('color', '0,0,255')


def prepare_users_trips(users_tree, users_trips_tree):
    trips = users_tree.xpath('/users/user/trips/trip')
    for trip in trips:
        trip_el = ET.SubElement(users_trips_tree, 'trip')
        trip_el.set('id', trip.attrib['id'])
        trip_el.set('type', 'veh_guided')
        trip_el.set('depart', trip.attrib['time'])
        trip_el.set('departLane', 'best')
        trip_el.set('from', random.choice(sources))
        trip_el.set('to', random.choice(sinks))

        stop = ET.SubElement(trip_el, 'stop')
        stop.set('parkingArea', find_parking_area(trip.attrib['target']))
        stop.set('duration', str(random.randint(min_stop_time, max_stop_time)))

    users_trips_tree[:] = sorted(users_trips_tree, key=lambda trip: float(trip.attrib['depart']) if trip.tag == 'trip' else 0.0)


def main():
    users_tree = xml_root('users')
    users_trips_tree = ET.parse(trips_file).find('.')
    
    generate_users(users_tree)
    save_output(users_tree, output_users_file)

    add_guided_v_type(users_trips_tree)
    prepare_users_trips(users_tree, users_trips_tree)
    save_output(users_trips_tree, trips_file)


if __name__ == '__main__':
    sys.exit(main())
