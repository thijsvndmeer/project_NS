import requests as req
import json
import mysql.connector as SQLconnect
from datetime import datetime




def openconnection():
    print('Opening connection to database...')
    db = SQLconnect.connect(
    host='localhost',
    user='admin',
    password='NS-server2026',
    database='NSdatabase')
    print('Connection established!')
    return db




def get_stations(db, stations):
    cursor = db.cursor(buffered=True)
    result = {}
    print('Getting uicCodes for stations...')
    for station in stations:
        print(f'Getting uicCode for {station}')
        sql = 'SELECT uic, id FROM station WHERE naam = %s'
        val = [station]
        cursor.execute(sql, val)
        data = cursor.fetchone()

        if data == None:
            print(f'{station} not found')
            quit()
        else:
            result[station] = {'iucCode': data[0], 'id': data[1]}
            print(f'Stationdata {station} fetched!')
    cursor.close()
    return(result)




def get_departures(station, time, iucCode):
    final = []
    sub_key = '76c74d43ff344b63b889a3ad12126b2a'
    result = req.get(f'https://gateway.apiportal.ns.nl/reisinformatie-api/api/v2/departures?uicCode={iucCode}&maxJourneys=10]', headers={'Ocp-Apim-Subscription-Key': sub_key})
    result = result.json()['payload']['departures']

    for dep in result:
        name=f'{dep['product']['shortCategoryName']} naar {dep['direction']} van {dep['actualDateTime']}'
        dep_time = datetime.strptime(dep['actualDateTime'].split('+')[0], '%Y-%m-%dT%H:%M:%S').replace(second=0)


        dif = dep_time - time
        if dif.total_seconds() <= 300:
            name = f'{dep['product']['shortCategoryName']} naar {dep['direction']} van {dep_time}'
            print(f'The {name} is withing the window')
            dep['name'] = name
            final.append(dep)
        else: return(final)





def insert_stops(dep, db, id):
    cursor = db.cursor()

    for stop in dep:
        values = [id]

        dep_time = datetime.strptime(stop['actualDateTime'].split('+')[0], '%Y-%m-%dT%H:%M:%S').replace(second=0)

        values.append(dep_time)

        values.append( int((dep_time - datetime.strptime(stop['plannedDateTime'].split('+')[0], '%Y-%m-%dT%H:%M:%S').replace(second=0)).total_seconds() / 60))

        val = [stop['direction']]
        sql = 'SELECT id FROM station WHERE naam = %s'
        cursor.execute(sql, val)

        result = cursor.fetchone()

        if result == None:
            print(f'inserting {stop['name']} has failed, skipping' )
            continue

        values.append(result[0])

        print(f'adding the {stop['name']} to the database)')

        sql = 'SELECT * FROM stop WHERE station = %s AND vertrek = %s AND vertraging_vertrek = %s AND richting = %s'
        cursor.execute(sql, values)

        if cursor.fetchone() != None:
            print('stop already in the database')
            continue

        sql = 'INSERT INTO stop (station, vertrek, vertraging_vertrek, richting) VALUES (%s, %s, %s, %s)'

        db.commit()

        print('stop succesfully added to the database')

        cursor.execute(sql, values)

    cursor.close()
