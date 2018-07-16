
from __future__ import print_function
from flask import Flask, render_template, session, request, redirect, send_file
app = Flask(__name__)

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
from bs4 import BeautifulSoup as bs
import re
import json
import os

import datetime
import sys
import re
from icalendar import Calendar, Event

import dates
WORKING_DAYS = dates.get_dates()

import build_event


DEBUG = False
GENERATE_ICS = True
TIMETABLE_DICT_RE ='([0-9]{1,2}):([0-9]{1,2}):([AP])M-([0-9]{1,2}):([0-9]{1,2}):([AP])M'
timetable_dict_parser = re.compile(TIMETABLE_DICT_RE)

with open('subjects.json') as data_file:
    subjects = json.load(data_file)

'''
Given a starting timestamp d and a weekday number d (0-6), return the timestamp
of the next time this weekday is going to happen
'''
def next_weekday(d, weekday):
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0: # Target day already happened this week
        days_ahead += 7
    return d + datetime.timedelta(days_ahead)

def get_stamp(argument, date):
    '''
    argument is a 3-tuple such as
    ('10', '14', 'A') : 1014 HRS on date
    ('10', '4', 'P') : 2204 HRS on date
    '''

    hours_24_format = int(argument[0])

    # Note:
    # 12 PM is 1200 HRS
    # 12 AM is 0000 HRS

    if argument[2] == 'P' and hours_24_format != 12:
        hours_24_format = (hours_24_format + 12) % 24

    if argument[2] == 'A' and hours_24_format == 12:
        hours_24_format = 0

    return build_event.generateIndiaTime(date.year,
            date.month,
            date.day,
            hours_24_format,
            int(argument[1]))



ERP_HOMEPAGE_URL = 'https://erp.iitkgp.ac.in/IIT_ERP3/'
ERP_LOGIN_URL = 'https://erp.iitkgp.ac.in/SSOAdministration/auth.htm'
ERP_SECRET_QUESTION_URL = 'https://erp.iitkgp.ac.in/SSOAdministration/getSecurityQues.htm'

headers = {
    'timeout': '20',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/51.0.2704.79 Chrome/51.0.2704.79 Safari/537.36',
}
session_dict = {}

@app.route('/')
def homepage():
    return render_template("main.html")

