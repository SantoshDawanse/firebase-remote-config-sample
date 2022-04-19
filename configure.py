import argparse
import sys
import requests
import io
import json

from oauth2client.service_account import ServiceAccountCredentials
import os

# load environment variable from .envrc file
ENVIRONMENT = os.environ.get("ENVIRONMENT")
PROJECT_ID = os.environ.get("PROJECT_ID")

# check both ENVIRONMENT and PROJECT_ID exists
if ENVIRONMENT is None or PROJECT_ID is None:
  print("Project environment or project id is not assigned. Assign them in .envrc and activate.")
  sys.exit(1)

BASE_URL = 'https://firebaseremoteconfig.googleapis.com'
REMOTE_CONFIG_ENDPOINT = 'v1/projects/' + PROJECT_ID + '/remoteConfig'
REMOTE_CONFIG_URL = BASE_URL + '/' + REMOTE_CONFIG_ENDPOINT
SCOPES = ['https://www.googleapis.com/auth/firebase.remoteconfig']

# retrieve access token
def _get_access_token():
  """
  Retrieve a valid access token that can be used to authorize requests.
  :return: Access token.
  """
  credentials = ServiceAccountCredentials.from_json_keyfile_name(
      'service-account.json', SCOPES)
  access_token_info = credentials.get_access_token()
  return access_token_info.access_token

# load a remote config file
def _load_template():
  template = {}
  try:
    with open(f"config/config-{ENVIRONMENT}.json") as stream:
      template = json.load(stream)
    stream.close()
    return template
  except IOError:
    print(f"remote config file for environment {ENVIRONMENT} not found in current directory.")

# write to remote config file
def _write_template(template = {}):
  try:
    with open(f"config/config-{ENVIRONMENT}.json", "w") as stream:
      json.dump(template, stream)
    stream.close()
  except IOError:
    print(f"remote config file for environment {ENVIRONMENT} not found in current directory.")

# returns latest etag
def _get_etag():
  """
  Returns latest etag
  """
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }
  resp = requests.get(REMOTE_CONFIG_URL, headers=headers)
  return resp.headers['ETag']

# get remote config and write to config file
def _get():
  """
  Retrieve the current Firebase Remote Config template from server.
  Retrieve the current Firebase Remote Config template from server and store it
  locally.
  """
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }
  resp = requests.get(REMOTE_CONFIG_URL, headers=headers)

  if resp.status_code == 200:
    with io.open(f"config/config-{ENVIRONMENT}.json", 'wb') as f:
      f.write(resp.text.encode('utf-8'))

    print(f'Retrieved template has been written to config/config-{ENVIRONMENT}.json')
    print('ETag from server: {}'.format(resp.headers['ETag']))
  else:
    print('Unable to get template')
    print(resp.text)

# list the versions of config file
def _listVersions():
  """Print the last 5 Remote Config version's metadata."""
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }
  resp = requests.get(REMOTE_CONFIG_URL + ':listVersions?pageSize=5', headers=headers)

  if resp.status_code == 200:
    print('Versions:')
    print(resp.text)
  else:
    print('Request to print template versions failed.')
    print(resp.text)

# rollback remote config to specified version
def _rollback(version):
  """
  Roll back to an available version of Firebase Remote Config template.
  :param version: The version of the template to roll back to.
  """
  headers = {
    'Authorization': 'Bearer ' + _get_access_token()
  }

  json = {
    "version_number": version
  }
  resp = requests.post(REMOTE_CONFIG_URL + ':rollback', headers=headers, json=json)

  if resp.status_code == 200:
    print('Rolled back to version: ' + version)
    print(resp.text)
    print('ETag from server: {}'.format(resp.headers['ETag']))
  else:
    print('Request to roll back to version ' + version + ' failed.')
    print(resp.text)

# return response from firebase remote config
def _publish_if_valid(remote_config_url):
  """
  Returns response from firebase server after pushing updated local template
  """
  # get latest etag
  etag = _get_etag()
  with open(f"config/config-{ENVIRONMENT}.json", 'r', encoding='utf-8') as f:
    content = f.read()
  headers = {
    'Authorization': 'Bearer ' + _get_access_token(),
    'Content-Type': 'application/json; UTF-8',
    'If-Match': etag
  }
  return requests.put(remote_config_url, data=content.encode('utf-8'), headers=headers)

