import NS as ns
from datetime import datetime


db = ns.openconnection()

stations = []
cursor = db.cursor()
cursor.execute('SELECT naam FROM station')
for row in cursor:
    stations.append(row[0])

stations = ns.get_stations(db, stations)

collection_time = int(input('How long do you wish to collect? (in minutes)'))

def main_loop(stations, db):

    for station in stations:
        now = datetime.now()

        print(f'searching for departures from {station}')
        departures = ns.get_departures(station, now, stations[station]['iucCode'])

        if departures != None:
            ns.insert_stops(departures, db, stations[station]['id'])
        else: print(f'no departures for {station}')


n = 1

while n < collection_time:
    print(" ")
    print(" ")
    print("waiting until next measuring moment...")
    time = datetime.now().replace(second=0, microsecond=0)
    t = True
    while t:
        if (datetime.now().replace(second=0, microsecond=0) - time).total_seconds() > 240:
            t = False
    print(datetime.now().replace(second=0, microsecond=0))

    main_loop(stations, db)

    n += 1

print(' ')
print(' ')
print(' ')
print('Measuring complete')
print('closing program')
