#!/usr/bin/env python
# * coding: utf8 *
'''
Folders.py

Validate or move AGOL items to the correct ISO category folder

Arguments:
1 - AGOL Username
2 - AGOL Password
3 - Path to internal.agrc.utah.gov.sde file
'''

import arcpy
import arcgis
from os.path import join
import sys
from tqdm import tqdm
import pydash


agol_items_table_name = 'SGID.META.AGOLItems'

username = sys.argv[1]
gis = arcgis.gis.GIS(username=username, password=sys.argv[2])

agol_items_table = join(sys.argv[3], agol_items_table_name)


def get_folder_from_fc(name):
  return pydash.title_case(name.split('.')[1])


def get_folders_to_items():
  print('getting folders and items for user...')
  user = arcgis.gis.User(gis, username)

  folders = {}
  for folder in user.folders:
    results = user.items(folder, max_items=1000)
    folders.setdefault(folder['title'], [item.id for item in results])

  return folders


def create_folders():
  folders = set()
  query = 'AGOL_ITEM_ID <> \'EXTERNAL\''
  with arcpy.da.SearchCursor(agol_items_table, ['TABLENAME'], query) as cursor:
    for tablename, in tqdm(cursor):
      folders.add(get_folder_from_fc(tablename))

  for folder in tqdm(folders):
    print(f'creating {folder}')
    gis.content.create_folder(folder)


def move_item_if_needed(item, folder, folders):
  if not item.id in folders[folder]:
    error_message = f'error moving {item.title} ({item.id})!'
    try:
      result = item.move(folder)

      if result['success'] == False:
        print(error_message)
    except Exception as e:
      print(f'{error_message}\n{e}')


def update_folders_for_meta_table_items():
  print('updating folders for meta table items...')
  folders = get_folders_to_items()

  query = 'AGOL_ITEM_ID <> \'EXTERNAL\''
  with arcpy.da.SearchCursor(agol_items_table, ['TABLENAME', 'AGOL_ITEM_ID', 'AGOL_PUBLISHED_NAME'], query) as cursor:
    for tablename, agol_id, agol_name in tqdm(cursor):
      item = arcgis.gis.Item(gis, agol_id)

      folder = get_folder_from_fc(tablename)

      move_item_if_needed(item, folder, folders)

      for related_item in item.related_items('Service2Data'):
        move_item_if_needed(related_item, folder, folders)


# create_folders()
# update_folders_for_meta_table_items()