@app.route('/login', methods=['POST'])
def user():
    try:
        user_id = request.form['user_id']
        token = request.form['sessionToken']
        login_details = {
            'user_id': user_id,
            'password': request.form['password'],
            'answer': request.form['security_answer'],
            'sessionToken': token,
            'requestedUrl': 'https://erp.iitkgp.ac.in/IIT_ERP3',
        }
        s = session_dict[token]
        sucess = False
        try:
            r = s.post(ERP_LOGIN_URL, data=login_details,
                   headers = headers)
            if r.status_code == 200:
                success = True
        except Exception as e:
            print(e)
            time.sleep(5)
            print("Error for LOGIN URL")
            print("Retrying.")

        
        ssoToken = re.search(r'\?ssoToken=(.+)$',
                         r.history[1].headers['Location']).group(1)

        ERP_TIMETABLE_URL = "https://erp.iitkgp.ac.in/Acad/student/view_stud_time_table.jsp"

        timetable_details = {
            'ssoToken': ssoToken,
            'module_id': '16',
            'menu_id': '40',
        }

        
        sucess = False
        try:
            r = s.post('https://erp.iitkgp.ac.in/Acad/student/view_stud_time_table.jsp', headers=headers, data=timetable_details)
            if r.status_code == 200:
                success = True
        except Exception as e:
            print(e)
            time.sleep(5)
            print("Error for timetable")
            print("Retrying.")

        
        cookie_val = None
        for a in s.cookies:
            if (a.path == "/Acad/"):
                cookie_val = a.value

        cookie = {
            'JSESSIONID': cookie_val,
        }

        sucess = False
        try:
            r = s.post('https://erp.iitkgp.ac.in/Acad/student/view_stud_time_table.jsp',cookies = cookie, headers=headers, data=timetable_details)
            if r.status_code == 200:
                success = True
        except Exception as e:
            print(e)
            time.sleep(5)
            print("Error for timetable")
            print("Retrying.")
        
        # print (r)
        soup = bs(r.text, 'html.parser')
        rows_head = soup.findAll('table')[2]
        rows = rows_head.findAll('tr')
        times = []

        for a in rows[0].findAll('td'):
            if ('AM' in a.text or 'PM' in a.text):
                times.append(a.text)

        #### For timings end
        days = {}
        #### For day
        days[1] = "Monday"
        days[2] = "Tuesday"
        days[3] = "Wednesday"
        days[4] = "Thursday"
        days[5] = "Friday"
        days[6] = "Saturday"
        #### For day end

        timetable_dict = {}

        for i in range(1, len(rows)):
            timetable_dict[days[i]] = {}
            tds = rows[i].findAll('td')
            time = 0
            for a in range(1, len(tds)):
                txt = tds[a].find('b').text.strip()
                if (len(txt) >= 7):
                    timetable_dict[days[i]][times[time]] = list((tds[a].find('b').text[:7],tds[a].find('b').text[7:], int(tds[a]._attr_value_as_string('colspan'))))
                time = time + int(tds[a]._attr_value_as_string('colspan'))


        def merge_slots(in_dict):
            for a in in_dict:
                in_dict[a] = sorted(in_dict[a])
                for i in range(len(in_dict[a]) - 1, 0, -1):
                    if (in_dict[a][i][0] == in_dict[a][i-1][0] + in_dict[a][i-1][1]):
                        in_dict[a][i-1][1] = in_dict[a][i][1] + in_dict[a][i-1][1]
                        in_dict[a].remove(in_dict[a][i])
                in_dict[a] = in_dict[a][0]
            return (in_dict)


        for day in timetable_dict.keys():
            subject_timings = {}
            for time in timetable_dict[day]:
                flattened_time = int(time[:time.find(':')])
                if (flattened_time < 6):
                    flattened_time += 12
                if (not timetable_dict[day][time][0] in subject_timings.keys()):
                    subject_timings[timetable_dict[day][time][0]] = []
                subject_timings[timetable_dict[day][time][0]].append([flattened_time, timetable_dict[day][time][2]])
            subject_timings = merge_slots(subject_timings)
            for time in list(timetable_dict[day].keys()):
                flattened_time = int(time[:time.find(':')])
                if (flattened_time < 6):
                    flattened_time += 12
                if (not flattened_time == subject_timings[timetable_dict[day][time][0]][0]):
                    del (timetable_dict[day][time])
                else:
                    timetable_dict[day][time][2] = subject_timings[timetable_dict[day][time][0]][1]

        # print(timetable_dict)

        del session_dict[token]

        cal = Calendar()
        cal.add('prodid', '-//Your Timetable generated by GYFT//mxm.dk//')
        cal.add('version', '1.0')
        data = timetable_dict

        days = {}
        days["Monday"] = 0
        days["Tuesday"] = 1
        days["Wednesday"] = 2
        days["Thursday"] = 3
        days["Friday"] = 4
        days["Saturday"] = 5
        ###
        # Get subjects code and         their respective name
        for day in data:
            startDates = [next_weekday(x[0], days[day]) for x in WORKING_DAYS]

            for time in data[day]:
                # parsing time from time_table dict
                # currently we only parse the starting time
                # duration of the event is rounded off to the closest hour
                # i.e 17:00 - 17:55 will be shown as 17:00 - 18:00

                parse_results = timetable_dict_parser.findall(time)[0]

                lectureBeginsStamps = [get_stamp(parse_results[:3], start) \
                                                            for start in startDates]

                durationInHours = data[day][time][2]
                
                # Find the name of this course
                # Use subject name if available, else ask the user for the subject
                # name and use that
                # TODO: Add labs to `subjects.json`
                subject_code = data[day][time][0]
                summary = subject_code
                description = subject_code
                if (subject_code in subjects.keys()):
                    summary = subjects[subject_code].title()
                else:
                    print('Our subjects database does not have %s in it.' %
                            subject_code);
                    # summary = input('INPUT: Please input the name of the course %s: ' %
                    #         subject_code)

                    subjects[subject_code] = str(subject_code)

                    summary = summary.title()

                # Find location of this class
                location = data[day][time][1]

                for lectureBegin, [periodBegin, periodEnd] in \
                        zip(lectureBeginsStamps, WORKING_DAYS):

                    event = build_event.build_event_duration(summary,
                            description,
                            lectureBegin,
                            durationInHours,
                            location,
                            "weekly",
                            periodEnd)

                    cal.add_component(event)

                if (DEBUG):
                    print (event)
        # print ("returned", str(cal.to_ical()))
        return str([cal.to_ical().decode('utf-8')])
    except Exception as e:
        del session_dict[token]
        print ("Error", e)
        return ("error occured")
#     # return str(top_N_sim_users(users_id['Kumar Srinivas'][0], 5))

@app.route('/getques', methods=['GET', 'POST'])
def getques():
    try:
        s = requests.Session()
        r = s.get(ERP_HOMEPAGE_URL)
        soup = bs(r.text, 'html.parser')
        sessionToken = soup.find_all(id='sessionToken')[0].attrs['value']
        user_id = request.form['user_id']
        r = s.post(ERP_SECRET_QUESTION_URL, data={'user_id': user_id},
               headers = headers)
        secret_question = r.text
        session_dict[sessionToken] = s
        data = []
        data.append(secret_question);
        data.append(sessionToken);
        if (secret_question == "FALSE"):
            data = "error occured"
        return str(data)
    except Exception as e:
        return "error occured"

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

