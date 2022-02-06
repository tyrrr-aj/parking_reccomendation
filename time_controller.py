from dateutil import parser
import os

from constants import *


time_file = os.path.join('.tmp', 'time')


class TimeController:
    def __init__(self, continue_, week, day, time):
        if continue_:
            self.start_time = self._restore_last_known_time()
        else:
            self.start_time = self._get_time(week, day, time)
        self.start_time_of_week = self.start_time % WEEK_LEN_SECONDS


    def global_time(self, sim_time):
        return self.start_time + sim_time


    def sim_time(self, global_time):
        return global_time - self.start_time


    def update_curr_time(self, curr_sim_time):
        self._curr_sim_time = curr_sim_time

    
    def curr_sim_time(self):
        return self._curr_sim_time


    def curr_global_time(self):
        return self._curr_sim_time + self.start_time


    def curr_time_of_week(self):
        return (self.start_time + self._curr_sim_time) % WEEK_LEN_SECONDS


    def time_of_week_from_sim(self, absolute_sim_time):
        return (self.start_time + absolute_sim_time) % WEEK_LEN_SECONDS


    def save_time(self):
        with open(time_file, 'w') as tf:
            tf.write(str(self.start_time))


    def clear_stored_time(self):
        open(time_file, 'w').close()


    def _restore_last_known_time(self):
        with open(time_file, 'r') as tf:
            content = tf.read()
            if content:
                return int(content)
            else:
                print("Illegal use of --continue flag - no simulation timestamp has been saved")
                exit(-1)


    def _get_time(self, week, day, time):
        time_parsed = parser.parse(time)
        return (week - 1) * WEEK_LEN_SECONDS \
            + (day - 1) * DAY_LEN_SECONDS \
            + time_parsed.hour * HOUR_LEN_SECONDS \
            + time_parsed.minute * MINUTE_LEN_SECONDS \
            + time_parsed.second
