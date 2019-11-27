#!/usr/bin/env python
# * coding: utf8 *
'''
main.py
A module that updates the sgid index with open data links
'''

import os
import pygsheets
import pyodbc
from dotenv import load_dotenv
from pydash.strings import kebab_case
from tqdm import tqdm

load_dotenv()

connection_string = (
    'DRIVER=ODBC Driver 17 for SQL Server;'
    f'SERVER={os.getenv("AGOL_SERVER")};'
    f'DATABASE={os.getenv("AGOL_DB")};'
    f'UID={os.getenv("AGOL_USER")};'
    f'PWD={os.getenv("AGOL_PW")}'
)
table_map = {}
sheet_id = os.getenv("AGOL_SHEET")
worksheet_id = 'SGID Stewardship Info'
skip_header_index = 1
endpoint_index = 21

connection = pyodbc.connect(connection_string)
cursor = connection.cursor()

print('connected to db')

cursor.execute('SELECT TABLENAME, AGOL_ITEM_ID, AGOL_PUBLISHED_NAME from META.AGOLITEMS')

for table_name, agol_id, proper_name in tqdm(cursor):
    if agol_id and agol_id.lower() == 'external':
        continue

    table_map[table_name.lower().replace('sgid.', '')] = f'https://opendata.gis.utah.gov/datasets/{kebab_case(proper_name.lower())}'

print('table map populated')

gc = pygsheets.authorize(service_file='client_secret.json')

worksheet = gc.open_by_key(sheet_id).worksheet_by_title(worksheet_id)
data_frame = worksheet.get_as_df()

for index, row in tqdm(data_frame.iterrows()):
    table_name = row['SGID Data Layer']

    if table_name and table_name.lower() in table_map:
        agol_id = table_map[table_name.lower()]

        row['Endpoint'] = agol_id

trimmed_frame = data_frame[['Endpoint']]

print('updating worksheet')

worksheet.set_dataframe(trimmed_frame, (skip_header_index, endpoint_index), nan='')

print('finished')
