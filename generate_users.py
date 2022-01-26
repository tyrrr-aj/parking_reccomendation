import sys, os
from lxml import etree as ET
import xml.dom.minidom
import random

from parking_generator import save_output


n_weeks = 1
n_users = 100

sumo_rel_path = 'sumo'

output_trips_file = 'users.trips.xml'
output_users_file = 'users.xml'

net_file = 'osm.net.xml'

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

WEEK_LEN_SECONDS = 7 * 24 * 3600
DAY_LEN_SECONDS = 24 * 3600


def get_parkings():
    parking_tree = ET.parse('parkings.add.xml')
    return [p.attrib['id'] for p in parking_tree.xpath('/additional/parkingArea')]

def get_roads():
    osm = ET.parse(os.path.join(sumo_rel_path, net_file))
    return [e.attrib['id'].split(':')[-1] for e in osm.xpath('/net/edge') if not str.startswith(e.attrib['id'], ':cluster') and 'function' not in e.attrib]

days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
buildings = ['A0', 'A1', 'A2', 'A3', 'A4', 'H-A1', 'H-A2', 'B1', 'B2', 'B3', 'B4', 'H-B1B2', 'H-B3B4', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'D1', 'D2', 'D4', 'S1', 'S2', 'U1', 'U2', 'U3', 'Z2']
parkings = get_parkings()
roads = get_roads()


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


def find_parking_area(target=None):
    return random.choice(parkings)


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
        trip_el.set('from', random.choice(roads))
        trip_el.set('to', random.choice(roads))

        stop = ET.SubElement(trip_el, 'stop')
        stop.set('parkingArea', find_parking_area(trip.attrib['target']))
        stop.set('duration', str(random.randint(min_stop_time, max_stop_time)))

    users_trips_tree[:] = sorted(users_trips_tree, key=lambda trip: float(trip.attrib['depart']) if trip.tag == 'trip' else 0.0)


def main():
    users_tree = xml_root('users')
    users_trips_tree = ET.parse('agh.random.trips.xml').find('.')
    
    generate_users(users_tree)
    save_output(users_tree, os.path.join(sumo_rel_path, output_users_file))

    add_guided_v_type(users_trips_tree)
    prepare_users_trips(users_tree, users_trips_tree)
    save_output(users_trips_tree, 'agh.random.trips.xml')


if __name__ == '__main__':
    sys.exit(main())
