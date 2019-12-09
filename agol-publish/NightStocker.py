import arcpy
import arcgis
import getpass
import os
import sys
import datetime
import csv
import tempfile
import shutil
import json
import pprint
# import gspread
# from oauth2client.service_account import ServiceAccountCredentials


def project_data(sgid_table, fgdb_folder, fgdb, is_table):
    web_mercator = arcpy.SpatialReference(3857)
    transformation = 'NAD_1983_to_WGS_1984_5'
    
    name = sgid_table.split(os.path.sep)[-1].replace('.', '_')
    output_table = os.path.join(fgdb_folder, fgdb, name)

    if not arcpy.Exists(os.path.join(fgdb_folder, fgdb)):
        #: create fgdb if it's missing
        print(f'creating {fgdb}')
        arcpy.management.CreateFileGDB(fgdb_folder, fgdb)

    #: Delete the feature class if it already exists. Don't use scratch for 
    #: long-term storage.
    if arcpy.Exists(output_table):
        arcpy.Delete_management(output_table)

    print('importing/projecting data')
    if is_table:
        arcpy.management.Copy(sgid_table, output_table)
    else:
        arcpy.management.Project(sgid_table, output_table, web_mercator, transformation)

    return output_table


def upload_layer(gis, service_definition, info, protect=True):
    '''
    Upload a service definition file to AGOL and publish it as a Hosted Feature
    Layer, setting appropriate information.

    gis: An ArcGIS API gis item.
    service_definition: path to a service definition file created in ArcGIS Pro
    info: a dictionary of the layer's information:
        name: layer name/title (string)
        summary: Summary snippet at top of AGOL page (string, max 2048 chars)
        groups: list of group names to share layer with (list of strings)
        tags: comma-separated string of tags (string)
        description: AGOL description (string)
        terms_of_use: AGOL terms of use/license info (string)
        credits: AGOL Credits/Attribution (string)
        folder: AGOL org's folder to move item to
    protect: if True, set AGOL flag to prevent item from being deleted

    returns the published feature layer's itemid
    '''

    print("uploading")
    sd_item = gis.content.add({}, data=service_definition)

    #: Publishing
    print("publishing")
    published_item = sd_item.publish()

    #: Updating information
    print("sharing") #: Everyone and groups.
    published_item.share(everyone=True, org=True, groups=info['groups'])
    if protect:
        print("delete protection")
        published_item.protect(enable=True)
    # sd_item.protect(enable=True)
    # print('authoritative')
    # published_item.content_status = 'authoritative'

    print("updating info")
    published_item.update(item_properties={'tags':info['tags'], 'description':info['description'], 'licenseInfo':info['terms_of_use'], 'snippet':info['summary'], 'accessInformation':info['credits']})

    print('folder')
    published_item.move(info['folder'])
    sd_item.move(info['folder'])

    #: Allow Downloads
    print("downloads")
    manager = arcgis.features.FeatureLayerCollection.fromitem(published_item).manager
    manager.update_definition({ 'capabilities': 'Query,Extract' })

    return published_item.itemid


