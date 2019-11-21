#!/usr/bin/env python
# * coding: utf8 *
'''
UpdateTitles.py

Updates AGOL Item titles to match the AGOL_PUBLISHED_NAME field in SGID.META.AGOLItems

Arguments:
1 - AGOL Username
2 - AGOL Password
3 - Path to internal.agrc.utah.gov.sde file
'''

import arcpy
import arcgis
from os.path import join
import sys


agol_items_table_name = 'SGID.META.AGOLItems'

gis = arcgis.gis.GIS(username=sys.argv[1], password=sys.argv[2])

agol_items_table = join(sys.argv[3], agol_items_table_name)

errors = []
query = 'AGOL_ITEM_ID IS NOT NULL AND AGOL_ITEM_ID <> \'EXTERNAL\' AND AGOL_PUBLISHED_NAME IS NOT NULL'
with arcpy.da.SearchCursor(agol_items_table, ['AGOL_ITEM_ID', 'AGOL_PUBLISHED_NAME'], query) as cursor:
  for item_id, name in cursor:
    try:
      item = arcgis.gis.Item(gis, item_id)

      if item.title != name:
        print(f'{item.title} -> {name}')
        item.update({'title': name})

    except Exception as e:
      message = f'Error with {name} ({item_id}): {e}'
      errors.append(message)
      print(message)

if len(errors) > 0:
  print('Errors:')
  for e in errors:
    print(e)