# validate remote config
def _validate(validate_only = True):
  UPDATED_REMOTE_CONFIG_URL = REMOTE_CONFIG_URL
  if(validate_only):
    UPDATED_REMOTE_CONFIG_URL += "?validate_only=true"
  return _publish_if_valid(UPDATED_REMOTE_CONFIG_URL)

# publish a remote config
def _publish():
  """
  Publish local template to Firebase server.
  """
  resp = _publish_if_valid(REMOTE_CONFIG_URL)
  if resp.status_code == 200:
    print('Template has been published.')
    print('ETag from server: {}'.format(resp.headers['ETag']))
  else:
    print('Unable to publish template.')
    print(resp.text)

# update parameter of remote config
def _update_parameter(args):
  try:
    template = _load_template()
    existing_params = template["parameters"]

    parameters = {}
    with open("config/update-parameters.json") as stream:
      parameters = json.load(stream)
    stream.close()

    for parameter, values in parameters["parameters"].items():
      existing_params[parameter] = values

    if hasattr(args, "update-parameter"):
      # validate and publish remote config
      resp = _validate()
      if resp.status_code == 200:
        _publish()
      else:
        print('The remote config template is not valid.')
        print(resp.text)
  except IOError:
    print("File config.json not found in current directory.")
  except ValueError:
    print(f"The {args.old_param} parameter is not found.")

# update conditions of remote config
def _update_condition(args):
  # list valid firebase remote config condition keys
  valid_condition_keys = set(["name", "expression", "tagColor"])
  try:
    # load the remote config template
    template = _load_template()

    conditions = {}
    with open("config/update-conditions.json", "r") as stream:
      conditions = json.load(stream)
    stream.close()

    # loop through each condition in config/update-conditions.json
    for condition in conditions["conditions"]:
      # check if condition has valid keys
      if not set(condition.keys()).issubset(valid_condition_keys):
        raise ValueError

      # check if condition passed already exists in remote config
      if [ob for ob in template["conditions"] if ob == condition]:
        print("This condition already exists in remote config \n")
      # check if condition exists in config/config.json
      elif condition["name"] in [value["name"] for value in template["conditions"]]:
        print("Updating...")
        # update the condition if condition name matches with remote config condition name
        for index, obj in enumerate(template["conditions"]):
          if obj["name"] == condition["name"]:
            template["conditions"][index] = condition
        # update the config.json
        _write_template(template)
      else:
        print("Creating...")
        # create a new condition
        template["conditions"].append(condition)
        # update the config.json
        _write_template(template)
    
    if hasattr(args, "update-condition"):
      # validate and publish remote config
      resp = _validate()
      if resp.status_code == 200:
        _publish()
      else:
        print('The remote config template is not valid.')
        print(resp.text)

  except ValueError:
    print("Invalid keys in condition.")
  except Exception as e:
    print(e)

# update remote config
def _update_remote_config(args):
  # fetch config from firebase remote config
  _get()

  # update conditions
  _update_condition(args)

  # update parameters
  _update_parameter(args)

  # validate and publish remote config
  resp = _validate()
  if resp.status_code == 200:
    _publish()
  else:
    print('The remote config template is not valid.')
    print(resp.text)

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--action')
  parser.add_argument('--version')

  sub_parsers = parser.add_subparsers()

  # add sub command to update parameters
  update_parameter = sub_parsers.add_parser("update-parameter", help="update parameters")
  update_parameter.set_defaults(func=_update_parameter)

  # add sub command to update conditions
  update_condition = sub_parsers.add_parser("update-condition", help="update conditions")
  update_condition.set_defaults(func=_update_condition)

  # add sub command to update remote config
  update_remote_config = sub_parsers.add_parser("update-remote-config", help="update remote config from config files.")
  update_remote_config.set_defaults(func=_update_remote_config)

  args = parser.parse_args()

  if "func" in args:
    args.func(args)

  if args.action and args.action == 'get':
    _get()
  elif args.action and args.action == 'publish':
    _publish()
  elif args.action and args.action == 'versions':
    _listVersions()
  elif args.action and args.action == 'rollback' and args.version:
    _rollback(args.version)
  elif args.action:
    print(
      '''
      Invalid command. Please use one of the following commands:
      python configure.py --action=get
      python configure.py --action=publish
      python configure.py --action=versions
      python configure.py --action=rollback --version=<TEMPLATE_VERSION_NUMBER>
      '''
    )

if __name__ == '__main__':
  main()