def create_service_definition(layer_info, sde_path, temp_dir, project_path, 
                              map_name, describe):
    '''
    Creates a service defintion for a layer to be uploaded to AGOL from an SDE
    using an existing ArcGIS Pro project
    
    layer_info: Dictionary of info about the layer to be prepped for upload
        fc_name: Fully qualified name of the SDE feature class to be uploaded 
                 (string)
        title: title of the item for AGOL (string)
    sde_path: Path to the source .sde connection file
    temp_dir: Directory for holding reprojected fgdb and .sddraft & .sd files
    project_path: Path to an existing ArcGIS Pro project
    map_name: Name of the map in the Pro project to use
    describe: results of arcpy.da.Describe() on feature class

    returns: path to the .sd file
    '''

    try:
        start = datetime.datetime.now()

        sgid_table = os.path.join(sde_path, layer_info['fc_name'])
        # describe = arcpy.da.Describe(sgid_table)
        is_table = describe['datasetType'] == 'Table'

        projected_table = project_data(sgid_table, temp_dir, 'tempfgdb.gdb', is_table)
        # projected_table = sgid_table

        #: Get project and map
        proj = arcpy.mp.ArcGISProject(project_path)
        for m in proj.listMaps():
            if m.name == map_name:
                agol_map = m
        del m

        #: Remove any existing layers
        for l in agol_map.listLayers():
            agol_map.removeLayer(l)
        for t in agol_map.listTables():
            agol_map.removeTable(t)

        # : Add layer
        layer = agol_map.addDataFromPath(projected_table)

        #: Verify map projection
        cim = agol_map.getDefinition('V2')
        if cim.spatialReference['wkid'] != 3857:
            print('changing map projection')
            cim.spatialReference = {'wkid':3857}
            agol_map.setDefinition(cim)
        else:
            cim = None

        proj.save()

        # item_name = fc_name.split('.')[-1]
        item_name = layer_info['title']
        if not item_name.startswith('Utah'):
            item_name = f'Utah {item_name}'

        #: Staging
        print("staging")
        draft_path = os.path.join(temp_dir, f'{item_name}.sddraft')
        sd_path = draft_path[:-5]
        sharing_draft = agol_map.getWebLayerSharingDraft('HOSTING_SERVER', 'FEATURE', item_name, [layer])
        sharing_draft.exportToSDDraft(draft_path)
        arcpy.server.StageService(draft_path, sd_path)

        end = datetime.datetime.now()
        print('time: {}'.format(end-start))

    except arcpy.ExecuteError:
        raise  #: pass error up so that it can be logged and continued

    finally:

        if layer and not is_table:
            layer.updateConnectionProperties(os.path.join(temp_dir, 'tempfgdb.gdb'), r'c:\foo\bar.gdb', auto_update_joins_and_relates=False, validate=False)

            print(layer.isBroken)
            agol_map.removeLayer(layer)
            proj.save()

        # layer = None
        # cim = None
        # agol_map = None
        # proj = None
        # sharing_draft = None

        # del layer
        # del cim
        # del agol_map
        # del proj
        # del sharing_draft

        #: Delete feature class
        # print(f'Deleting {projected_table}...')
        # arcpy.Delete_management(projected_table)
        # tempgdb = os.path.join(temp_dir, 'tempfgdb.gdb')
        # print(f'Deleting {tempgdb}...')
        # shutil.rmtree(tempgdb)

    # return t
    return sd_path


def get_info(entry, generic_terms_of_use):
    '''
    Gets the info needed for publishing AGOL item.
    entry:  list from CSV: [fully-qualifed FC name, fc title, credit, method]
    '''
    category = entry[0].split('.')[-2].title()
    credit = entry[2] if entry[2] else 'AGRC'
    
    #: Get metadata for this specific featureclass
    metadata = metadata_lookup[entry[0].split('.')[-1]]

    #: Get tags, ensuring AGRC and SGID are in the list
    base_tags = ['AGRC', 'SGID']
    if metadata['tags']:
        tags = metadata['tags'].split(',')
        for tag in base_tags:
            if tag not in tags:
                tags.append(tag)
    else:
        tags = base_tags

    description = metadata['description']

    shelved_disclaimer = '<i><b>NOTE</b>: This dataset is an older dataset that we have removed from the SGID and \'shelved\' in ArcGIS Online. There may be a newer vintage of this dataset in the SGID.</i>'

    static_disclaimer = '<i><b>NOTE</b>: This dataset holds \'static\' data that we don\'t expect to change. We have removed it from the SDE database and placed it in ArcGIS Online, but it is still considered part of the SGID and shared on opendata.gis.utah.gov.</i>'

    if metadata['licenseInfo']:
        terms = metadata['licenseInfo']
    else:
        terms = generic_terms_of_use

    if entry[3] == 'shelved':
        group = 'AGRC Shelf'
        tags.append('shelved')
        folder = 'AGRC_Shelved'
        description = f'{shelved_disclaimer} <p> </p> <p>{description}</p>'
    elif entry[3] == 'static':
        group = f'Utah SGID {category}'
        tags.append('static')
        folder = f'Utah SGID {category}'
        description = f'{static_disclaimer} <p> </p> <p>{description}</p>'
    else:
        raise ValueError(f'Unknown shelving category: {entry[3]}')

    item_info = {
        'name': entry[1],
        'summary': metadata['snippet'][:2047],  #: truncate long snippets
        'groups': [group],
        'tags': ', '.join(tags),
        'description': description,
        'terms_of_use': terms,
        'credits': credit,
        'folder': folder
    }

    return item_info


