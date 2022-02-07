# ====================================================================
# Configurable parameters:

POS_TIME_DELTA_SEC = 3600
NEG_TIME_DELTA_SEC = 900

MAX_DIST_NEARBY_METERS = 500
T_CONST_SEC = 300

T_ERR = 600

BASE_CONF_NEARBY = 0.2
BASE_CONF_CALENDAR = 0.4
BASE_CONF_FREQUENT = 0.1
BASE_CONF_REPEATING = 0.3

N_PROPOSITIONS = 5

MAX_TIME_TOTAL = 1200
MAX_TIME_WALKING = 600

COEF_FREE_SPACE = 2
FREQ_N = 5

MIN_STOP_TIME_SEC = 200
MAX_STOP_TIME_SEC = 2000


# ====================================================================
# Technical constants:

MINUTE_LEN_SECONDS = 60
HOUR_LEN_SECONDS = 60 * MINUTE_LEN_SECONDS
DAY_LEN_SECONDS = 24 * HOUR_LEN_SECONDS
WEEK_LEN_SECONDS = 7 * DAY_LEN_SECONDS

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


# ====================================================================
# File and directory names:

sumo_rel_path = 'sumo'
config_subdir = 'config'
gen_subdir = 'generated'

sumocfg_filename = 'agh.sumocfg'

users_conf_filename = 'users.xml'
weights_filename = 'weights.xml'

parkings_gen_filename = 'parkings.add.xml'
net_gen_filename = 'osm.net.xml'
users_trips_filename = 'users.trips.xml'
all_trips_gen_filename = 'agh.random.trips.xml'
buildings_filename = 'buildings.xml'
map_filename = 'agh_bbox.osm.xml'
