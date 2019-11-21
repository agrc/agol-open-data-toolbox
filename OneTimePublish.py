from os.path import dirname, join, realpath
from os import mkdir
from shutil import rmtree
import json

import arcgis
import arcpy
import pydash
import sys

owner = sys.argv[1]
password = sys.argv[2]
share = sys.argv[3]

current_folder = dirname(realpath(__file__))

#: prod
sgid_write = join(share, 'internal.agrc.utah.gov as agrc-arcgis.sde')
sgid = join(share, 'internal.agrc.utah.gov as internal.sde')
pro_project_path = join(share, 'AGOL_Layers.aprx')

#: test
# sgid_write = join(share, 'SGID_Local as META.sde')
# sgid = join(share, 'SGID_Local as META.sde')
# pro_project_path = join(share, 'AGOL_Layers_TEST.aprx')

terms_of_use_file_path = join(share, 'termsOfUse.html')
with open(terms_of_use_file_path) as file:
  generic_terms_of_use = file.read()
agol_items_table = join(sgid_write, 'SGID.META.AGOLItems')
fgdb_folder =share
map_name = 'Publishing'
transformation = 'NAD_1983_to_WGS_1984_5'
drafts_folder = join(fgdb_folder, 'drafts')
metadata_file_path = join(current_folder, 'metadata.json')

gis = arcgis.gis.GIS(username=owner, password=password)
pro_project = arcpy.mp.ArcGISProject(pro_project_path)
maps = {}
for cat_map in pro_project.listMaps():
  maps[cat_map.name] = cat_map
temp_map = maps['Temp']
web_mercator = arcpy.SpatialReference(3857)
published_items = []
metadata_lookup = None
with open(metadata_file_path, 'r') as file:
  metadata_lookup = json.loads(file.read())


def cleanup():
  print('cleaning up Temp map')
  for layer in temp_map.listLayers():
    temp_map.removeLayer(layer)
  for table in temp_map.listTables():
    temp_map.removeTable(table)

  print('cleaning up drafts folder')
  rmtree(drafts_folder)
  mkdir(drafts_folder)

def import_data(sgid_table, fgdb_folder, fgdb, name, is_table):
  output_table = join(fgdb_folder, fgdb, name)

  if not arcpy.Exists(join(fgdb_folder, fgdb)):
    print(f'creating {fgdb}')
    arcpy.management.CreateFileGDB(fgdb_folder, fgdb)

  if not arcpy.Exists(output_table):
    print('importing/projecting data')
    if is_table:
      arcpy.management.Copy(sgid_table, output_table)
    else:
      arcpy.management.Project(sgid_table, output_table, web_mercator, transformation)

  return output_table

def add_data_to_map(category, name, output_table, add_map):
  existing_layers = add_map.listLayers()
  existing_tables = add_map.listTables()

  share_layer = None
  for layer in existing_layers + existing_tables:
    if layer.name == name:
      share_layer = layer

  if share_layer is None:
    print(f'adding data to map: {output_table}')
    new_layer = temp_map.addDataFromPath(output_table)

    if is_table:
      share_layer = add_map.addTable(new_layer)[0]
    else:
      share_layer = add_map.addLayer(new_layer, 'BOTTOM')[0]

    pro_project.save()

  return share_layer

def publish_to_agol(share_layer, category, item_name, add_map):
  global missing_thumbnails
  print(f'publishing {item_name} to AGOL')
  draft_path = join(drafts_folder, f'{share_layer.name}.sddraft')
  sd_path = draft_path[:-5]
  category_tag = pydash.title_case(category)

  print('staging')
  sharing_draft = add_map.getWebLayerSharingDraft('HOSTING_SERVER', 'FEATURE', share_layer.name, [share_layer])
  sharing_draft.exportToSDDraft(draft_path)
  arcpy.server.StageService(draft_path, sd_path)

  print('uploading')
  source_item = gis.content.add({}, data=sd_path)
  source_item.protect()

  print('publishing feature service')
  item = source_item.publish()
  item.protect()
  published_items.append((item_name, item.id))

  print('updating feature service item properties')
  tags = f'AGRC,SGID,{category_tag}'
  metadata = metadata_lookup[share_layer.name]

  #: add default license/access items if they are missing in metadata
  if len(metadata['licenseInfo']) == 0:
    metadata['licenseInfo'] = generic_terms_of_use
  if len(metadata['accessInformation']) == 0:
    metadata['accessInformation'] = 'AGRC'

  #: truncate snippet to 2048 chars (found issue in Parcels_Beaver_LIR)
  metadata['snippet'] = metadata['snippet'][:2047]

  metadata.update({
    'tags': tags,
    'title': item_name
  })
  success = item.update(metadata)
  if not success:
    raise Error('item update was not successful!')
  group = gis.groups.search(query=f'title: "Utah SGID {category_tag}" AND owner: "{owner}"')[0]
  item.share(everyone=True, groups=[group.id])

  print('creating thumbnail')
  try:
    item.create_thumbnail()
  except Exception as e:
    print(e)
    print('retrying thumbnail')
    try:
      item.create_thumbnail()
    except Exception as e:
      print(e)
      print('error creating thumbnail, skipping')
      missing_thumbnails.append(item.id)

  #: enable "Allow others to export to different formats" checkbox
  manager = arcgis.features.FeatureLayerCollection.fromitem(item).manager
  manager.update_definition({ 'capabilities': 'Query,Extract' })

  print(f'{item_name} published as: {source_item.id} (service def) & {item.id} (feature layer)')

  return item.id

cleanup()

#: get tables with missing ids from AGOLItems
sql = (None, 'ORDER BY TABLENAME')
query = 'AGOL_ITEM_ID IS NULL'

max_publishes = 10
total_publishes = 0
missing_thumbnails = []
with arcpy.da.SearchCursor(agol_items_table, ['TABLENAME', 'AGOL_PUBLISHED_NAME'], query, sql_clause=sql) as cursor:
  for table, item_name in cursor:
    if total_publishes >= max_publishes:
      break
    sgid_table = join(sgid, table)

    try:
      describe = arcpy.da.Describe(sgid_table)
    except:
      print(f'{sgid_table} does not exist!!!!!!!')
      continue
    is_table = describe['datasetType'] == 'Table'

    if is_table:
      continue

    print(table)
    _, category, name = table.split('.')
    fgdb = f'{category}.gdb'

    output_table = import_data(sgid_table, fgdb_folder, fgdb, name, is_table)

    try:
      add_map = maps[category]
    except KeyError:
      raise Error(f'ERROR: no map corresponding map found for {category}')

    share_layer = add_data_to_map(category, name, output_table, add_map)

    published_id = publish_to_agol(share_layer, category, item_name, add_map)

    share_layer.visible = False

    #: this is so that edits are saved with each successful publish
    with arcpy.da.Editor(sgid_write):
      update_query = f'TABLENAME = \'{table}\''
      with arcpy.da.UpdateCursor(agol_items_table, ['AGOL_ITEM_ID'], update_query) as update_cursor:
        for row in update_cursor:
          update_cursor.updateRow((published_id,))

    total_publishes = total_publishes + 1


print('published item ids:')
for title, id in published_items:
  print(f'{title},{id}')
print('items with missing thumbnails:')
for id in missing_thumbnails:
  print(id)