#: TODO: finish this method
#: TODO add AGOL link to stewardship doc after item is shelved/staticed?
#: TODO create log of updates, either directly to stewardship or as csv
def log_action(action_info, method, log_path=None):
    '''
    Documents actions to stewardship doc, local csv, and AGOLItems metatable
    action_info:    a list of info relevant to a single feature class
    method:         a list of methods (gdoc, csv, or metatable)
    '''

    if 'gdoc' in method:
        pass
        # #: reauthorize gspread for each publish to make sure that the auth doesn't time out
        # scope = ['https://spreadsheets.google.com/feeds',
        #         'https://www.googleapis.com/auth/drive']

        # credentials = ServiceAccountCredentials.from_json_keyfile_name('deq-enviro-key.json', scope)
        # gc = gspread.authorize(credentials)

        # sheet = gc.open_by_key('1MBTwZg7pqpD9noFNAHU8d76EfXD3hMffmbjAHBtkoyQ').get_worksheet(0)
        # sheet.append_row([item_name, published_id, f'https://utah.maps.arcgis.com/home/item.html?id={published_id}'])
    if 'csv' in method:
        if not log_path:
            raise IOError('Logfile not specified')
        with open(log_path, 'a', newline='\n') as logfile:
            log_writer = csv.writer(logfile)
            log_writer.writerow(action_info)



#: TODO: Generalized tag checker method


#: TODO: get info from config file instead of hardcoding
sde_path = r'C:\gis\Projects\Data\sgid.agrc.utah.gov.sde'
project_path = r'c:\gis\projects\data\data.aprx'
map_name = 'AGOL Upload'
test_fc_name = r'SGID10.BIOSCIENCE.Habitat_BandtailedPigeon'
list_csv = r'c:\temp\shelved.csv'
terms_of_use_path = r'l:\sgid_to_agol\termsOfUse.html'
log_path = r'c:\temp\shelved_log.csv'

temp_dir = tempfile.TemporaryDirectory(prefix='shelved_')
# arcpy.env.scratchWorkspace = temp_dir.name

#: Connect to AGOL
# agol_user = sys.argv[1]
# gis = arcgis.gis.GIS('https://www.arcgis.com', agol_user, getpass.getpass(prompt='{}\'s password: '.format(agol_user)))

layers = []
with open(list_csv) as list_file:
    reader = csv.reader(list_file)
    next(reader)
    for row in reader:
        if row[3] != 'removed': #: Just don't even add removed items to the list
            layers.append(row)

test = layers
# test = [[test_fc_name, 'Bandtailed Pigeon Habitat', 'DWR', 'shelved']]

#: Get metadata for whole SDE, terms of use
metadata_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'metadata2.json')
metadata_lookup = None
with open(metadata_file_path, 'r') as meta_file:
    metadata_lookup = json.loads(meta_file.read())

with open(terms_of_use_path) as terms_file:
    generic_terms_of_use = terms_file.read()

log = []

for entry in test:
    print('\n Starting {}'.format(entry[0]))

    layer_info = {
        'fc_name':entry[0],
        'title':entry[1]
    }

    print('describing')
    describe = arcpy.da.Describe(os.path.join(sde_path, entry[0]))
    is_table = describe['datasetType'] == 'Table'
    if is_table:
        #: Log: AGOL title, operation, SGID name for stewardship doc, description, source/credit, shape type, endpoint, AGOL item ID
        log_entry = [entry[1], 'Table: not uploaded']
        log.append(log_entry)
        log_action(log_entry, ['csv'], log_path)

        continue

    try:
        print('creating sd')
        sd_path = create_service_definition(layer_info, sde_path, 
                                            temp_dir.name, project_path, 
                                            map_name, describe)

        item_info = get_info(entry, generic_terms_of_use)


        # pprint.pprint(item_info)

        # item_id = upload_layer(gis, sd_path, item_info, protect=False)
        item_id = 'testing'

        shape = describe['shapeType'].lower()
        dash_name = entry[1].replace(' ', '-').lower
        endpoint = f'https://opendata.gis.utah.gov/datasets/{dash_name}'
        data_layer = entry[0].partition('.')[2]  #: layername for stewardship doc

        #: Log: AGOL title, operation, SGID name for stewardship doc, description, source/credit, shape type, endpoint, AGOL item ID
        log_entry = [entry[1], entry[3], data_layer, item_info['description'], item_info['credits'], shape, endpoint, item_id]
        log.append(log_entry)
        log_action(log_entry, ['csv'], log_path)

        #: Delete files from the scratch folder
        # sddraft = sd_path + 'draft'
        # os.remove(sd_path)
        # os.remove(sddraft)
    except arcpy.ExecuteError:
        message = arcpy.GetMessages()
        print(message)
        log_action([entry[1], message.replace(',', ';')], 'csv', log_path)



