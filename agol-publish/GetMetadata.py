'''
to be run with py2 because arcpy_metadata does not support py3
'''
import arcpy
import arcpy_metadata
import json
from os.path import join, dirname, realpath


current_directory = dirname(realpath(__file__))
sgid = sys.argv[1]
json_file_path = join(current_directory, 'metadata.json')

arcpy.env.workspace = sgid

data = {}
def record_metadata(name, metadata):
  data[name] = {
    'snippet': metadata.purpose,
    'description': metadata.abstract,
    'accessInformation': metadata.credits, #: "Credits (Attribution)"
    'licenseInfo': metadata.limitation, #: terms of use
    'tags': ','.join(metadata.tags) #: comma-separated sequence of tags
  }

print('listing feature classes & tables')
for table in arcpy.ListFeatureClasses() + arcpy.ListTables():
  print(table)
  metadata = arcpy_metadata.MetadataEditor(join(sgid, table))
  record_metadata(table.split('.')[-1], metadata)

with open(json_file_path, 'wb') as file:
  file.write(json.dumps(data, sort_keys=True, indent=2))

print('done')
